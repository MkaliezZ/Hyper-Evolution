"""Volatile rendezvous. Stores no learning files, API keys, device names or message plaintext."""
import asyncio
import base64
import hashlib
import hmac
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


def create_app():
    rooms = {}
    limits = defaultdict(deque)

    async def cleanup():
        while True:
            await asyncio.sleep(30)
            for room_id, room in list(rooms.items()):
                if room['expires'] < time.time():
                    rooms.pop(room_id, None)
                    for connection in list(room['sides'].values()):
                        try:
                            await connection.close(code=1000)
                        except Exception:
                            pass
            for client, stamps in list(limits.items()):
                if not stamps or stamps[-1] < time.time() - 600:
                    limits.pop(client, None)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(cleanup())
        yield
        task.cancel()

    app = FastAPI(docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.rooms = rooms

    def ice_servers(room_id):
        secret = os.environ.get('GROWTH_TURN_SECRET')
        urls = [u for u in os.environ.get('GROWTH_TURN_URLS', '').split(',') if u]
        if not secret or not urls:
            return []
        user = str(int(time.time()) + 1800) + ':' + room_id[:16]
        credential = base64.b64encode(hmac.new(secret.encode(), user.encode(), hashlib.sha1).digest()).decode()
        return [{'urls': urls, 'username': user, 'credential': credential}]

    @app.get('/health')
    def health():
        return {'ok': True, 'role': 'encrypted-rendezvous-only', 'learning_storage': False, 'turn_configured': bool(os.environ.get('GROWTH_TURN_SECRET'))}

    @app.websocket('/ws')
    async def socket(ws: WebSocket):
        client = ws.client.host if ws.client else 'unknown'
        stamps = limits[client]
        while stamps and stamps[0] < time.time() - 60:
            stamps.popleft()
        if len(stamps) >= 20 or len(rooms) > 256:
            await ws.close(code=1008)
            return
        stamps.append(time.time())
        await ws.accept()
        room_id, side = None, None
        try:
            hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
            room_id, side = hello.get('room'), hello.get('side')
            if not isinstance(room_id, str) or not re.fullmatch('[a-f0-9]{64}', room_id) or side not in [0, 1]:
                await ws.close(code=1008)
                return
            room = rooms.setdefault(room_id, {'sides': {}, 'expires': time.time() + 7200})
            if side in room['sides']:
                await ws.send_json({'kind': 'busy'})
                await ws.close(code=1008)
                return
            room['sides'][side] = ws
            if len(room['sides']) == 2:
                for connection in list(room['sides'].values()):
                    await connection.send_json({'kind': 'ready', 'ice_servers': ice_servers(room_id)})
            else:
                await ws.send_json({'kind': 'waiting'})
            while True:
                message = await ws.receive_text()
                if len(message) > 512 * 1024:
                    await ws.close(code=1009)
                    break
                # Only relay opaque encrypted signaling. Application content travels on DTLS data channels.
                import json
                data = json.loads(message)
                if set(data) != {'kind', 'ciphertext'} or data['kind'] != 'signal' or not isinstance(data['ciphertext'], str):
                    await ws.close(code=1008)
                    break
                other = room['sides'].get(1 - side)
                if other:
                    await other.send_json(data)
        except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, RuntimeError):
            pass
        finally:
            room = rooms.get(room_id)
            if room and room['sides'].get(side) is ws:
                room['sides'].pop(side, None)
                if not room['sides']:
                    rooms.pop(room_id, None)
    return app

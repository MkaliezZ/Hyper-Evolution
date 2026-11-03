"""Authenticated WebRTC data channels. Pairing secrets and signed events stay on the devices."""
import asyncio
import hashlib
import json
import re
import secrets
import time
from uuid import uuid4
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from websockets.asyncio.client import connect
from base.app.local_identity import Identity, b64, unb64, canonical


def channel_key(secret):
    return hashlib.sha256(b'hyper-growth-signaling-v1:' + secret.encode()).digest()


def seal(secret, payload):
    nonce = secrets.token_bytes(12)
    return b64(nonce + AESGCM(channel_key(secret)).encrypt(nonce, canonical(payload), b'hyper-growth-v1'))


def open_sealed(secret, value):
    try:
        raw = unb64(value)
        return json.loads(AESGCM(channel_key(secret)).decrypt(raw[:12], raw[12:], b'hyper-growth-v1'))
    except Exception:
        raise PermissionError('配对连接信息校验失败') from None


class PeerManager:
    def __init__(self, runtime, force_relay=False):
        self.runtime = runtime
        runtime.network = self
        self.force_relay = force_relay
        self.channels = {}
        self.tasks = {}
        self.states = {}
        self.invitation = None
        self.assemblies = {}
        self.stopping = False
        self.main_task = None
        self.established = set()
        self.errors = {}
        self.receive_locks = {}

    def status(self):
        return {'running': self.main_task is not None, 'states': dict(self.states), 'errors': dict(self.errors), 'invitation': self.invitation, 'relay_only_test': self.force_relay}

    def url(self):
        return self.runtime.config('network', {}).get('coordinator', 'wss://124.222.12.235/connect/ws')

    async def start(self):
        if self.main_task is None:
            self.main_task = asyncio.create_task(self._maintain())

    async def stop(self):
        self.stopping = True
        for task in list(self.tasks.values()):
            task.cancel()
        if self.main_task:
            self.main_task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)

    async def invite(self):
        self.runtime.require_role('teacher')
        code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(12))
        self.invitation = {'code': '-'.join(code[i:i+4] for i in range(0, 12, 4)), 'expires': int(time.time()) + 600, 'state': 'waiting'}
        self._launch('invite:' + code, code, 0, None, True)
        return self.invitation

    async def join(self, code):
        self.runtime.require_role('student')
        code = re.sub(r'[\s-]', '', code or '').upper()
        if not re.fullmatch('[A-HJ-NP-Z2-9]{12}', code):
            raise ValueError('请输入老师本地版给出的12位配对码')
        self._launch('join:' + code, code, 1, None, True)
        return {'connecting': True, 'note': '正在连接老师，请保持双方本机服务在线。'}

    def _launch(self, key, secret, side, peer_id, initial):
        if key not in self.tasks or self.tasks[key].done():
            self.tasks[key] = asyncio.create_task(self._session_loop(key, secret, side, peer_id, initial))

    async def _maintain(self):
        while not self.stopping:
            for peer in self.runtime.peers():
                if peer['state'] == 'active' and peer['id'] not in self.channels:
                    # A pending invitation for another student must not block established peers.
                    secret = self.runtime.vault.get('peer:' + peer['id'])
                    if secret:
                        self._launch(peer['id'], secret, 0 if self.runtime.role == 'teacher' else 1, peer['id'], False)
            for peer_id, channel in list(self.channels.items()):
                try:
                    self.runtime.peer(peer_id)
                    if channel.readyState == 'open' and channel.bufferedAmount < 256 * 1024:
                        for envelope in self.runtime.pending(peer_id)[:2]:
                            await self._send(channel, envelope)
                except Exception:
                    self.states[peer_id] = 'waiting_for_reconnect'
            for key, value in list(self.assemblies.items()):
                if value['time'] < time.time() - 120:
                    self.assemblies.pop(key, None)
            await asyncio.sleep(2)

    async def _send(self, channel, envelope):
        raw = canonical(envelope)
        total = max(1, (len(raw) + 23999) // 24000)
        for seq in range(total):
            while channel.readyState == 'open' and channel.bufferedAmount > 512 * 1024:
                await asyncio.sleep(.02)
            if channel.readyState != 'open':
                raise ConnectionError('channel closed')
            channel.send(json.dumps({'kind': 'chunk', 'id': envelope['body']['id'], 'seq': seq, 'total': total, 'data': b64(raw[seq*24000:(seq+1)*24000])}))

    async def _receive_chunk(self, peer_id, channel, frame):
        if frame.get('kind') != 'chunk' or not isinstance(frame.get('id'), str) or len(frame['id']) > 128 or not isinstance(frame.get('total'), int) or not 1 <= frame['total'] <= 900 or not isinstance(frame.get('seq'), int) or not 0 <= frame['seq'] < frame['total']:
            raise ValueError('同步分片无效')
        key = peer_id + ':' + frame['id']
        if key not in self.assemblies and sum(k.startswith(peer_id + ':') for k in self.assemblies) >= 3:
            raise ValueError('同时同步的内容过多')
        state = self.assemblies.setdefault(key, {'total': frame['total'], 'parts': {}, 'time': time.time()})
        data = unb64(frame['data'])
        if len(data) > 24000 or frame['total'] != state['total']:
            raise ValueError('同步分片长度无效')
        state['parts'][frame['seq']] = data
        if len(state['parts']) == state['total']:
            raw = b''.join(state['parts'][i] for i in range(state['total']))
            self.assemblies.pop(key, None)
            envelope = json.loads(raw)
            if envelope['body']['id'] != frame['id'] or envelope['body']['sender'] != peer_id:
                raise PermissionError('同步发送方不匹配')
            await asyncio.to_thread(self.runtime.receive, envelope)
            if envelope['body']['kind'] != 'ack':
                ack = self.runtime.identity.envelope(peer_id, 'ack', {'id': envelope['body']['id']}, uuid4().hex)
                await self._send(channel, ack)

    async def _session_loop(self, key, secret, side, expected_peer, initial):
        deadline = time.time() + 600 if initial else float('inf')
        connected_once = False
        while not self.stopping and time.time() < deadline:
            if expected_peer:
                try:
                    self.runtime.peer(expected_peer)
                except PermissionError:
                    return
            pc, remote_hello, local_channel, active_peer = None, None, None, None
            pair_secret = b64(secrets.token_bytes(32)) if initial and side == 0 else None
            closed = asyncio.Event()

            async def handle_message(message, channel):
                nonlocal pair_secret, active_peer, connected_once
                try:
                    if not isinstance(message, str) or len(message) > 100000:
                        raise ValueError('消息无效')
                    frame = json.loads(message)
                    if frame.get('kind') == 'hello':
                        hello = frame['hello']
                        if remote_hello != hello or (expected_peer and hello['id'] != expected_peer):
                            raise PermissionError('连接设备与配对身份不一致')
                        Identity.verify(hello['public_key'], hello, frame['signature'])
                        if initial:
                            if side == 1:
                                pair_secret = frame.get('pair_secret')
                                if not isinstance(pair_secret, str) or len(unb64(pair_secret)) != 32:
                                    raise PermissionError('缺少安全重连凭据')
                            self.runtime.accept_peer(hello, pair_secret)
                        else:
                            peer = self.runtime.peer(hello['id'])
                            if peer['public_key'] != hello['public_key']:
                                raise PermissionError('设备公钥不匹配')
                        active_peer = hello['id']
                        self.channels[active_peer] = channel
                        self.states[active_peer] = 'connected'
                        connected_once = True
                        self.established.add(key)
                        if initial and self.invitation:
                            self.invitation['state'] = 'used'
                        return
                    if not active_peer:
                        raise PermissionError('设备尚未完成身份验证')
                    async with self.receive_locks.setdefault(active_peer, asyncio.Lock()):
                        await self._receive_chunk(active_peer, channel, frame)
                except Exception:
                    self.states[active_peer or key.split(':')[0]] = 'message_rejected'

            def configure_channel(channel):
                @channel.on('open')
                def on_open():
                    hello = self.runtime.hello()
                    message = {'kind': 'hello', 'hello': hello, 'signature': self.runtime.identity.sign(hello)}
                    if initial and side == 0:
                        message['pair_secret'] = pair_secret
                    channel.send(json.dumps(message, ensure_ascii=False))

                @channel.on('message')
                def on_message(message):
                    asyncio.create_task(handle_message(message, channel))

                @channel.on('close')
                def on_close():
                    closed.set()
                if channel.readyState == 'open':
                    on_open()

            def filtered_sdp(description):
                sdp = description.sdp
                if self.force_relay:
                    lines = [line for line in sdp.splitlines() if not line.startswith('a=candidate:') or ' typ relay' in line]
                    if not any(' typ relay' in line for line in lines):
                        raise ValueError('TURN未生成relay候选，不能把直连冒充中转验证')
                    sdp = '\r\n'.join(lines) + '\r\n'
                return sdp

            self.states[expected_peer or ('invitation' if side == 0 else 'joining')] = 'connecting'
            room_id = hashlib.sha256(('initial:' if initial else 'paired:').encode() + secret.encode()).hexdigest()
            try:
                async with connect(self.url(), max_size=1024*1024, open_timeout=15, ping_interval=20) as ws:
                    await ws.send(json.dumps({'room': room_id, 'side': side}))
                    while not self.stopping and not closed.is_set():
                        try:
                            data = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                        except asyncio.TimeoutError:
                            continue
                        if data.get('kind') == 'busy':
                            raise ValueError('配对码已被其他设备使用')
                        if data.get('kind') == 'ready' and pc is None:
                            ice = [RTCIceServer(**value) for value in data.get('ice_servers', [])]
                            pc = RTCPeerConnection(RTCConfiguration(iceServers=ice))

                            @pc.on('connectionstatechange')
                            async def connection_changed():
                                if pc.connectionState in ['failed', 'closed']:
                                    closed.set()

                            @pc.on('datachannel')
                            def incoming(channel):
                                configure_channel(channel)

                            if side == 0:
                                local_channel = pc.createDataChannel('hyper-growth', ordered=True)
                                configure_channel(local_channel)
                                await pc.setLocalDescription(await pc.createOffer())
                                await ws.send(json.dumps({'kind': 'signal', 'ciphertext': seal(secret, {'type': 'offer', 'sdp': filtered_sdp(pc.localDescription), 'hello': self.runtime.hello()})}))
                        elif data.get('kind') == 'signal':
                            message = open_sealed(secret, data['ciphertext'])
                            remote_hello = message['hello']
                            if pc is None:
                                raise ValueError('连接尚未就绪')
                            await pc.setRemoteDescription(RTCSessionDescription(sdp=message['sdp'], type=message['type']))
                            if message['type'] == 'offer':
                                await pc.setLocalDescription(await pc.createAnswer())
                                await ws.send(json.dumps({'kind': 'signal', 'ciphertext': seal(secret, {'type': 'answer', 'sdp': filtered_sdp(pc.localDescription), 'hello': self.runtime.hello()})}))
            except asyncio.CancelledError:
                break
            except Exception as error:
                state_key = expected_peer or ('invitation' if side == 0 else 'joining')
                self.states[state_key] = 'waiting_for_reconnect'
                # Exception class helps diagnose reachability without recording SDP, keys or works.
                self.errors[state_key] = type(error).__name__ + (': ' + str(error) if isinstance(error, ValueError) else '')
            finally:
                if active_peer and self.channels.get(active_peer) is not None:
                    self.channels.pop(active_peer, None)
                    self.states[active_peer] = 'waiting_for_reconnect'
                if pc:
                    await pc.close()
            if initial and connected_once:
                break
            await asyncio.sleep(3)

"""Real WebRTC loopback exchange between independent device data directories (not a cross-network claim)."""
import asyncio
import json
import socket
import tempfile
from pathlib import Path
import uvicorn
from base.app.local_runtime import LocalRuntime
from growth_local.peer import PeerManager
from growth_local.signal import create_app


class TestVault:
    def __init__(self): self.data = {}
    def get(self, key): return self.data.get(key)
    def set(self, key, value): self.data[key] = value
    def delete(self, key): self.data.pop(key, None)


async def until(predicate, seconds=30):
    for _ in range(seconds*10):
        if predicate(): return
        await asyncio.sleep(.1)
    raise AssertionError('Timed out waiting for real device exchange')


async def main():
    with tempfile.TemporaryDirectory(prefix='growth-peer-') as temp:
        teacher = LocalRuntime(Path(temp)/'teacher', TestVault())
        student = LocalRuntime(Path(temp)/'student', TestVault())
        teacher.setup('teacher', '合成真实RTC教师')
        student.setup('student', '合成真实RTC学生')
        signal_app = create_app()
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen(128)
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(signal_app, log_level='warning', access_log=False))
        server_task = asyncio.create_task(server.serve(sockets=[sock]))
        await until(lambda: server.started)
        for r in [teacher, student]: r.save_config('network', {'coordinator': f'ws://127.0.0.1:{port}/ws'})
        a, b = PeerManager(teacher), PeerManager(student)
        await a.start(); await b.start()
        try:
            invitation = await a.invite()
            await b.join(invitation['code'])
            await until(lambda: bool(a.channels) and bool(b.channels))
            assert teacher.peer(student.identity.id)['name'] == student.profile['name']
            task = teacher.assign(student.identity.id, 'writing', 'rtc-writing')
            await until(lambda: len(student.student_dashboard()['tasks']) == 1)
            student.submit(task['id'], {}, 'Synthetic RTC writing sample. Could you explain the next step?', [], 'submit-1')
            await until(lambda: len(teacher.task(task['id'])['attempts']) == 1)
            sid = teacher.task(task['id'])['attempts'][0]['id']
            teacher.feedback(sid, '合成RTC联动：请求清楚，补充场次。', '补充具体可用时间后修订。', 'needs_revision', None, 'rtc-feedback')
            await until(lambda: student.task(task['id'])['attempts'] and student.task(task['id'])['attempts'][0]['evaluation'].get('judgement') == 'needs_revision')
            student.submit(task['id'], {}, 'Revised synthetic RTC writing, available Monday at 10.', [], 'submit-2')
            await until(lambda: len(teacher.task(task['id'])['attempts']) == 2)
            await until(lambda: not teacher.pending(student.identity.id) and not student.pending(teacher.identity.id))
            # Shutdown and reopen the student transport; durable records and paired secret reconnect.
            await a.invite()  # An unused invitation for a second student cannot block this peer.
            await b.stop()
            await until(lambda: student.identity.id not in a.channels)
            b = PeerManager(student)
            await b.start()
            await until(lambda: bool(b.channels) and student.identity.id in a.channels, 45)
            assert len(teacher.task(task['id'])['attempts']) == 2
            report = {'ok': True, 'transport': 'real aiortc DTLS/SCTP data channels', 'separate_databases': True, 'pairing': True, 'assignment_submission_signed_feedback_revision': True, 'durable_acknowledgements': True, 'reconnection': True, 'cross_network': False, 'signal_learning_storage': False, 'synthetic_only': True}
            output = Path(__file__).resolve().parents[1]/'artifacts/local-peer-verification.json'
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
            print(json.dumps(report,ensure_ascii=False))
        except Exception:
            print(json.dumps({'teacher_states': a.status(), 'student_states': b.status()},ensure_ascii=False))
            raise
        finally:
            await a.stop(); await b.stop()
            server.should_exit = True
            await server_task


if __name__ == '__main__': asyncio.run(main())

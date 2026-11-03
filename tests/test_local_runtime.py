import asyncio
import base64
import json
import secrets
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from base.app.local_runtime import LocalRuntime
from base.app.local_identity import b64
from base.app.local_agent import run_agent, execute_job, learning_context
from base.app.content import make_drill
from growth_local.mcp import create_mcp
from growth_local.web import create_app


class MemoryVault:
    """Test-only vault. No production launcher flag enables this backend."""
    def __init__(self): self.values = {}
    def get(self, key): return self.values.get(key)
    def set(self, key, value): self.values[key] = value
    def delete(self, key): self.values.pop(key, None)


def test_two_local_profiles_do_not_overwrite_browser_cookies(tmp_path):
    a=LocalRuntime(tmp_path/'a',MemoryVault()); b=LocalRuntime(tmp_path/'b',MemoryVault())
    first=create_app(a.folder,runtime=a,network=False)
    second=create_app(b.folder,runtime=b,network=False)
    with TestClient(first,base_url='http://127.0.0.1') as x, TestClient(second,base_url='http://127.0.0.1') as y:
        assert x.post('/api/local/session',json={'bootstrap':first.state.bootstrap}).status_code==200
        assert y.post('/api/local/session',json={'bootstrap':second.state.bootstrap}).status_code==200
        assert set(x.cookies.keys()).isdisjoint(y.cookies.keys())
        x.cookies.update(y.cookies)
        assert x.get('/api/local/status').json()['device_id']==a.identity.id


def instance(folder, role, name):
    r = LocalRuntime(folder, MemoryVault())
    r.setup(role, name, 'toefl', 'predeparture')
    return r


def pair(a, b):
    secret = b64(secrets.token_bytes(32))
    a.accept_peer(b.hello(), secret)
    b.accept_peer(a.hello(), secret)


def drain(a, b):
    for envelope in a.pending(b.identity.id):
        b.receive(envelope)
        a.ack(b.identity.id, envelope['body']['id'])


def test_local_model_key_not_in_sqlite_status_or_synchronization(tmp_path):
    teacher = instance(tmp_path/'t', 'teacher', '合成老师')
    student = instance(tmp_path/'s', 'student', '合成学生')
    key = 'synthetic-test-only-secret'
    cfg = {'provider': 'deepseek', 'base_url': 'https://api.deepseek.com', 'model': 'test'}
    teacher.save_model(cfg, key, remember=True)
    assert key not in json.dumps(teacher.status())
    assert key.encode() not in (teacher.folder/'base.sqlite3').read_bytes()
    assert teacher.vault.get('api') == key
    teacher.save_model(cfg, remember=False)
    assert teacher.vault.get('api') is None and teacher.model_key() == key
    restored = LocalRuntime(teacher.folder, teacher.vault)
    assert not restored.model_status()['configured']
    pair(teacher, student)
    teacher.assign(student.identity.id, 'diagnostic', 'diag')
    assert key not in json.dumps(teacher.pending(student.identity.id))


def test_two_local_databases_signed_task_submission_revision_feedback(tmp_path):
    t = instance(tmp_path/'t', 'teacher', '合成老师')
    s = instance(tmp_path/'s', 'student', '合成学生')
    pair(t, s)
    task = t.assign(s.identity.id, 'diagnostic', 'diag')
    # Before teacher delivery, student holds neither teacher task nor its answer keys.
    assert not s.student_dashboard()['tasks']
    drain(t, s)
    received = s.task(task['id'])
    assert received['signature_verified'] and 'key' not in received['pack']['items'][0]
    full = t.service._task(task['id'])['snapshot']['growth']
    answers = {i['id']: i['key'][0] for i in full['items']}
    s.submit(task['id'], answers, '', [], 'first')
    drain(s, t)
    drain(t, s)
    assert s.task(task['id'])['attempts'][0]['automatic']['score'] == 5
    sid = t.task(task['id'])['attempts'][0]['id']
    t.feedback(sid, '合成测试：定位细节明确', '换新材料再独立完成', 'meets_criteria', None, 'feedback')
    drain(t, s)
    assert s.task(task['id'])['attempts'][0]['evaluation']['judgement'] == 'meets_criteria'
    s.submit(task['id'], answers, '', [], 'revision')
    drain(s, t)
    drain(t, s)
    assert len(t.task(task['id'])['attempts']) == 2
    assert len(s.task(task['id'])['attempts']) == 2
    assert not t.pending(s.identity.id)


def test_signature_tampering_unauthorized_peer_and_replay(tmp_path):
    t = instance(tmp_path/'t', 'teacher', 'T')
    s = instance(tmp_path/'s', 'student', 'S')
    other = instance(tmp_path/'o', 'student', 'O')
    pair(t, s)
    task = t.assign(s.identity.id, 'writing', 'write')
    event = t.pending(s.identity.id)[0]
    tampered = json.loads(json.dumps(event))
    tampered['body']['payload']['task']['pack']['title'] = 'tampered'
    with pytest.raises(PermissionError): s.receive(tampered)
    with pytest.raises(PermissionError): other.receive(event)
    assert s.receive(event)['duplicate'] is False
    assert s.receive(event)['duplicate'] is True
    forged = s.identity.envelope(t.identity.id, 'task.updated', {'task': task}, 'forge')
    with pytest.raises(PermissionError): t.receive(forged)
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError): t.receive(s.identity.envelope(t.identity.id, 'submission', {}, 'revoked'))
    assert t.service.tasks(t.peers()[0]['learner_id'])


def test_local_mcp_role_filter_and_same_database(tmp_path):
    t = instance(tmp_path/'t', 'teacher', 'T')
    s = instance(tmp_path/'s', 'student', 'S')
    pair(t, s)
    async def run():
        mcp = create_mcp(s)
        names = {tool.name for tool in await mcp.list_tools()}
        assert 'submit_work' in names and 'record_teacher_feedback' not in names
        with pytest.raises(PermissionError): await mcp.call_tool('record_teacher_feedback', {})
        tools = {tool.name for tool in await create_mcp(t).list_tools()}
        assert 'record_teacher_feedback' in tools and 'submit_work' not in tools
    asyncio.run(run())
    restored = LocalRuntime(s.folder, s.vault)
    assert restored.identity.id == s.identity.id
    assert restored.peer(t.identity.id)['role'] == 'teacher'


def test_html_bootstrap_origin_and_secret_configuration(tmp_path):
    r = LocalRuntime(tmp_path, MemoryVault())
    app = create_app(tmp_path, runtime=r, network=False)
    with TestClient(app, base_url='http://127.0.0.1') as web:
        assert web.get('/api/local/status').status_code == 401
        assert web.post('/api/local/session', headers={'Origin': 'https://untrusted.invalid'}, json={'bootstrap': app.state.bootstrap}).status_code == 403
        assert web.post('/api/local/session', json={'bootstrap': app.state.bootstrap}).status_code == 200
        assert web.post('/api/local/session', json={'bootstrap': app.state.bootstrap}).status_code == 403
        assert web.post('/api/local/setup', json={'name': 'S', 'role': 'student'}).status_code == 200
        assert web.post('/api/local/setup', json={'name': 'T', 'role': 'teacher'}).status_code == 400
        assert web.post('/api/local/feedback/nonexistent', json={'comment':'x','next_step':'y','request_key':'deny'}).status_code == 403
        cfg = {'provider': 'deepseek', 'base_url': 'https://api.deepseek.com', 'model': 'test', 'key': 'synthetic-key', 'remember': True}
        saved = web.put('/api/local/model', json=cfg)
        assert saved.status_code == 200 and 'synthetic-key' not in saved.text
        assert web.get('/api/local/status', headers={'Host': 'untrusted.invalid'}).status_code == 421
        assert web.put('/api/local/model', json={**cfg, 'base_url': 'http://untrusted.invalid'}).status_code == 400
        assert web.delete('/api/local/model/key').json()['configured'] is False


def test_agent_uses_read_tools_and_saves_pending_draft_without_teacher_approval(tmp_path):
    s = instance(tmp_path/'s', 'student', 'PRIVATE NAME')
    drill = make_drill('toefl', 'predeparture', seed='local-agent-test')
    output = {k: drill[k] for k in ['title', 'task_type', 'instructions', 'stimulus', 'items']}
    output['task_type'] = 'daily_life'
    model = TestModel(custom_output_args=output)
    result = asyncio.run(run_agent(s, {'mode': 'draft'}, model))
    assert set(result['tools_used']) == {'get_learning_evidence', 'get_exam_blueprint'}
    assert result['output']['status'] == 'pending_review'
    assert s.service.resources()[0]['status'] == 'pending_review'
    with pytest.raises(PermissionError): s.feedback('any', 'x', 'y', None, None, 'x')
    with pytest.raises(ValueError): s.start_model_practice(result['output']['pack_id'], 'early')
    diag = s.start_self('diagnostic', 'diag')
    full = s.service._task(diag['id'])['snapshot']['growth']
    s.submit(diag['id'], {i['id']: i['key'][0] for i in full['items']}, '', [], 'diag')
    own = s.start_model_practice(result['output']['pack_id'], 'use')
    assert own['pack']['status'] == 'pending_review'


def test_agent_context_excludes_names_teacher_notes_and_unsubmitted_answers(tmp_path):
    t = instance(tmp_path/'t', 'teacher', 'PRIVATE TEACHER')
    s = instance(tmp_path/'s', 'student', 'PRIVATE STUDENT')
    pair(t, s)
    id = t.peer(s.identity.id)['learner_id']
    t.service.update_person(id, 'PRIVATE STUDENT', 'Find evidence', 'toefl', 'predeparture', 'SECRET TEACHER NOTE')
    t.assign(s.identity.id, 'diagnostic', 'diag')
    raw = json.dumps(learning_context(t, s.identity.id))
    assert 'PRIVATE' not in raw and 'SECRET' not in raw and 'key' not in raw
    assert 'BLUEPRINT' not in raw


def test_model_job_persistence_and_plaintext_no_fallback(tmp_path):
    s = instance(tmp_path, 'student', 'S')
    job = s.create_job({'mode': 'coach', 'prompt': 'Give next step'})
    asyncio.run(execute_job(s, job, TestModel(custom_output_args={'message': '先定位原文依据', 'next_steps': ['做新材料练习'], 'boundary': '不是正式成绩'})))
    assert s.job(job)['status'] == 'completed'
    restored = LocalRuntime(tmp_path, s.vault)
    assert restored.job(job)['result']['automatic_teacher_judgement'] is False

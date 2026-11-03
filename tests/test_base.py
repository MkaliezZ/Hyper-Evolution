import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from base.app.activities import prepare_activity
from base.core import Store
from base.web import create_app


def text_activity():
    return {**prepare_activity(), 'mode': 'text'}


def numeric():
    return {**prepare_activity(), 'name': '数值伴学', 'mode': 'numeric', 'expected': '1/2'}


def test_config_errors_point_to_editable_file(tmp_path, monkeypatch):
    from base.app import activities
    monkeypatch.setattr(activities, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='app/config.json'):
        activities.prepare_activity()
    (tmp_path / 'config.json').write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError, match='顶层必须是对象'):
        activities.prepare_activity()


def test_names_isolation_and_manual_loop(tmp_path):
    service = Store(tmp_path)
    a, b = service.create('小林', text_activity()), service.create('小林', text_activity())
    assert a['learner_id'] != b['learner_id']
    submitted = service.submit(a['token'], '先试做，再记录观察。', 'one')
    assert submitted['evaluation']['status'] == 'pending'
    service.feedback(submitted['id'], '已写明行动，请增加观察时间。', '明天执行并记录。')
    assert Store(tmp_path).public_task(a['token'])['submissions'][0]['evaluation']['status'] == 'reviewed'
    assert service.public_task(b['token'])['submissions'] == []
    with service.db() as db:
        assert db.execute('SELECT count(*) FROM reviews').fetchone()[0] == 1


def test_numeric_snapshot_and_no_private_answer(tmp_path):
    service = Store(tmp_path)
    draft = numeric()
    task = service.create('测试', draft)
    draft['expected'] = '9'
    assert 'expected' not in service.public_task(task['token'])['activity']
    assert service.submit(task['token'], '0.5', 'a')['evaluation']['correct'] is True
    assert service.submit(task['token'], '2/3', 'b')['evaluation']['correct'] is False
    with pytest.raises(ValueError):
        service.submit(task['token'], '__import__("os")', 'c')


def test_idempotency_concurrent_and_conflict(tmp_path):
    service = Store(tmp_path)
    task = service.create('测试', text_activity(), request_key='create-one')
    assert service.create('测试', text_activity(), request_key='create-one')['id'] == task['id']
    with pytest.raises(ValueError):
        service.create('别人', text_activity(), request_key='create-one')
    with ThreadPoolExecutor(4) as pool:
        ids = list(pool.map(lambda _: service.submit(task['token'], '内容', 'same')['id'], range(4)))
    assert len(set(ids)) == 1
    with pytest.raises(ValueError):
        service.submit(task['token'], '改过的内容', 'same')


def test_validation_never_saves_invalid_task(tmp_path):
    service = Store(tmp_path)
    with pytest.raises(ValueError):
        service.create('测试', {'mode': 'numeric'})
    assert service.tasks() == []
    with pytest.raises(KeyError):
        service.task('unknown')


def test_http_roles_origin_and_complete_loop(tmp_path):
    app = create_app(tmp_path)
    owner, learner = TestClient(app), TestClient(app)
    assert owner.get('/api/manage').status_code == 403
    assert owner.post('/api/login', json={'token': {}}).status_code == 403
    assert owner.post('/api/login', json=[]).status_code == 400
    assert owner.post('/api/login', json={'token': app.state.store.owner_token}).status_code == 200
    task = owner.post('/api/tasks', json={'learner': '合成学习者', 'draft': text_activity()}).json()
    path = '/api/learn/' + task['token']
    assert learner.post('/api/tasks', json={'learner': '越权'}).status_code == 403
    assert owner.post('/api/tasks', headers={'Origin': 'https://wrong.invalid'}, json={'learner': '越权'}).status_code == 403
    submission = learner.post(path, json={'answer': '行动与观察', 'request_key': 'one'}).json()
    assert learner.post('/api/feedback/' + submission['id'], json={'comment': '越权', 'next_step': '越权'}).status_code == 403
    assert owner.post('/api/feedback/' + submission['id'], json={'comment': '补充具体观察。', 'next_step': '再做一次。'}).status_code == 200
    result = learner.get(path).json()
    assert result['submissions'][0]['evaluation']['next_step'] == '再做一次。'
    assert 'owner_token' not in json.dumps(result)
    assert learner.get('/learn/'+task['token']).status_code == 200


def test_structural_hints_never_award_grade(tmp_path):
    from base.app.assessment import evaluate_submission, validate_activity
    draft = text_activity() | {'structure': {'sections': ['现状', '行动'], 'min_chars': 8, 'max_chars': 40, 'vague_phrases': ['差不多']}}
    validate_activity(draft)
    bad = evaluate_submission(draft, '现状差不多')
    assert bad['status'] == 'pending' and bad['correct'] is None and 'total' not in bad
    assert bad['structure']['missing_sections'] == ['行动']
    assert bad['structure']['vague_phrases'] == ['差不多'] and not bad['structure']['length_ok']
    good = evaluate_submission(draft, '现状已观察；行动先试做一个小任务。')
    assert good['status'] == 'pending' and good['structure']['length_ok']
    assert not good['structure']['missing_sections']
    with pytest.raises(ValueError):
        validate_activity(text_activity() | {'structure': {'min_chars': 10, 'max_chars': 2}})


def test_structured_scores_snapshot_validation_and_restart(tmp_path):
    rubric = [{'label': '清楚', 'max_score': 5}, {'label': '可执行', 'max_score': 10}]
    service = Store(tmp_path)
    task = service.create('评分合成学习者', text_activity() | {'rubric': rubric})
    row = service.submit(task['token'], '行动说明', 'one')
    scores = [{'label': '清楚', 'score': 4}, {'label': '可执行', 'score': 8}]
    result = service.feedback(row['id'], '补充时间。', '明天再试。', scores)
    assert result['total'] == 12 and result['max_total'] == 15
    rubric[0]['max_score'] = 100
    assert Store(tmp_path).public_task(task['token'])['submissions'][0]['evaluation']['scores'][0]['max_score'] == 5
    assert service.tasks()[0]['rubric'][0]['max_score'] == 5
    for invalid in ([], [{'label': '清楚', 'score': 6}, scores[1]], [{'label': '清楚', 'score': True}, scores[1]], [{'label': '其他', 'score': 1}, scores[1]]):
        with pytest.raises(ValueError):
            service.feedback(row['id'], '反馈', '下一步', invalid)
    with pytest.raises(PermissionError):
        service.authorize('错误口令')


def test_score_api_rejects_student_write(tmp_path):
    app = create_app(tmp_path)
    owner, learner = TestClient(app), TestClient(app)
    owner.post('/api/login', json={'token': app.state.store.owner_token})
    draft = text_activity() | {'rubric': [{'label': '内容', 'max_score': 10}]}
    task = owner.post('/api/tasks', json={'learner': '合成', 'draft': draft}).json()
    row = learner.post('/api/learn/'+task['token'], json={'answer': '内容', 'request_key': 'one'}).json()
    payload = {'comment': '反馈', 'next_step': '修订', 'scores': [{'label': '内容', 'score': 9}]}
    assert learner.post('/api/feedback/'+row['id'], json=payload).status_code == 403
    assert owner.post('/api/feedback/'+row['id'], json=payload).json()['total'] == 9
    assert learner.get('/api/learn/'+task['token']).json()['submissions'][0]['evaluation']['total'] == 9


def test_backup_supports_isolated_data_and_safe_restore(tmp_path):
    from pathlib import Path
    import shutil
    import subprocess
    import sys
    import zipfile
    project = tmp_path / 'starter'
    (project / 'scripts').mkdir(parents=True)
    (project / 'src/base/app').mkdir(parents=True)
    script = project / 'scripts/backup.py'
    root = Path(__file__).resolve().parents[1]
    source = root / 'base-starter/scripts/backup.py'
    shutil.copy(source if source.exists() else root / 'scripts/backup.py', script)
    service = Store(project / 'data/isolated')
    service.create('合成备份学习者')
    archive = project / 'data/backup.zip'
    subprocess.run([sys.executable, str(script), 'backup', str(archive)], check=True, capture_output=True)
    with zipfile.ZipFile(archive) as z:
        assert 'data/isolated/base.sqlite3' in z.namelist()
        assert 'data/backup.zip' not in z.namelist()
    restored = tmp_path / 'restored'
    subprocess.run([sys.executable, str(script), 'restore', str(archive), str(restored)], check=True, capture_output=True)
    assert (restored / 'data/isolated/base.sqlite3').read_bytes() == service.path.read_bytes()
    malicious = tmp_path / 'invalid.zip'
    with zipfile.ZipFile(malicious, 'w') as z:
        z.writestr('../escape.txt', 'must not escape')
    result = subprocess.run([sys.executable, str(script), 'restore', str(malicious), str(tmp_path/'empty')], capture_output=True)
    assert result.returncode != 0 and not (tmp_path/'escape.txt').exists()


def test_separate_data_directories_do_not_share_identity(tmp_path):
    a, b = Store(tmp_path / 'first'), Store(tmp_path / 'second')
    task = a.create('同名合成学习者')
    assert a.owner_token != b.owner_token
    with pytest.raises(PermissionError):
        b.authorize(a.owner_token)
    with pytest.raises(KeyError):
        b.public_task(task['token'])
    assert b.tasks() == []

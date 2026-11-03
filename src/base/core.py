"""Small shared store: snapshots, scoped access and idempotent submissions."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
from uuid import uuid4
from base.app.activities import prepare_activity
from base.app.assessment import validate_activity, evaluate_submission, valid_number
from base.app.profile import validate_profile
from base.app.strategy import plan_next


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / 'base.sqlite3'
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, learner_id TEXT NOT NULL, learner TEXT NOT NULL, token TEXT UNIQUE NOT NULL, snapshot TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), request_key TEXT NOT NULL, answer TEXT NOT NULL, evaluation TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(task_id,request_key));
            CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, submission_id TEXT NOT NULL REFERENCES submissions(id), evaluation TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS task_requests(key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, task_id TEXT NOT NULL REFERENCES tasks(id));
            CREATE TABLE IF NOT EXISTS learners(id TEXT PRIMARY KEY, name TEXT NOT NULL, profile TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learners(id), task_id TEXT, kind TEXT NOT NULL, actor TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feedback_requests(key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS profile_requests(key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, learner_id TEXT NOT NULL REFERENCES learners(id));
            ''')
            if 'state' not in {row['name'] for row in db.execute('PRAGMA table_info(tasks)')}:
                db.execute("ALTER TABLE tasks ADD COLUMN state TEXT NOT NULL DEFAULT 'active'")
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('owner_token', secrets.token_urlsafe(32)))
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('instance_id', uuid4().hex))
            self.owner_token = db.execute('SELECT value FROM settings WHERE key=?', ('owner_token',)).fetchone()[0]
            self.instance_id = db.execute('SELECT value FROM settings WHERE key=?', ('instance_id',)).fetchone()[0]
            # Additive migration: retain historical identities, names, URLs and records.
            db.execute("INSERT OR IGNORE INTO learners SELECT learner_id,learner,'{}',created FROM tasks")

    def event(self, db, learner_id, task_id, kind, detail=None, actor=None):
        db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)', (uuid4().hex, learner_id, task_id, kind, actor or self.instance_id + ':maintainer', json.dumps(detail or {}, ensure_ascii=False), now()))

    def save_learner(self, name, profile=None, learner_id=None, request_key=None):
        if not isinstance(name, str) or not 0 < len(name.strip()) <= 80:
            raise ValueError('学习者称呼：请填写1至80字')
        if learner_id is not None and not isinstance(learner_id, str):
            raise ValueError('学习者标识无效')
        if profile is None and learner_id is not None:
            profile = self.learner(learner_id)['profile']
        clean = validate_profile({} if profile is None else profile)
        if request_key is not None and (not isinstance(request_key, str) or not 0 < len(request_key) <= 128):
            raise ValueError('档案操作标识无效')
        fingerprint = hashlib.sha256(json.dumps([name.strip(), clean, learner_id], sort_keys=True).encode()).hexdigest()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if request_key is not None:
                previous = db.execute('SELECT * FROM profile_requests WHERE key=?', (request_key,)).fetchone()
                if previous:
                    if previous['fingerprint'] != fingerprint:
                        raise ValueError('档案操作已保存；修改内容请使用新的操作标识')
                    row = db.execute('SELECT * FROM learners WHERE id=?', (previous['learner_id'],)).fetchone()
                    return {**dict(row), 'profile': json.loads(row['profile'])}
            if learner_id is not None:
                if not db.execute('SELECT 1 FROM learners WHERE id=?', (learner_id,)).fetchone():
                    raise KeyError('学习者不存在于本实例')
                db.execute('UPDATE learners SET name=?,profile=? WHERE id=?', (name.strip(), json.dumps(clean), learner_id))
            else:
                learner_id = uuid4().hex
                db.execute('INSERT INTO learners VALUES (?,?,?,?)', (learner_id, name.strip(), json.dumps(clean), now()))
            self.event(db, learner_id, None, 'profile_saved')
            if request_key is not None:
                db.execute('INSERT INTO profile_requests VALUES (?,?,?)', (request_key, fingerprint, learner_id))
        return self.learner(learner_id)

    def learner(self, learner_id):
        if not isinstance(learner_id, str):
            raise ValueError('学习者标识无效')
        with self.db() as db:
            row = db.execute('SELECT * FROM learners WHERE id=?', (learner_id,)).fetchone()
        if not row:
            raise KeyError('学习者不存在于本实例')
        return {**dict(row), 'profile': json.loads(row['profile'])}

    def learners(self):
        with self.db() as db:
            rows = db.execute('SELECT * FROM learners ORDER BY created,id').fetchall()
        return [{**dict(row), 'profile': json.loads(row['profile'])} for row in rows]

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def authorize(self, token):
        if not isinstance(token, str) or not token or not token.isascii() or not hmac.compare_digest(token, self.owner_token):
            raise PermissionError('请先登录维护者入口')

    def create(self, learner, draft=None, request_key=None, learner_id=None):
        if not isinstance(learner, str) or not learner.strip() or len(learner) > 80:
            raise ValueError('学习者称呼：请填写1至80字')
        snapshot = validate_activity(prepare_activity() if draft is None else draft)
        if learner_id is not None and not isinstance(learner_id, str):
            raise ValueError('学习者标识无效')
        if request_key is not None and (not isinstance(request_key, str) or not 0 < len(request_key) <= 128):
            raise ValueError('创建操作标识无效')
        fingerprint = hashlib.sha256(json.dumps([learner.strip(), snapshot], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if learner_id is not None:
            fingerprint = hashlib.sha256((fingerprint + str(learner_id)).encode()).hexdigest()
        task = {'id': uuid4().hex, 'learner_id': learner_id or uuid4().hex, 'learner': learner.strip(), 'token': secrets.token_urlsafe(24), 'created': now()}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if request_key:
                previous = db.execute('SELECT * FROM task_requests WHERE key=?', (request_key,)).fetchone()
                if previous:
                    if previous['fingerprint'] != fingerprint:
                        raise ValueError('创建操作已保存；内容变化请使用新的操作标识')
                    saved = dict(db.execute('SELECT id,learner_id,learner,token,created FROM tasks WHERE id=?', (previous['task_id'],)).fetchone())
                    return self.receipt(saved, snapshot)
            if learner_id is not None:
                saved = db.execute('SELECT name FROM learners WHERE id=?', (learner_id,)).fetchone()
                if not saved:
                    raise KeyError('学习者不存在于本实例')
                if saved['name'] != learner.strip():
                    raise ValueError('学习者称呼与档案不符，请刷新后选择已有档案')
            else:
                db.execute('INSERT INTO learners VALUES (?,?,?,?)', (task['learner_id'], task['learner'], '{}', task['created']))
            db.execute('INSERT INTO tasks(id,learner_id,learner,token,snapshot,created) VALUES (?,?,?,?,?,?)', (task['id'], task['learner_id'], task['learner'], task['token'], json.dumps(snapshot, ensure_ascii=False), task['created']))
            if request_key:
                db.execute('INSERT INTO task_requests VALUES (?,?,?)', (request_key, fingerprint, task['id']))
            self.event(db, task['learner_id'], task['id'], 'activity_published', {'task_version': self.receipt(task, snapshot)['task_version']})
        return self.receipt(task, snapshot)

    def receipt(self, task, snapshot):
        return {**task, 'instance_id': self.instance_id, 'task_version': hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}

    def set_state(self, task_id, state):
        if state not in ('active', 'paused', 'archived'):
            raise ValueError('活动状态只能为active、paused或archived')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT learner_id,state FROM tasks WHERE id=?', (task_id,)).fetchone()
            if not row:
                raise KeyError('活动不存在')
            if row['state'] == 'archived' and state != 'archived':
                raise ValueError('已归档活动只读；继续学习请创建新活动')
            if row['state'] != state:
                db.execute('UPDATE tasks SET state=? WHERE id=?', (state, task_id))
                self.event(db, row['learner_id'], task_id, 'state_changed', {'from': row['state'], 'to': state})
        return {'task_id': task_id, 'state': state}

    def task(self, token):
        with self.db() as db:
            row = db.execute('SELECT * FROM tasks WHERE token=?', (token,)).fetchone()
        if row is None:
            raise KeyError('学习链接不存在')
        result = dict(row)
        result['snapshot'] = json.loads(result['snapshot'])
        return result

    def public_task(self, token):
        task = self.task(token)
        allowed = ('name', 'activity_title', 'instructions', 'criteria', 'next_step', 'material', 'mode', 'goal', 'deliverable')
        sources = [{k: source[k] for k in ('title', 'locator', 'version', 'verification_status') if k in source} for source in task['snapshot'].get('sources', [])]
        return {'learner': task['learner'], 'state': task['state'], 'activity': {**{k: task['snapshot'][k] for k in allowed if k in task['snapshot']}, 'rubric': task['snapshot'].get('rubric', []), 'sources': sources}, 'submissions': self.submissions(task['id'])}

    def submissions(self, task_id=None):
        with self.db() as db:
            rows = db.execute('SELECT * FROM submissions' + (' WHERE task_id=?' if task_id else '') + ' ORDER BY created', (task_id,) if task_id else ()).fetchall()
            history = db.execute('SELECT r.* FROM reviews r JOIN submissions s ON s.id=r.submission_id' + (' WHERE s.task_id=?' if task_id else '') + ' ORDER BY r.id', (task_id,) if task_id else ()).fetchall()
        reviews = {}
        for item in history:
            reviews.setdefault(item['submission_id'], []).append({'id': item['id'], 'created': item['created'], 'evaluation': json.loads(item['evaluation'])})
        return [{**dict(row), 'evaluation': json.loads(row['evaluation']), 'review_history': reviews.get(row['id'], [])} for row in rows]

    def submit(self, token, answer, request_key):
        task = self.task(token)
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 20000:
            raise ValueError('请填写1至20000字的提交内容')
        if not isinstance(request_key, str) or not request_key or len(request_key) > 128:
            raise ValueError('提交标识无效，请刷新页面后重试')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT * FROM submissions WHERE task_id=? AND request_key=?', (task['id'], request_key)).fetchone()
            if previous:
                if previous['answer'] != answer:
                    raise ValueError('这次提交已保存；修改内容请发起新一次提交')
                return {**dict(previous), 'evaluation': json.loads(previous['evaluation'])}
            state = db.execute('SELECT state FROM tasks WHERE id=?', (task['id'],)).fetchone()['state']
            if state != 'active':
                raise ValueError('活动已暂停或归档，暂不接受新提交；已有记录仍可查看')
            evaluation = evaluate_submission(task['snapshot'], answer)
            evaluation.update(evaluation_version=task['snapshot'].get('assessment_version', 'unversioned'), review_state='pending' if evaluation['status'] == 'pending' else 'automatic', reviewer_id=None if evaluation['status'] == 'pending' else self.instance_id + ':system')
            result = {'id': uuid4().hex, 'task_id': task['id'], 'request_key': request_key, 'answer': answer, 'evaluation': evaluation, 'created': now()}
            db.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?)', (result['id'], task['id'], request_key, answer, json.dumps(evaluation, ensure_ascii=False), result['created']))
            self.event(db, task['learner_id'], task['id'], 'evidence_submitted', {'submission_id': result['id']}, actor=task['learner_id'])
        return result

    def feedback(self, submission_id, comment, next_step, scores=None, judgement=None, request_key=None):
        if not all(isinstance(x, str) and 0 < len(x.strip()) <= 20000 for x in (comment, next_step)):
            raise ValueError('反馈和下一步均须填写1至20000字')
        if judgement not in (None, 'meets_criteria', 'needs_revision'):
            raise ValueError('judgement：只能为空、meets_criteria或needs_revision；已评阅不自动代表达标')
        if request_key is not None and (not isinstance(request_key, str) or not 0 < len(request_key) <= 128):
            raise ValueError('反馈操作标识无效')
        fingerprint = hashlib.sha256(json.dumps([submission_id, comment, next_step, scores, judgement], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        result = {'status': 'reviewed', 'comment': comment, 'next_step': next_step, 'correct': None, 'judgement': judgement, 'reviewer_id': self.instance_id + ':maintainer', 'review_state': 'confirmed', 'reviewed_at': now()}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if request_key is not None:
                previous = db.execute('SELECT * FROM feedback_requests WHERE key=?', (request_key,)).fetchone()
                if previous:
                    if previous['fingerprint'] != fingerprint:
                        raise ValueError('反馈已保存；修改内容请使用新的操作标识')
                    return json.loads(previous['result'])
            row = db.execute('SELECT t.snapshot,t.id,t.learner_id,t.state FROM submissions s JOIN tasks t ON s.task_id=t.id WHERE s.id=?', (submission_id,)).fetchone()
            if not row:
                raise KeyError('找不到这次提交')
            if row['state'] == 'archived':
                raise ValueError('已归档活动只读，不能新增反馈')
            result['evaluation_version'] = json.loads(row['snapshot']).get('assessment_version', 'unversioned')
            if scores is not None:
                rubric = json.loads(row['snapshot']).get('rubric', [])
                if not rubric or not isinstance(scores, list) or len(scores) != len(rubric):
                    raise ValueError('scores：须与此活动发布时的评价维度完全对应')
                verified = []
                for entry, rule in zip(scores, rubric):
                    if not isinstance(entry, dict) or entry.get('label') != rule['label'] or not valid_number(entry.get('score')) or not 0 <= entry['score'] <= rule['max_score']:
                        raise ValueError('scores：维度顺序须一致，得分须在0至该项满分之间')
                    verified.append({'label': rule['label'], 'score': entry['score'], 'max_score': rule['max_score']})
                result.update(scores=verified, total=sum(v['score'] for v in verified), max_total=sum(v['max_score'] for v in verified))
            db.execute('INSERT INTO reviews(submission_id,evaluation,created) VALUES (?,?,?)', (submission_id, json.dumps(result, ensure_ascii=False), now()))
            db.execute('UPDATE submissions SET evaluation=? WHERE id=?', (json.dumps(result, ensure_ascii=False), submission_id))
            if request_key is not None:
                db.execute('INSERT INTO feedback_requests VALUES (?,?,?)', (request_key, fingerprint, json.dumps(result)))
            self.event(db, row['learner_id'], row['id'], 'feedback_recorded', {'submission_id': submission_id, 'judgement': judgement})
        return result

    def verify_transfer(self, submission_id, context, independent):
        if not isinstance(context, str) or not 0 < len(context.strip()) <= 2000 or independent is not True:
            raise ValueError('独立迁移须填写新情境说明，并由维护者确认独立完成；不是自动能力判定')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT s.evaluation,t.id,t.learner_id,t.state FROM submissions s JOIN tasks t ON s.task_id=t.id WHERE s.id=?', (submission_id,)).fetchone()
            if not row:
                raise KeyError('找不到这次提交')
            if row['state'] == 'archived':
                raise ValueError('已归档活动只读')
            if json.loads(row['evaluation']).get('judgement') != 'meets_criteria':
                raise ValueError('先按公开依据确认本次作品达标，再核验独立迁移')
            detail = {'submission_id': submission_id, 'context': context.strip(), 'independent': True}
            existing = db.execute("SELECT detail FROM events WHERE learner_id=? AND kind='transfer_verified'", (row['learner_id'],)).fetchall()
            if not any(json.loads(item['detail']) == detail for item in existing):
                self.event(db, row['learner_id'], row['id'], 'transfer_verified', detail)
        return {'recorded': True, 'meaning': '维护者确认的一次新情境独立达标证据，不代表永久掌握'}

    def growth(self, learner_id):
        self.learner(learner_id)
        with self.db() as db:
            tasks = db.execute('SELECT id,state FROM tasks WHERE learner_id=?', (learner_id,)).fetchall()
            rows = db.execute('SELECT s.* FROM submissions s JOIN tasks t ON s.task_id=t.id WHERE t.learner_id=? ORDER BY s.created,s.id', (learner_id,)).fetchall()
            events = db.execute('SELECT * FROM events WHERE learner_id=? ORDER BY created,id', (learner_id,)).fetchall()
        # Count the latest submission of each activity, not an obsolete first draft.
        latest = {}
        states = {row['id']: row['state'] for row in tasks}
        for row in rows:
            latest[row['task_id']] = json.loads(row['evaluation'])
        transfers = {json.loads(e['detail'])['submission_id'] for e in events if e['kind'] == 'transfer_verified'}
        current_passed = {row['id'] for row in rows if json.loads(row['evaluation']).get('judgement') == 'meets_criteria'}
        return {'learner_id': learner_id, 'encountered': len(tasks), 'completed': len(latest), 'meets_criteria': sum(v.get('judgement') == 'meets_criteria' for v in latest.values()), 'independent_transfer': len(transfers & current_passed), 'open_activities': sum(s != 'archived' for s in states.values()), 'pending_submissions': sum(v['status'] == 'pending' and states[k] != 'archived' for k,v in latest.items()), 'needs_revision': sum(v.get('judgement') == 'needs_revision' and states[k] != 'archived' for k,v in latest.items()), 'events': [{**dict(e), 'detail': json.loads(e['detail'])} for e in events], 'meaning': '接触=已发布活动，完成=已有提交；达标与独立迁移各自需要明确证据；计数不是掌握度。'}

    def next_plan(self, learner_id):
        result = plan_next(self.learner(learner_id)['profile'], self.growth(learner_id))
        if not isinstance(result, dict) or any(not isinstance(result.get(k), str) or not 0 < len(result[k].strip()) <= limit for k,limit in [('action',80),('suggestion',20000)]):
            raise ValueError('app/strategy.py：plan_next须返回非空action（最多80字）和suggestion（最多20000字），动作名称由业务决定')
        return result

    def tasks(self):
        with self.db() as db:
            rows = db.execute('SELECT * FROM tasks ORDER BY created').fetchall()
        return [{k: row[k] for k in ('id', 'learner_id', 'learner', 'token', 'created', 'state')} | {'rubric': json.loads(row['snapshot']).get('rubric', [])} for row in rows]

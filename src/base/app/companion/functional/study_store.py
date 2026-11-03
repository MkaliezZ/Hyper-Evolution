"""Additive local storage, prepared-operation recovery and immutable versions."""
import json
from base.core import now
from base.app.companion.assets.references import digest

def initialize(runtime):
    with runtime.db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS companion_materials(id TEXT NOT NULL,revision INTEGER NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(id,revision));
        CREATE TABLE IF NOT EXISTS companion_previews(id TEXT PRIMARY KEY,body TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companion_assessments(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,submission_id TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companion_requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,prepared TEXT NOT NULL,result TEXT);
        ''')

def transact(runtime, request, prepare, apply):
    fingerprint=digest(request.model_dump())
    with runtime.db() as db:
        row=db.execute('SELECT * FROM companion_requests WHERE id=?',(request.request_id,)).fetchone()
    if row:
        if row['fingerprint']!=fingerprint:raise ValueError('操作标识已用于不同内容，请重新发起操作')
        if row['result']:return json.loads(row['result'])
        prepared=json.loads(row['prepared'])
    else:
        candidate=prepare()
        with runtime.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO companion_requests VALUES (?,?,?,NULL)',(request.request_id,fingerprint,json.dumps(candidate,ensure_ascii=False)))
            row=db.execute('SELECT * FROM companion_requests WHERE id=?',(request.request_id,)).fetchone()
        if row['fingerprint']!=fingerprint:raise ValueError('操作标识冲突')
        if row['result']:return json.loads(row['result'])
        prepared=json.loads(row['prepared'])
    result=apply(prepared)
    with runtime.db() as db:
        db.execute('UPDATE companion_requests SET result=? WHERE id=?',(json.dumps(result,ensure_ascii=False),request.request_id))
    return result

def ledger(runtime, task_id):
    with runtime.db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_assessments'").fetchone():return []
        rows=db.execute('SELECT body FROM companion_assessments WHERE task_id=? ORDER BY created,id',(task_id,)).fetchall()
    return [json.loads(r['body']) for r in rows]

def append_assessment(runtime,record):
    with runtime.db() as db:
        db.execute('INSERT OR IGNORE INTO companion_assessments VALUES (?,?,?,?,?)',
          (record['id'],record['task_id'],record['submission_id'],json.dumps(record,ensure_ascii=False),record['created']))

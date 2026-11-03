"""Three additive, teacher-private tables; existing BASE and v1-v5 records unchanged."""
import json

TABLES={'prereview':'companion_prereviews','draft':'companion_review_drafts','publication':'companion_review_publications'}
def initialize(runtime):
    from base.app.companion.functional.study_store import initialize as previous
    previous(runtime)
    with runtime.db() as db:
        for table in TABLES.values():db.execute('CREATE TABLE IF NOT EXISTS '+table+'(id TEXT NOT NULL,revision INTEGER NOT NULL,peer_id TEXT NOT NULL,task_id TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(id,revision))')

def exists(runtime,kind):
    with runtime.db() as db:return bool(db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(TABLES[kind],)).fetchone())

def get(runtime,kind,id,revision=None):
    if not exists(runtime,kind):raise KeyError('评阅记录尚不存在')
    with runtime.db() as db:row=db.execute('SELECT body FROM '+TABLES[kind]+' WHERE id=? '+('AND revision=? ' if revision else '')+'ORDER BY revision DESC LIMIT 1',(id,revision) if revision else (id,)).fetchone()
    if not row:raise KeyError('评阅记录尚不存在')
    return json.loads(row['body'])

def rows(runtime,kind,peer_id,task_id):
    if not exists(runtime,kind):return []
    with runtime.db() as db:return [json.loads(r['body']) for r in db.execute('SELECT body FROM '+TABLES[kind]+' t WHERE peer_id=? AND task_id=? AND revision=(SELECT MAX(revision) FROM '+TABLES[kind]+' WHERE id=t.id) ORDER BY rowid DESC',(peer_id,task_id))]

def save(runtime,kind,value):
    with runtime.db() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT body FROM '+TABLES[kind]+' WHERE id=? AND revision=?',(value['id'],value['revision'])).fetchone()
        if old:
            if json.loads(old['body'])!=value:raise ValueError('不可变评阅版本冲突')
            return value
        head=db.execute('SELECT MAX(revision) FROM '+TABLES[kind]+' WHERE id=?',(value['id'],)).fetchone()[0]
        if value['revision']!=(head or 0)+1:raise ValueError('评阅草稿已在其他窗口更新，请刷新')
        db.execute('INSERT INTO '+TABLES[kind]+' VALUES (?,?,?,?,?)',(value['id'],value['revision'],value['peer_id'],value['task_id'],json.dumps(value,ensure_ascii=False)))
    return value

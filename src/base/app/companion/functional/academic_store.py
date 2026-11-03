"""One additive append-only entity store; immutable versions and compare-and-save."""
import json
from base.app.companion.functional.study_store import initialize as previous

def initialize(runtime):
    previous(runtime)
    with runtime.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS companion_academic_records(kind TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,peer_id TEXT,body TEXT NOT NULL,PRIMARY KEY(kind,id,revision))')

def get(runtime,kind,id,revision=None):
    initialize(runtime)
    with runtime.db() as db:row=db.execute('SELECT body FROM companion_academic_records WHERE kind=? AND id=? '+('AND revision=? ' if revision else '')+'ORDER BY revision DESC LIMIT 1',(kind,id,revision) if revision else (kind,id)).fetchone()
    if not row:raise KeyError('这份学科记录不存在')
    return json.loads(row['body'])

def rows(runtime,kind,peer_id=None):
    initialize(runtime)
    with runtime.db() as db:
        raw=db.execute('SELECT body FROM companion_academic_records a WHERE kind=? AND revision=(SELECT MAX(revision) FROM companion_academic_records WHERE kind=a.kind AND id=a.id) ORDER BY rowid DESC',(kind,)).fetchall()
    values=[json.loads(x['body']) for x in raw]
    return [x for x in values if peer_id is None or x.get('peer_id')==peer_id]

def save(runtime,kind,value):
    initialize(runtime)
    with runtime.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT body FROM companion_academic_records WHERE kind=? AND id=? AND revision=?',(kind,value['id'],value['revision'])).fetchone()
        if row:
            if json.loads(row['body'])!=value:raise ValueError('不可变学科版本发生冲突')
            return value
        head=db.execute('SELECT MAX(revision) FROM companion_academic_records WHERE kind=? AND id=?',(kind,value['id'])).fetchone()[0]
        if value['revision']!=(head or 0)+1:raise ValueError('学科记录已被更新，请重新读取版本')
        db.execute('INSERT INTO companion_academic_records VALUES (?,?,?,?,?)',(kind,value['id'],value['revision'],value.get('peer_id'),json.dumps(value,ensure_ascii=False)))
    return value

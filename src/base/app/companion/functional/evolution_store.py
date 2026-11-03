"""Additive v5 immutable local records; no production BASE schema is rewritten."""
import json
TABLES={'path':'companion_path_versions','path_preview':'companion_path_previews','writing':'companion_writing_versions',
        'suggestion':'companion_writing_suggestions','writing_preview':'companion_writing_previews','receipt':'companion_writing_receipts',
        'method':'companion_method_candidates','method_review':'companion_method_reviews','method_release':'companion_method_releases'}

def initialize(runtime):
    from base.app.companion.functional.study_store import initialize as previous
    previous(runtime)
    with runtime.db() as db:
        for table in TABLES.values():db.execute('CREATE TABLE IF NOT EXISTS '+table+'(id TEXT NOT NULL,revision INTEGER NOT NULL,scope TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(id,revision))')

def exists(runtime,kind):
    with runtime.db() as db:return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(TABLES[kind],)).fetchone())

def rows(runtime,kind,scope=None,id=None):
    if not exists(runtime,kind):return []
    conditions=['revision=(SELECT MAX(revision) FROM '+TABLES[kind]+' WHERE id=t.id)'];values=[]
    if scope is not None:conditions.append('scope=?');values.append(scope)
    if id is not None:conditions.append('id=?');values.append(id)
    with runtime.db() as db:return [json.loads(r['body']) for r in db.execute('SELECT body FROM '+TABLES[kind]+' t WHERE '+' AND '.join(conditions)+' ORDER BY rowid DESC',values)]

def get(runtime,kind,id,revision=None):
    if not exists(runtime,kind):raise KeyError('记录尚不存在')
    with runtime.db() as db:
        row=db.execute('SELECT body FROM '+TABLES[kind]+' WHERE id=? '+('AND revision=? ' if revision else '')+'ORDER BY revision DESC LIMIT 1',
            (id,revision) if revision else (id,)).fetchone()
    if not row:raise KeyError('记录尚不存在')
    return json.loads(row['body'])

def versions(runtime,kind,id):
    with runtime.db() as db:return [json.loads(r['body']) for r in db.execute('SELECT body FROM '+TABLES[kind]+' WHERE id=? ORDER BY revision',(id,))]

def save(runtime,kind,value,remote=False):
    with runtime.db() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT body FROM '+TABLES[kind]+' WHERE id=? AND revision=?',(value['id'],value['revision'])).fetchone()
        if old:
            saved=json.loads(old['body'])
            if saved['scope']!=value['scope'] or saved.get('content_hash')!=value.get('content_hash'):raise ValueError('不可变版本冲突')
            return saved
        head=db.execute('SELECT MAX(revision) FROM '+TABLES[kind]+' WHERE id=?',(value['id'],)).fetchone()[0]
        if not remote and value['revision']!=(head or 0)+1:raise ValueError('版本已变化，请重新预览')
        owners=db.execute('SELECT scope FROM '+TABLES[kind]+' WHERE id=? LIMIT 1',(value['id'],)).fetchone()
        if owners and owners['scope']!=value['scope']:raise PermissionError('记录不属于当前身份范围')
        if kind=='method_release':
            previous=[json.loads(row['body']) for row in db.execute('SELECT body FROM '+TABLES[kind]+' WHERE scope=?',(value['scope'],))]
            generation=max([v['artifact']['version'] for v in previous if v['candidate_id']==value['candidate_id']],default=0)
            if value['artifact']['version']!=generation+1:raise ValueError('方法发布版本已变化，请重新检查最新审阅并发布')
        db.execute('INSERT INTO '+TABLES[kind]+' VALUES (?,?,?,?)',(value['id'],value['revision'],value['scope'],json.dumps(value,ensure_ascii=False)))
    return value

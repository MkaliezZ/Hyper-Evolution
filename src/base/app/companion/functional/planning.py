"""Shared local/MCP growth planning with explicit signed sharing and immutable versions."""
import json
from uuid import uuid4
from base.core import now
from base.app.companion.assets.planning import seal,verify
from base.app.companion.assets.references import digest
from base.app.companion.aesthetic.planning import guide
from base.app.companion.functional.planning_contracts import PlanningRequest,PlanningResult,PAYLOADS,Content
from base.app.companion.functional.retrieval_sources import scope_key
from base.app.companion.functional.evidence import evidence_view
from base.app.companion.functional import study_store

TABLE='companion_growth_plans'


def initialize(runtime):
    study_store.initialize(runtime)
    with runtime.db() as db:
        db.execute('CREATE TABLE IF NOT EXISTS '+TABLE+'(id TEXT NOT NULL,revision INTEGER NOT NULL,scope TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(id,revision))')


def scope(runtime,peer_id=None):
    if runtime.role=='teacher' and not peer_id:raise ValueError('请先选择一位已配对学生')
    return scope_key(runtime,peer_id)


def rows(runtime,key):
    with runtime.db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(TABLE,)).fetchone():return []
        return [json.loads(r['body']) for r in db.execute('SELECT body FROM '+TABLE+' t WHERE scope=? AND revision=(SELECT MAX(revision) FROM '+TABLE+' WHERE id=t.id) ORDER BY rowid DESC',(key,))]


def agent_context(runtime,peer_id=None):
    key=scope(runtime,peer_id);result=[]
    for value in rows(runtime,key):
        try:active_record(runtime,value,key)
        except PermissionError:continue
        content=value['content']
        result.append({'plan_id':value['id'],'revision':value['revision'],'author_role':value['author_role'],
            'stage_declaration':content['stage'],'current_situation':content['current_situation'][:400],
            'goal':content['goal'][:300],'question':content['question'][:200],
            'requirements':[{k:v[:100] for k,v in item.items() if k in ['requirement','current_evidence','gap','next_action','completion_standard']} for item in content['requirements'][:2]],
            'content_hash':value['content_hash']})
        if len(result)==2:break
    return result


def active_record(runtime,value,key):
    if value['scope']!=key:raise PermissionError('这份规划不属于当前学生')
    if value['owner_device']!=runtime.identity.id:runtime.peer(value['owner_device'])
    return verify(value)


def read(runtime,id,key):
    with runtime.db() as db:row=db.execute('SELECT body FROM '+TABLE+' WHERE id=? ORDER BY revision DESC LIMIT 1',(id,)).fetchone()
    if not row:raise KeyError('找不到这份成长规划')
    return active_record(runtime,json.loads(row['body']),key)


def insert(runtime,value,expected=None):
    with runtime.db() as db:
        db.execute('BEGIN IMMEDIATE')
        same=db.execute('SELECT body FROM '+TABLE+' WHERE id=? AND revision=?',(value['id'],value['revision'])).fetchone()
        if same:
            previous=json.loads(same['body'])
            if previous['content_hash']!=value['content_hash'] or previous['scope']!=value['scope']:raise ValueError('规划版本冲突')
            return previous
        head=db.execute('SELECT body FROM '+TABLE+' WHERE id=? ORDER BY revision DESC LIMIT 1',(value['id'],)).fetchone()
        old=json.loads(head['body']) if head else None
        if old and (old['owner_device']!=value['owner_device'] or old['scope']!=value['scope']):raise PermissionError('规划作者不匹配')
        if expected is not None and (old['revision'] if old else 0)!=expected:raise ValueError('规划已更新，请重新打开后修改')
        db.execute('INSERT INTO '+TABLE+' VALUES (?,?,?,?)',(value['id'],value['revision'],value['scope'],json.dumps(value,ensure_ascii=False)))
    return value


def evidence(runtime,peer_id):
    return evidence_view(runtime,peer_id,None,10,2)


def invoke(runtime,raw):
    r=PlanningRequest.model_validate(raw)
    p=PAYLOADS[r.operation].model_validate(r.payload) if r.operation in PAYLOADS else None
    if p is None and r.payload:raise ValueError('本次读取不需要额外参数')
    key=scope(runtime,r.peer_id);initialize(runtime)
    if r.operation=='planning.context':
        view=evidence(runtime,r.peer_id)
        values=[]
        for value in rows(runtime,key):
            try:values.append(active_record(runtime,value,key))
            except PermissionError:continue
        tasks=view['tasks']
        data={'plans':values,'tasks':[{'id':t['id'],'title':t['material']['title'],'attempts':len(t['attempts']),
              'feedback':sum(bool(a.get('assessment_authority') in ['signed_teacher_review','local_maintainer_review']) for a in t['attempts'])} for t in tasks],
              'coverage':view['coverage'],'policy':guide({'stage':'exploring'}),
              'state_counts':{'tasks':len(tasks),'submitted':sum(bool(t['attempts']) for t in tasks),
                    'with_teacher_feedback':sum(any(a.get('assessment_authority') in ['signed_teacher_review','local_maintainer_review'] for a in t['attempts']) for t in tasks)}}
    elif r.operation=='planning.read':
        value=read(runtime,p.id,key);data={'plan':value,'policy':guide(value['content'],len(value['evidence_refs']))}
    else:
        def prepare():
            if r.operation=='planning.save':
                item=p
                old=read(runtime,item.id,key) if item.id else None
                if old and old['owner_device']!=runtime.identity.id:raise PermissionError('收到的建议只读，请另存自己的规划')
                if (old['revision'] if old else 0)!=item.expected_revision:raise ValueError('规划版本已变化，请重新打开')
                view=evidence(runtime,r.peer_id);available={t['id']:t for t in view['tasks']}
                if any(tid not in available for tid in item.task_ids):raise PermissionError('作品不在当前学生的可用范围内')
                refs=[available[tid]['snapshot_ref'] for tid in item.task_ids]
                value=seal({'id':item.id or uuid4().hex,'revision':item.expected_revision+1,'scope':key,
                    'owner_device':runtime.identity.id,'subject_device':r.peer_id if runtime.role=='teacher' else runtime.identity.id,
                    'author_role':runtime.role,'content':item.content.model_dump(mode='json'),'evidence_refs':refs,
                    'created':now(),'parent_hash':old['content_hash'] if old else None,'signature_verified':False})
                return {'record':value}
            return p.model_dump(mode='json')
        def apply(payload):
            if r.operation=='planning.save':
                value=payload['record']
                value=insert(runtime,value,p.expected_revision)
                refs=value['evidence_refs']
                return {'plan':value,'policy':guide(value['content'],len(refs))}
            item=PAYLOADS[r.operation].model_validate(payload)
            value=read(runtime,item.id,key)
            if value['owner_device']!=runtime.identity.id:raise PermissionError('只能分享自己保存的规划')
            if value['revision']!=item.expected_revision or value['content_hash']!=item.content_hash:raise ValueError('规划已更新，请先查看最新版')
            receiver=r.peer_id if runtime.role=='teacher' else item.receiver_id
            peer=runtime.peer(receiver)
            if peer['role']!=('student' if runtime.role=='teacher' else 'teacher'):raise PermissionError('请选择对应的师生配对设备')
            if runtime.role=='teacher' and value['subject_device']!=receiver:raise PermissionError('规划不属于这位学生')
            if runtime.config('peer-planning:'+receiver)!='growth-planning.v1':raise ValueError('对方需更新到支持投石问路的版本，再重新连接')
            shared={k:v for k,v in value.items() if k not in ['scope','signature_verified']}
            event='growth-'+digest([r.request_id,value['id'],receiver])
            runtime.queue(receiver,'growth.plan',{'plan':shared},event_id=event)
            return {'id':value['id'],'revision':value['revision'],'delivery':'queued_for_peer'}
        data=study_store.transact(runtime,r,prepare,apply)
    return PlanningResult(request_id=r.request_id,operation=r.operation,data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'policy_id':'learning.growth_orientation',
        'policy_version':'1.0.0','scope':key,'subject':getattr(runtime,'workspace_subject',None)}).model_dump(mode='json')


def receive(runtime,peer,payload):
    raw=payload.get('plan',{})
    if not isinstance(raw,dict) or len(json.dumps(raw,ensure_ascii=False))>50000:raise ValueError('成长规划格式无效或过大')
    required={'id','revision','owner_device','subject_device','author_role','content','evidence_refs','created','parent_hash','content_hash'}
    if set(raw)!=required:raise ValueError('成长规划字段无效')
    import re
    if not isinstance(raw['id'],str) or not re.fullmatch('[a-f0-9]{32}',raw['id']) or type(raw['revision']) is not int or not 1<=raw['revision']<=10000:raise ValueError('成长规划标识无效')
    if raw['owner_device']!=peer['id'] or raw['author_role']!=peer['role']:raise PermissionError('成长规划作者不匹配')
    if runtime.role=='teacher':
        if peer['role']!='student' or raw['subject_device']!=peer['id']:raise PermissionError('学生只能分享自己的成长规划')
        key=scope(runtime,peer['id'])
    else:
        runtime.require_role('student')
        if peer['role']!='teacher' or raw['subject_device']!=runtime.identity.id:raise PermissionError('老师建议的学生不匹配')
        key='self'
    Content.model_validate(raw['content'])
    if not isinstance(raw['evidence_refs'],list) or len(raw['evidence_refs'])>10:raise ValueError('成长证据格式无效')
    verify(raw);initialize(runtime)
    return insert(runtime,{**raw,'scope':key,'signature_verified':True})

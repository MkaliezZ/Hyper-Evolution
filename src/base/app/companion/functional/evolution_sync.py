"""Typed extensions on existing signed task/submission events; older fields remain valid."""
import json
from base.app.companion.assets.references import digest
from base.app.companion.assets.changes import validate_writing_history,validate_history_ref,apply_suggestions
from base.app.companion.functional import evolution_store as store
from base.app.companion.functional.evolution_contracts import PathContent,Edit
from base.app.companion.functional.study import authorized_task

def capture_history(runtime,task_id,history,text,owner_device,scope):
    from base.app.companion.functional.evolution import seal
    history=validate_writing_history(history,text);store.initialize(runtime)
    checksum=digest(history);id='history-'+digest(task_id+':'+owner_device+':'+checksum)
    value=seal({'id':id,'revision':1,'scope':scope,'created':history['versions'][-1]['created'],
        'task_id':task_id,'owner_device':owner_device,'subject_device':owner_device,'history':history,'history_hash':checksum})
    store.save(runtime,'receipt',value)
    return {'id':id,'hash':checksum,'document_id':history['document_id'],'revision':history['versions'][-1]['revision']}

def read_history(runtime,task_id,history_id,peer_id=None):
    from base.app.companion.functional.retrieval_sources import scope_key
    task=authorized_task(runtime,task_id,peer_id)
    refs=[a['answer'].get('writing_history_ref') for a in task.get('attempts',[])]
    ref=next((r for r in refs if isinstance(r,dict) and r.get('id')==history_id),None)
    if not ref:raise PermissionError('该历史引用不属于这份已提交作品')
    validate_history_ref(ref);value=store.get(runtime,'receipt',history_id)
    if value['scope']!=scope_key(runtime,peer_id) or value['task_id']!=task_id or value['history_hash']!=ref['hash']:
        raise PermissionError('写作历史不属于当前身份范围')
    text=next(a['answer']['text'] for a in task['attempts'] if a['answer'].get('writing_history_ref')==ref)
    return {'history':validate_writing_history(value['history'],text),'source_ref':ref,'device_declaration_only':True}

def task_extensions(runtime,peer_id,task_id):
    paths=[];suggestions=[]
    if store.exists(runtime,'path'):
        for p in store.rows(runtime,'path','peer:'+peer_id):
            published=runtime.config('path-published:'+p['id'],{})
            if published and task_id in published['task_ids']:
                value=store.get(runtime,'path',p['id'],published['revision']);paths.append({k:v for k,v in value.items() if k!='scope'})
    if store.exists(runtime,'suggestion'):
        for s in store.rows(runtime,'suggestion','peer:'+peer_id):
            if s.get('task_id')==task_id and runtime.config('writing-shared:'+s['id'],False):suggestions.append({k:v for k,v in s.items() if k!='scope'})
    if len(paths)>20 or len(suggestions)>20:raise ValueError('本任务同步的计划或建议过多，请分开关联任务')
    return {'companion_paths':paths,'companion_writing_suggestions':suggestions}

def accept_extensions(runtime,peer_id,task,event_id):
    from base.app.companion.functional.evolution import seal
    paths=task.get('companion_paths',[]);suggestions=task.get('companion_writing_suggestions',[])
    if not isinstance(paths,list) or not isinstance(suggestions,list) or len(paths)>20 or len(suggestions)>20:raise ValueError('任务扩展格式无效')
    checked=[]
    path_fields={'id','revision','created','owner_device','subject_device','title','goal','steps','task_ids','reason','parent_hash','changes','runtime_policy','mastery','content_hash'}
    suggestion_fields={'id','revision','created','owner_device','subject_device','document_id','task_id','submission_id','base_revision','base_text_hash','edits','contributor','meaning','content_hash'}
    for value in paths+suggestions:
        if not isinstance(value,dict) or value.get('owner_device')!=peer_id or value.get('subject_device')!=runtime.identity.id:
            raise PermissionError('任务扩展主体不匹配')
        if not isinstance(value.get('id'),str) or not 1<=len(value['id'])<=80 or not isinstance(value.get('revision'),int) or not 1<=value['revision']<=100000:
            raise ValueError('任务扩展标识无效')
        if value.get('content_hash')!=seal(value)['content_hash']:raise ValueError('任务扩展内容校验失败')
    for value in paths:
        if set(value)!=path_fields:raise ValueError('计划快照字段无效')
        PathContent.model_validate({k:value[k] for k in ['title','goal','steps','task_ids','reason']})
        if len(json.dumps(value,ensure_ascii=False))>150000:raise ValueError('计划快照过大')
        checked.append({**value,'scope':'remote:'+peer_id,'authorization_anchor':task['id'],
            'received_event_id':event_id,'signature_verified':True})
    for value in suggestions:
        if set(value)!=suggestion_fields or value['contributor']!='teacher_suggestion' or value['task_id']!=task['id']:raise ValueError('教师建议字段无效')
        attempt=next((a for a in task['attempts'] if a['id']==value['submission_id']),None)
        if not attempt or digest(attempt['answer'].get('text',''))!=value['base_text_hash']:raise ValueError('教师建议来源不匹配')
        if not isinstance(value['edits'],list) or not 1<=len(value['edits'])<=6:raise ValueError('教师建议数量无效')
        edits=[Edit.model_validate(e).model_dump() for e in value['edits']];apply_suggestions(attempt['answer']['text'],edits)
    if checked:
        store.initialize(runtime)
        for value in checked:store.save(runtime,'path',value,remote=True)

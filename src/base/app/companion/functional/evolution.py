"""v5 Harness: explicit plan changes and optional, attributable writing revision."""
import json
from uuid import uuid4
from base.core import now
from base.app.companion.assets.references import digest
from base.app.companion.assets.changes import text_changes,plan_changes,apply_suggestions,validate_writing_history
from base.app.companion.aesthetic.engine import compose
from base.app.companion.functional.evolution_contracts import EvolutionRequest,EvolutionResult,PAYLOADS,PathContent
from base.app.companion.functional import evolution_store as store
from base.app.companion.functional.retrieval_sources import scope_key
from base.app.companion.functional.study import authorized_task
from base.app.companion.functional.study_store import transact

LOCAL_META={'scope','content_hash','received_event_id','signature_verified','authorization_anchor'}
def seal(value):return {**value,'content_hash':digest({k:v for k,v in value.items() if k not in LOCAL_META})}

def access(runtime,kind,id,peer_id=None,revision=None):
    selected=scope_key(runtime,peer_id);value=store.get(runtime,kind,id,revision)
    if value['scope'].startswith('remote:'):
        runtime.require_role('student');sender=value['scope'].removeprefix('remote:');runtime.peer(sender)
        if value.get('subject_device')!=runtime.identity.id or value.get('owner_device')!=sender:raise PermissionError('外部记录主体不匹配')
        task=authorized_task(runtime,value['authorization_anchor'])
        if task.get('peer_id')!=sender:raise PermissionError('外部记录来源不匹配')
    elif value['scope']!=selected:raise PermissionError('记录不属于当前身份范围')
    if value.get('task_id'):authorized_task(runtime,value['task_id'],peer_id)
    if kind=='path':
        for tid in value['task_ids']:
            try:authorized_task(runtime,tid,peer_id)
            except PermissionError:
                if not value['scope'].startswith('remote:'):raise
    return value

def require_edit(runtime,value):
    if value['owner_device']!=runtime.identity.id or value['scope'].startswith('remote:'):raise PermissionError('老师的安排只读；可另建自己的安排，不能修改老师版本')

def subject_device(runtime,peer_id):
    return runtime.peer(peer_id)['id'] if runtime.role=='teacher' and peer_id else runtime.identity.id

def policy(runtime,goal,task_ids,peer_id=None,method='reflect',draft=None,minutes=10):
    evidence=[];sources=[]
    for tid in task_ids:
        task=authorized_task(runtime,tid,peer_id)
        evidence.extend({'task_id':tid,'submission_id':a['id'],'answer_hash':digest(a['answer'])} for a in task.get('attempts',[])[-1:])
        sources.append({'task_id':tid,'source_hash':digest(task['pack'])})
    material={'kind':'text' if draft is not None or sources else 'none','verified':draft is not None or bool(sources),
        'ref':{'kind':'current_declared_draft','text_hash':digest(draft)} if draft is not None else {'tasks':sources} if sources else None}
    return compose({'goal':goal,'method':method,'scenario':'general' if method=='reflect' else 'writing',
        'material':material,'evidence':evidence,'minutes':minutes})

def checked_head(runtime,kind,value,peer_id,expected):
    head=access(runtime,kind,value['id'],peer_id)
    require_edit(runtime,head)
    if head['revision']!=expected:raise ValueError('版本已变化，请重新打开并预览差异')
    return head

def writing_suggestions(runtime,document,peer_id=None):
    candidates=store.rows(runtime,'suggestion',document['scope'])
    result=[s for s in candidates if s['document_id']==document['id']]
    if runtime.role=='student' and document.get('task_id'):
        task=authorized_task(runtime,document['task_id'])
        result+=task.get('companion_writing_suggestions',[])
    return [{**s,'current_text':s['base_text_hash']==document['text_hash']} for s in result]

def selected_suggestions(runtime,document,ids,peer_id=None):
    available={s['id']:s for s in writing_suggestions(runtime,document,peer_id)};selected=[]
    for id in ids:
        if id not in available or not available[id]['current_text']:raise ValueError('建议已过期或不属于当前作品；请重新准备或手动参考')
        selected.append(available[id])
    return selected

def public_history(runtime,document):
    history=store.versions(runtime,'writing',document['id']);truncated=len(history)>25
    if truncated:history=[history[0]]+history[-24:]
    fields=['revision','text','text_hash','parent_hash','contribution','contribution_note','additional_help','suggestion_refs','changes','created']
    return validate_writing_history({'document_id':document['id'],'title':document['title'],
        'versions':[{k:v[k] for k in fields} for v in history],'truncated':truncated},document['text'])

def publish_path(runtime,path,peer_id,event_key):
    runtime.require_role('teacher');require_edit(runtime,path);runtime.peer(peer_id)
    if path['subject_device']!=peer_id:raise PermissionError('计划不属于这位学生')
    old=runtime.config('path-published:'+path['id'],{})
    anchors=list(dict.fromkeys(path['task_ids']+old.get('task_ids',[])))
    if not anchors:raise ValueError('先关联至少一份已布置任务，才能通过现有签名通道同步安排')
    for tid in anchors:authorized_task(runtime,tid,peer_id)
    runtime.save_config('path-published:'+path['id'],{'revision':path['revision'],'task_ids':anchors})
    for tid in anchors:runtime.queue_task_update(peer_id,tid,event_id='path-'+digest(event_key+':'+tid))
    return {'path_id':path['id'],'revision':path['revision'],'delivery':'queued_for_peer','task_ids':anchors}

def invoke(runtime,raw):
    if runtime.role not in ['student','teacher']:raise PermissionError('请先设置本机身份')
    try:
        r=EvolutionRequest.model_validate(raw);p=PAYLOADS[r.operation].model_validate(r.payload) if r.operation in PAYLOADS else None
        if p is None and r.payload:raise ValueError()
    except ValueError:raise ValueError('v5 请求格式无效，请核对目标、版本、差异和必填项') from None
    selected=scope_key(runtime,r.peer_id);store.initialize(runtime)
    if r.operation.startswith('method.'):
        from base.app.companion.functional.method_assets import invoke_method
        return invoke_method(runtime,r,p)
    is_path=r.operation.startswith('path.')
    if is_path and runtime.role=='teacher' and not r.peer_id and r.operation not in ['path.list']:raise ValueError('请先选择已配对学生')
    original=None;preview=None;suggestion=None
    if hasattr(p,'path_id'):original=access(runtime,'path',p.path_id,r.peer_id,getattr(p,'revision',None))
    if hasattr(p,'document_id'):original=access(runtime,'writing',p.document_id,r.peer_id,getattr(p,'revision',None))
    if hasattr(p,'preview_id'):
        preview=store.get(runtime,'path_preview' if is_path else 'writing_preview',p.preview_id)
        original=access(runtime,'path' if is_path else 'writing',preview['parent_id'],r.peer_id)
        if preview['scope']!=selected:raise PermissionError('预览不属于当前身份范围')
    if hasattr(p,'suggestion_id'):
        suggestion=store.get(runtime,'suggestion',p.suggestion_id)
        original=access(runtime,'writing',suggestion['document_id'],r.peer_id)
        if suggestion['scope']!=selected:raise PermissionError('建议不属于当前范围')
    writes=r.operation in ['path.create','path.preview','path.confirm','path.publish','writing.create','writing.suggest',
        'writing.share_suggestion','writing.preview','writing.confirm','writing.submit']
    if writes and original:require_edit(runtime,original)
    if hasattr(p,'task_id') and p.task_id:authorized_task(runtime,p.task_id,r.peer_id)
    def common(id,revision=1):return {'id':id,'revision':revision,'scope':selected,'created':now(),
        'owner_device':runtime.identity.id,'subject_device':subject_device(runtime,r.peer_id)}
    def prepare():
        if r.operation=='path.create':
            for tid in p.task_ids:authorized_task(runtime,tid,r.peer_id)
            return seal({**common('path-'+uuid4().hex),**p.model_dump(),'parent_hash':None,'changes':[],
                'runtime_policy':policy(runtime,p.goal,p.task_ids,r.peer_id,minutes=sum(s.minutes for s in p.steps)),'mastery':'not_inferred'})
        if r.operation=='path.preview':
            old=checked_head(runtime,'path',original,r.peer_id,p.expected_revision)
            for tid in p.task_ids:authorized_task(runtime,tid,r.peer_id)
            content=p.model_dump(exclude={'path_id','expected_revision'});changes=plan_changes(old,content)
            if not changes:raise ValueError('安排没有变化，无需生成新版本')
            return seal({**common('path-preview-'+uuid4().hex),'parent_id':old['id'],'parent_revision':old['revision'],
                'parent_hash':old['content_hash'],'proposed':content,'changes':changes,
                'runtime_policy':policy(runtime,p.goal,p.task_ids,r.peer_id,minutes=sum(s.minutes for s in p.steps)),'kind':'path'})
        if r.operation in ['path.confirm','writing.confirm']:
            kind='path' if is_path else 'writing';old=checked_head(runtime,kind,original,r.peer_id,p.expected_revision)
            if preview['content_hash']!=p.preview_hash or preview['parent_revision']!=old['revision'] or preview['parent_hash']!=old['content_hash']:
                raise ValueError('预览与当前版本不匹配，请重新检查差异')
            return seal({**old,**preview['proposed'],'revision':old['revision']+1,'created':now(),'parent_hash':old['content_hash'] if is_path else old['text_hash'],
                'changes':preview['changes'],'runtime_policy':preview['runtime_policy']})
        if r.operation=='path.publish':
            old=checked_head(runtime,'path',original,r.peer_id,p.expected_revision)
            runtime.require_role('teacher');return old
        if r.operation=='writing.create':
            text=p.text;contribution='learner_declared' if runtime.role=='student' else 'teacher_proposed_revision';source_submission=None
            if p.task_id and (runtime.role=='teacher' or p.submission_id):
                task=authorized_task(runtime,p.task_id,r.peer_id)
                attempts=[a for a in task.get('attempts',[]) if not p.submission_id or a['id']==p.submission_id]
                if not attempts:raise ValueError('先收到实际作品，才能基于提交准备写作建议')
                a=attempts[-1];actual=a['answer'].get('text','')
                if text and text!=actual:raise ValueError('不能把改写内容冒充原始提交')
                text=actual;source_submission=a['id'];contribution='submitted_work_snapshot'
            if not text.strip():raise ValueError('先写下首稿，或选择一份已有文字作品')
            if not p.title.strip() or not p.goal.strip():raise ValueError('请写明作品标题和目标')
            return seal({**common('writing-'+uuid4().hex),'title':p.title,'goal':p.goal,'task_id':p.task_id,'submission_id':source_submission,
                'text':text,'text_hash':digest(text),'parent_hash':None,'contribution':contribution,'contribution_note':'初始稿来源为当前身份声明或实际提交快照',
                'additional_help':p.additional_help,'suggestion_refs':[],'changes':[],
                'runtime_policy':policy(runtime,p.goal,[p.task_id] if p.task_id else [],r.peer_id,'apply',draft=text),'mastery':'not_inferred'})
        if r.operation=='writing.suggest':
            old=checked_head(runtime,'writing',original,r.peer_id,p.expected_revision)
            if p.contributor=='teacher_suggestion':runtime.require_role('teacher')
            edits=[e.model_dump() for e in p.edits];apply_suggestions(old['text'],edits)
            return seal({**common('suggestion-'+uuid4().hex),'document_id':old['id'],'task_id':old.get('task_id'),
                'submission_id':old.get('submission_id'),'base_revision':old['revision'],'base_text_hash':old['text_hash'],
                'edits':edits,'contributor':p.contributor,'meaning':'候选改动，未修改首稿或教师判断'})
        if r.operation=='writing.share_suggestion':
            runtime.require_role('teacher')
            if suggestion['contributor']!='teacher_suggestion' or not suggestion.get('task_id') or not suggestion.get('submission_id'):
                raise ValueError('仅可分享基于这位学生实际提交的教师建议')
            task=authorized_task(runtime,suggestion['task_id'],r.peer_id)
            attempt=next((a for a in task['attempts'] if a['id']==suggestion['submission_id']),None)
            if not attempt or digest(attempt['answer'].get('text',''))!=suggestion['base_text_hash']:raise ValueError('建议不再对应原始作品')
            return suggestion
        if r.operation=='writing.preview':
            old=checked_head(runtime,'writing',original,r.peer_id,p.expected_revision);refs=[]
            if p.suggestion_ids:
                candidates=selected_suggestions(runtime,old,p.suggestion_ids,r.peer_id)
                edits=[e for s in candidates for e in s['edits']];text=apply_suggestions(old['text'],edits)
                refs=[{k:s[k] for k in ['id','owner_device','contributor','base_text_hash']} for s in candidates]
            else:text=p.text
            if not text.strip():raise ValueError('修订稿不能为空')
            changes=text_changes(old['text'],text)
            if not changes:raise ValueError('稿件没有变化，无需保存新版本')
            contribution='teacher_proposed_revision' if runtime.role=='teacher' else 'external_assisted_revision' if refs else 'learner_revision_declared'
            return seal({**common('writing-preview-'+uuid4().hex),'kind':'writing','parent_id':old['id'],'parent_revision':old['revision'],
                'parent_hash':old['content_hash'],'proposed':{'text':text,'text_hash':digest(text),'contribution':contribution,
                    'contribution_note':p.contribution_note,'additional_help':p.additional_help,'suggestion_refs':refs},
                'changes':changes,'runtime_policy':policy(runtime,old['goal'],[old['task_id']] if old.get('task_id') else [],r.peer_id,'apply',draft=text)})
        if r.operation=='writing.submit':
            runtime.require_role('student');old=checked_head(runtime,'writing',original,None,p.expected_revision)
            if not old.get('task_id'):raise ValueError('先关联学习任务，再明确提交给老师或本机任务')
            task=authorized_task(runtime,old['task_id'])
            if task['state']!='active' or task['pack'].get('items'):raise ValueError('此处只提交进行中的文字作品任务，不代填客观题')
            return {'document':old,'history':public_history(runtime,old),'additional_help':p.additional_help}
    def apply(body):
        if scope_key(runtime,r.peer_id)!=selected:raise PermissionError('当前授权范围变化')
        if r.operation=='path.publish':
            head=checked_head(runtime,'path',body,r.peer_id,body['revision'])
            if head['content_hash']!=body['content_hash']:raise ValueError('待发布版本已变化，请重新检查')
            return publish_path(runtime,head,r.peer_id,r.request_id)
        if r.operation=='writing.share_suggestion':
            task=authorized_task(runtime,body['task_id'],r.peer_id);runtime.require_role('teacher')
            runtime.save_config('writing-shared:'+body['id'],True)
            runtime.queue_task_update(r.peer_id,task['id'],event_id='writing-suggestion-'+digest(r.request_id))
            return {'suggestion_id':body['id'],'delivery':'queued_for_peer'}
        if r.operation=='writing.submit':
            doc=access(runtime,'writing',body['document']['id']);checked_head(runtime,'writing',doc,None,body['document']['revision'])
            task=authorized_task(runtime,doc['task_id']);key='writing:'+r.request_id
            runtime.submit(doc['task_id'],{},doc['text'],[],key,{'additional_help':body['additional_help']},writing_history=body['history'])
            return {'document_id':doc['id'],'revision':doc['revision'],'task_id':doc['task_id'],'text_hash':doc['text_hash'],
                'delivery':'queued_for_peer' if task.get('origin')=='teacher' else 'saved_locally','mastery_updated':False}
        kind={'path.create':'path','path.preview':'path_preview','path.confirm':'path','writing.create':'writing',
            'writing.suggest':'suggestion','writing.preview':'writing_preview','writing.confirm':'writing'}[r.operation]
        if 'parent_id' in body:access(runtime,'path' if body['kind']=='path' else 'writing',body['parent_id'],r.peer_id)
        if kind in ['path','writing'] and body['revision']>1:
            head=access(runtime,kind,body['id'],r.peer_id)
            if head['revision']!=body['revision']-1 and head['content_hash']!=body['content_hash']:raise ValueError('其他操作已更新此版本，请重新预览')
        if kind=='path':
            for tid in body['task_ids']:authorized_task(runtime,tid,r.peer_id)
        if kind in ['writing','suggestion'] and body.get('task_id'):authorized_task(runtime,body['task_id'],r.peer_id)
        saved=store.save(runtime,kind,body)
        return {'preview' if kind.endswith('preview') else 'suggestion' if kind=='suggestion' else 'path' if kind=='path' else 'document':saved}
    if writes:data=transact(runtime,r,prepare,apply)
    elif r.operation in ['path.list','writing.list']:
        kind='path' if is_path else 'writing';values=[]
        for v in store.rows(runtime,kind):
            try:value=access(runtime,kind,v['id'],r.peer_id)
            except (PermissionError,ValueError,KeyError):continue
            values.append(value)
        data={'paths' if is_path else 'documents':values[:100],'truncated':len(values)>100}
    elif r.operation in ['path.read','writing.read']:
        versions=store.versions(runtime,'path' if is_path else 'writing',original['id'])
        data={'path' if is_path else 'document':original,'versions':versions[:1]+versions[-99:] if len(versions)>100 else versions,'truncated':len(versions)>100}
    elif r.operation=='writing.history':
        from base.app.companion.functional.evolution_sync import read_history
        data=read_history(runtime,p.task_id,p.history_id,r.peer_id)
    else:data={'suggestions':writing_suggestions(runtime,original,r.peer_id)}
    # Cached receipts must not revive a revoked task or a different learner's record.
    if writes:
        if original:access(runtime,'path' if is_path else 'writing',original['id'],r.peer_id)
        for k in ['path','document']:
            if k in data:access(runtime,'path' if k=='path' else 'writing',data[k]['id'],r.peer_id)
    return EvolutionResult(request_id=r.request_id,operation=r.operation,status='completed',data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'actor':runtime.role,'scope':selected,
            'professional_validation':'NOT_AUTOMATIC','mastery_updated':False},
        **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if writes else {})).model_dump(mode='json',exclude_none=True)

"""Teacher pre-review facade: immutable model evidence, editable versions, human publication."""
import hashlib,json
from pathlib import Path
from uuid import uuid4
from base.core import now
from base.app.companion.assets.references import digest
from base.app.companion.assets.review import quote_refs,field_changes,seal
from base.app.companion.aesthetic.prereview import descriptor,normalize_report,check_teacher_fields
from base.app.companion.functional.review_contracts import ReviewRequest,ReviewResult,PAYLOADS
from base.app.companion.functional import review_store as store
from base.app.companion.functional.study import authorized_task,invoke as study_invoke
from base.app.companion.functional.study_store import transact,append_assessment,ledger

def target(runtime,task_id,submission_id,peer_id,latest=True):
    runtime.require_role('teacher')
    if not peer_id:raise ValueError('请选择已配对学生')
    task=authorized_task(runtime,task_id,peer_id)
    attempt=next((a for a in task['attempts'] if a['id']==submission_id),None)
    if not attempt:raise PermissionError('这份作品不属于所选学生和任务')
    if latest and (task['state']=='archived' or task['attempts'][-1]['id']!=submission_id):raise ValueError('任务已归档或已有新提交，请刷新后评阅最新作品')
    return task,attempt

def context(runtime,task_id,submission_id,peer_id):
    task,attempt=target(runtime,task_id,submission_id,peer_id);pack=task['pack'];answer=attempt['answer']
    plan=pack.get('companion_plan',{});criteria=plan.get('criteria') or pack.get('rubric')
    if not criteria:
        raw=runtime.service._task(task_id)['snapshot'];criteria=[raw['criteria']]
    if not 1<=len(criteria)<=10 or any(not isinstance(c,str) or not 1<=len(c)<=1500 for c in criteria):raise ValueError('当前评价标准过长或超过10项，请先人工评阅或拆分任务')
    attachments=[];limitations=[];has_sound=False
    for id in answer.get('files',[]):
        f=runtime.service.file(id)
        if f['learner_id']!=task['learner_id']:raise PermissionError('作品附件主体不匹配')
        path=Path(f['path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=f['sha256']:raise ValueError('作品附件缺失或内容变化，不能采用旧预审')
        attachments.append({'id':id,'mime':f['mime'],'sha256':f['sha256'],'model_read':False})
        has_sound=has_sound or f['mime'].startswith(('audio/','video/webm'))
        limitations.append('附件未由本次文字模型读取：'+f['mime']+'，须教师查看原件。')
    if pack.get('source_page'):limitations.append('本次文字预审未读取原始图面；图中依据须教师查看原图核对。')
    if pack.get('audio') or task['purpose'] in ['listening','speaking']:limitations.append('本次未分析声音，不能据此判断实际听辨、发音或口语流利度。')
    if not answer.get('learning_conditions'):limitations.append('历史参与和额外帮助条件未完整记录，不能补认为独立完成。')
    if answer.get('writing_history_ref'):limitations.append('此作品附有修订历史；本次仅看当前稿与帮助声明，教师应另查首稿和外部贡献。')
    coverage={'requires_unread_media':bool(attachments or pack.get('source_page') or pack.get('audio') or task['purpose']=='speaking'),
        'has_sound':has_sound,'needs_sound':task['purpose']=='speaking' or plan.get('runtime_policy',{}).get('scenario_id')=='speaking',
        'limitations':list(dict.fromkeys(limitations)),'text_model_only':True}
    policy=descriptor()
    source={'task_id':task_id,'submission_id':submission_id,'purpose':task['purpose'],
        'goal':plan.get('goal',''),'instructions':pack['instructions'],'criteria':criteria,
        'material':pack.get('stimulus',''),'items':[{k:i[k] for k in ['id','kind','prompt','options','key','evidence','explanation'] if k in i} for i in pack.get('items',[])],
        'work':answer.get('text',''),'answers':answer.get('answers',{}),'learning_conditions':answer.get('learning_conditions','not_recorded'),
        'help_declaration':answer.get('conditions','not_recorded'),'exact_checks':attempt.get('automatic'),
        'attachments':attachments,'coverage':coverage,'policy':policy,
        'task_policy_refs':plan.get('runtime_policy',{}).get('policy_refs',plan.get('policy_refs',[]))}
    if pack.get('academic'):
        source['work']='\n'.join(q['id']+'：'+answer.get('answers',{}).get(q['id'],'') for q in pack['items'])
        source['material']='\n\n'.join(q['id']+' '+q.get('material','')+'\n'+q['prompt'] for q in pack['items'])
    if len(json.dumps(source,ensure_ascii=False))>60000:raise ValueError('单次预审上下文超过6万字符，请拆分任务或人工评阅')
    basis={'pack_hash':digest(pack),'answer_hash':digest(answer),'attachments':attachments,'criteria':criteria,'policy_hash':policy['hash'],
        'teacher_review_hash':digest({'evaluation':attempt.get('evaluation'),'history':attempt.get('review_history'),
            'ledger':[r for r in ledger(runtime,task_id) if r['submission_id']==submission_id and r['source_type']=='teacher_review']})}
    return {'context_hash':digest(basis),'basis':basis,'source':source,'coverage':coverage}

def own(runtime,kind,id,peer_id,revision=None):
    value=store.get(runtime,kind,id,revision)
    if value['peer_id']!=peer_id:raise PermissionError('评阅草稿不属于当前学生')
    target(runtime,value['task_id'],value['submission_id'],peer_id,False)
    return value

def current(runtime,value,peer_id):
    value_context=context(runtime,value['task_id'],value['submission_id'],peer_id)
    if value_context['context_hash']!=value['context_hash']:raise ValueError('原答、标准或教师评阅已有变化，请重新读取，不覆盖新记录')
    return value_context

def ai_fields(report):return {k:report[k] for k in ['comment','next_step','dimensions']}|{'outcome':'ungraded'}

def enqueue(runtime,task_id,submission_id,peer_id,request_id,automatic=False):
    runtime.require_role('teacher');target(runtime,task_id,submission_id,peer_id)
    id='review-job-'+digest([peer_id,task_id,submission_id,'automatic' if automatic else request_id])
    body={'mode':'prereview','task_id':task_id,'submission_id':submission_id,'peer_id':peer_id,'automatic':automatic}
    configured=runtime.model_status()['configured'];status='queued' if configured else 'failed'
    error=None if configured else '本机模型API未配置或本次会话Key不可用，请配置后手动重新预审。'
    with runtime.db() as db:db.execute('INSERT OR IGNORE INTO local_jobs VALUES (?,?,?,?,?,?)',(id,status,json.dumps(body),None,error,now()))
    return {'id':id,'status':runtime.job(id)['status'],'local_web_worker_required':True}

def on_received(runtime,task,peer_id):
    if runtime.role=='teacher' and runtime.config('prereview-settings',{}).get('automatic') and task['attempts'] and task['state']!='archived':
        enqueue(runtime,task['id'],task['attempts'][-1]['id'],peer_id,'received',True)

def publish_assessment(runtime,r,draft,sound_confirmed):
    """Use the existing idempotent v2 publication, repairing an interrupted audit append."""
    fields=draft['fields'];internal='pr-publish-'+digest(r.request_id)
    request={'contract_version':'companion.capability.v2','request_id':internal,'operation':'assessment.record','peer_id':r.peer_id,
        'payload':{'task_id':draft['task_id'],'submission_id':draft['submission_id'],'source_type':'teacher_review',
            **fields,'human_review_confirmed':True}}
    with runtime.db() as db:
        done=db.execute('SELECT 1 FROM feedback_requests WHERE key=?',('study-review:'+internal,)).fetchone()
        saved=db.execute('SELECT * FROM companion_requests WHERE id=?',(internal,)).fetchone()
    if done and saved:
        from base.app.companion.functional.study_contracts import StudyRequest
        if saved['fingerprint']!=digest(StudyRequest.model_validate(request).model_dump()):raise ValueError('发布恢复内容不匹配')
        record=json.loads(saved['prepared']);append_assessment(runtime,record)
        with runtime.db() as db:db.execute('UPDATE companion_requests SET result=? WHERE id=?',(json.dumps({'record':record},ensure_ascii=False),internal))
        return record
    if own(runtime,'draft',draft['id'],r.peer_id)['content_hash']!=draft['content_hash']:raise ValueError('草稿已在其他窗口修改，请核对最新版本')
    c=current(runtime,draft,r.peer_id);s=c['source'];coverage=c['coverage']
    check_teacher_fields(fields,s['criteria'],s['work'],s['material'],coverage['needs_sound'],coverage['has_sound'],sound_confirmed)
    return study_invoke(runtime,request)['data']['record']

def assistance(runtime,peer_id,task_id):
    return [{k:v[k] for k in ['assessment_id','submission_id','used_ai','model_name','teacher_modified','draft_revision','created']}
        for v in store.rows(runtime,'publication',peer_id,task_id)[:50]]

def invoke(runtime,raw):
    runtime.require_role('teacher')
    try:
        r=ReviewRequest.model_validate(raw);p=PAYLOADS[r.operation].model_validate(r.payload) if r.operation in PAYLOADS else None
        if p is None and r.payload:raise ValueError()
    except ValueError:raise ValueError('预审请求无效，请核对学生、提交、版本及必填项') from None
    store.initialize(runtime)
    if r.operation.startswith('review.settings'):
        if r.peer_id:raise ValueError('自动预审设置属于教师本机，不属于某个学生')
    elif not r.peer_id:raise ValueError('请选择已连接学生')
    original=None;publication=None
    if hasattr(p,'draft_id') and p.draft_id:original=own(runtime,'draft',p.draft_id,r.peer_id)
    if hasattr(p,'task_id'):authorized_task(runtime,p.task_id,r.peer_id)
    writes=r.operation in ['review.capture','review.draft.save','review.publish','review.settings.save','review.start']
    def base(id,task_id,submission_id,revision=1):return {'id':id,'revision':revision,'peer_id':r.peer_id,'task_id':task_id,'submission_id':submission_id,'created':now()}
    def prepare():
        if r.operation=='review.settings.save':return {'automatic':p.automatic,'cost_owner':'teacher_own_api','formal_review_automatic':False}
        if r.operation=='review.start':
            c=context(runtime,p.task_id,p.submission_id,r.peer_id)
            if not runtime.model_status()['configured']:raise ValueError('请先在教师本机配置自己的模型API，或由外部Agent读取review.context后提供候选')
            return {'task_id':p.task_id,'submission_id':p.submission_id,'context_hash':c['context_hash']}
        if r.operation=='review.capture':
            c=context(runtime,p.task_id,p.submission_id,r.peer_id)
            if c['context_hash']!=p.context_hash:raise ValueError('预审依据已变化，模型结果未保存')
            report=normalize_report(p.report.model_dump(),c['source']['criteria'],c['source']['work'],c['source']['material'],c['coverage'])
            return seal({**base('prereview-'+uuid4().hex,p.task_id,p.submission_id),'context_hash':c['context_hash'],
                'basis':c['basis'],'report':report,'coverage':c['coverage'],'policy':descriptor(),'model_name':p.model_name,
                'source_type':'model_candidate','formal_review_written':False,
                'evidence_refs':quote_refs(report['dimensions'],p.task_id,p.submission_id,c['source']['work'],c['source']['material'])})
        if r.operation=='review.draft.save':
            c=context(runtime,p.task_id,p.submission_id,r.peer_id)
            if c['context_hash']!=p.context_hash:raise ValueError('原答、标准或评阅已变化，请刷新')
            if original:
                if original['task_id']!=p.task_id or original['submission_id']!=p.submission_id or original['revision']!=p.expected_revision:raise ValueError('草稿版本或作品不匹配')
            elif p.expected_revision:raise ValueError('新草稿的期望版本应为0')
            ai=None
            if p.prereview_id:
                ai=own(runtime,'prereview',p.prereview_id,r.peer_id)
                if ai['task_id']!=p.task_id or ai['submission_id']!=p.submission_id or ai['context_hash']!=p.context_hash:raise ValueError('AI预审不属于当前作品版本')
            fields=p.fields.model_dump()
            # Saving may retain unresolved dimensions; only publication can confirm meets_criteria.
            check_teacher_fields({**fields,'outcome':'ungraded'},c['source']['criteria'],c['source']['work'],c['source']['material'])
            before=original['fields'] if original else ai_fields(ai['report']) if ai else {}
            return seal({**base(original['id'] if original else 'review-draft-'+uuid4().hex,p.task_id,p.submission_id,(original['revision']+1) if original else 1),
                'context_hash':c['context_hash'],'fields':fields,'prereview_id':p.prereview_id,'changes':field_changes(before,fields),
                'teacher_modified':bool(ai and field_changes(ai_fields(ai['report']),fields)),'parent_hash':original['content_hash'] if original else None})
        if r.operation=='review.publish':
            if original['revision']!=p.expected_revision or original['content_hash']!=p.draft_hash:raise ValueError('草稿已更新，请重新核对后发布')
            current(runtime,original,r.peer_id)
            return seal({**base('review-pub-'+digest(r.request_id),original['task_id'],original['submission_id']),
                'draft_id':original['id'],'draft_revision':original['revision'],'draft_hash':original['content_hash'],
                'prereview_id':original['prereview_id'],'used_ai':bool(original['prereview_id']),
                'model_name':own(runtime,'prereview',original['prereview_id'],r.peer_id)['model_name'] if original['prereview_id'] else '',
                'teacher_modified':original['teacher_modified'],'human_review_confirmed':True,'sound_review_confirmed':p.sound_review_confirmed})
    def apply(body):
        runtime.require_role('teacher')
        if r.operation=='review.settings.save':runtime.save_config('prereview-settings',body);return {'settings':body}
        if r.operation=='review.start':return {'job':enqueue(runtime,body['task_id'],body['submission_id'],r.peer_id,r.request_id)}
        if r.operation=='review.publish':
            target(runtime,body['task_id'],body['submission_id'],r.peer_id,False)
            try:existing=own(runtime,'publication',body['id'],r.peer_id)
            except KeyError:existing=None
            if existing:
                runtime.queue_task_update(r.peer_id,body['task_id'],event_id='review-published-'+digest(r.request_id))
                return {'publication':existing}
            pinned=own(runtime,'draft',body['draft_id'],r.peer_id,body['draft_revision'])
            if pinned['content_hash']!=body['draft_hash']:raise ValueError('发布草稿内容校验失败')
            record=publish_assessment(runtime,r,pinned,body['sound_review_confirmed'])
            value=seal({**body,'assessment_id':record['id']});store.save(runtime,'publication',value)
            runtime.queue_task_update(r.peer_id,body['task_id'],event_id='review-published-'+digest(r.request_id))
            return {'publication':value}
        current(runtime,body,r.peer_id)
        kind='prereview' if r.operation=='review.capture' else 'draft'
        return {kind:store.save(runtime,kind,body)}
    if writes:data=transact(runtime,r,prepare,apply)
    elif r.operation=='review.settings':data={'settings':runtime.config('prereview-settings',{'automatic':False}),'model_configured':runtime.model_status()['configured']}
    elif r.operation=='review.context':data=context(runtime,p.task_id,p.submission_id,r.peer_id)
    elif r.operation=='review.list':
        task=authorized_task(runtime,p.task_id,r.peer_id);data={}
        try:c=context(runtime,p.task_id,task['attempts'][-1]['id'],r.peer_id)
        except (ValueError,PermissionError,KeyError,FileNotFoundError,IndexError):c=None
        data['history_truncated']=False
        for kind,label in [('prereview','prereviews'),('draft','drafts'),('publication','publications')]:
            all_values=store.rows(runtime,kind,r.peer_id,p.task_id);data['history_truncated']=data['history_truncated'] or len(all_values)>30;values=all_values[:30]
            for value in values:
                value['current']=bool(task['attempts'] and value['submission_id']==task['attempts'][-1]['id']) if kind=='publication' else bool(c and value['context_hash']==c['context_hash'])
            data[label]=values
    elif r.operation=='review.draft.read':data={'draft':original}
    else:
        job=runtime.job(p.job_id);body=job['body']
        if body.get('mode')!='prereview' or body.get('peer_id')!=r.peer_id:raise PermissionError('预审任务不属于当前学生')
        target(runtime,body['task_id'],body['submission_id'],r.peer_id,False)
        data={'job':{k:job[k] for k in ['id','status','error','result','created']}}
    # Replayed receipts never revive a revoked pairing.
    if original:own(runtime,'draft',original['id'],r.peer_id)
    if hasattr(p,'task_id'):authorized_task(runtime,p.task_id,r.peer_id)
    return ReviewResult(request_id=r.request_id,operation=r.operation,status='completed',data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'model_is_teacher':False,'professional_validation':'NOT_REVIEWED'},
        **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if writes else {})).model_dump(mode='json',exclude_none=True)

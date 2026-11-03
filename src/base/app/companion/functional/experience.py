"""Compose existing reading, policy, assessment and review capabilities for a local learner."""
from base.app.companion.assets.references import digest
from base.app.companion.functional.experience_contracts import ExperienceRequest,ExperienceResult,PAYLOADS
from base.app.companion.functional.study import authorized_task
from base.app.companion.functional.study_store import initialize,transact

KEY='learning-experience-v1'

def describe(runtime):
    role=runtime.role
    mode='teacher' if role=='teacher' else runtime.config(KEY,'student')
    if mode not in ['student','self'] and role!='teacher':mode='student'
    return {'id':mode,'brand':{'teacher':'Enlighter','student':'Evolver','self':'Self-Evolver'}[mode],
        'label':{'teacher':'教师工作台','student':'跟随老师学习','self':'自主学习'}[mode],
        'identity_role':role,'data_location':'this_device','model_account':'user_configured',
        'selection_changes_identity':False}

def require_self(runtime):
    runtime.require_role('student')
    if describe(runtime)['id']!='self':raise PermissionError('请先明确切换到Self-Evolver自学版')

def own_work(runtime,task_id,submission_id):
    task=authorized_task(runtime,task_id)
    if task.get('origin')=='teacher':raise PermissionError('老师布置的任务请在跟随老师模式中完成，保留原有帮助与评价要求')
    attempt=next((a for a in task['attempts'] if a['id']==submission_id),None)
    if not attempt:raise PermissionError('这份提交不属于本次自主学习任务')
    return task,attempt

def feedback_context(runtime,task_id,submission_id):
    require_self(runtime);task,a=own_work(runtime,task_id,submission_id);pack=task['pack'];plan=pack.get('companion_plan') or {}
    answer=a['answer']
    value={'task_id':task_id,'submission_id':submission_id,'title':pack['title'],
        'goal':plan.get('goal',pack.get('instructions','')),'criteria':plan.get('criteria',pack.get('rubric',[])),
        'material':pack.get('stimulus',''),'questions':pack.get('items',[]),'text':answer.get('text',''),
        'answers':answer.get('answers',{}),'automatic':a.get('automatic'),
        'learning_conditions':answer.get('learning_conditions','not_recorded'),
        'answer_hash':digest(answer),'task_hash':digest(pack),'source_ref':plan.get('source_ref'),
        'policy_refs':plan.get('policy_refs',[]),'runtime_policy':plan.get('runtime_policy',{}),
        'unobserved':(['attachments_not_opened'] if answer.get('files') else [])+(['audio_not_listened'] if pack.get('audio') else [])+
            (['original_image_not_viewed'] if pack.get('source_page') else []),
        'feedback_authority':'self_report_or_model_suggestion'}
    return value

def invoke(runtime,raw):
    if runtime.role not in ['teacher','student']:raise PermissionError('请先设置本机身份')
    try:
        r=ExperienceRequest.model_validate(raw);p=PAYLOADS[r.operation].model_validate(r.payload)
    except ValueError:raise ValueError('v11请求无效，请核对学习模式、来源与实际提交') from None
    if r.peer_id:raise PermissionError('学习模式与自主任务只操作当前本机使用者')
    initialize(runtime)
    def call(op,payload,version='v3',tag=None):
        return runtime.invoke_capability({'contract_version':'companion.capability.'+version,
            'request_id':'exp-'+digest([r.request_id,tag or op]),'operation':op,'payload':payload})['data']
    if r.operation=='experience.read':data={'experience':describe(runtime)}
    elif r.operation=='experience.select':
        allowed=['teacher'] if runtime.role=='teacher' else ['student','self']
        if p.experience not in allowed:raise PermissionError('切换学习模式不会改变教师/学生身份权限')
        transact(runtime,r,lambda:{'experience':p.experience},lambda prepared:select(runtime,prepared['experience']))
        data={'experience':describe(runtime)}
    else:
        require_self(runtime)
        if r.operation=='self.context':
            tasks=[t for t in runtime.student_dashboard()['tasks'] if t.get('origin')!='teacher']
            data={'experience':describe(runtime),'tasks':tasks,'no_teacher_required':True,
                'feedback_authority':'self_report_or_model_suggestion','three_layers':'existing_policy_functional_assets'}
        elif r.operation=='self.feedback_context':data=feedback_context(runtime,p.task_id,p.submission_id)
        elif r.operation=='self.start':
            if p.source.task_id:
                task=authorized_task(runtime,p.source.task_id)
                if task.get('origin')=='teacher':raise PermissionError('自主学习请使用自己的材料；老师任务保留原有完成要求')
            # This calls the existing Policy Pack runtime and frozen source assembly.
            data=transact(runtime,r,lambda:p.model_dump(),lambda body:call('activity.create',body))
            data.update(experience='self',feedback_authority='self_report_or_model_suggestion')
        else:
            own_work(runtime,p.task_id,p.submission_id)
            def reflect(body):
                result=call('assessment.record',{'task_id':body['task_id'],'submission_id':body['submission_id'],'source_type':'self_report',
                    **{k:body[k] for k in ['outcome','comment','next_step']}},'v2')
                if body['schedule_review']:
                    cards=call('review.list',{})['cards']
                    existing=next((c for c in cards if c['task_id']==body['task_id']),None)
                    result['review']=existing or call('review.create',{'task_id':body['task_id'],'prompt':body['next_step'][:1500]},tag='review')['card']
                return result
            data=transact(runtime,r,lambda:p.model_dump(),reflect)
            data['feedback_authority']='self_report'
    return ExperienceResult(request_id=r.request_id,operation=r.operation,status='completed',data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'reuses':['v3_policy_activity','v2_assessment','v3_review'],
            'identity_role':runtime.role,'teacher_review_created':False},
        **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if r.operation in ['experience.select','self.start','self.reflect'] else {})).model_dump(mode='json',exclude_none=True)

def select(runtime,mode):
    runtime.save_config(KEY,mode)
    return {'selected':mode}

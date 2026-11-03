"""Source reading, policy-bound activities, append-only assessments and preview imports."""
import json
from uuid import uuid4
from pydantic import ValidationError
from base.core import now
from base.app.companion.assets.references import digest
from base.app.companion.aesthetic.scenarios import design,options
from base.app.companion.functional.study_contracts import StudyRequest,StudyResult,PAYLOADS,MaterialRead
from base.app.companion.functional.study_store import initialize,transact,ledger,append_assessment
from base.app.companion.functional.evidence import authorized_tasks
from base.app.companion.functional.bank_import import preview

def authorized_task(runtime,task_id,peer_id=None):
    return authorized_tasks(runtime,peer_id,task_id)[1][0]

def read_material(runtime,p,peer_id=None):
    if runtime.role not in ['student','teacher']:raise PermissionError('请先完成本机身份设置')
    if p.task_id:
        task=authorized_task(runtime,p.task_id,peer_id)
        pack=task['pack'];plan=pack.get('companion_plan')
        if not plan:raise ValueError('此任务没有绑定资料学习来源')
        if pack.get('source_page'):raise ValueError('此任务绑定原图，请使用 v3 page.read 读取原始页面')
        material={'id':plan['source_ref'].get('material_id','task:'+plan['source_ref'].get('task_id',task['id'])),'revision':plan['source_ref']['revision'],
                  'title':pack['title'],'text':pack['stimulus'],'source':pack.get('source',{}).get('title',''),
                  'source_hash':digest(pack['stimulus']),'owner_ref':plan['source_ref']['owner_ref'],
                  'task_id':task['id'],'superseded':False}
    else:
        if not p.material_id:raise ValueError('请选择一份本机资料')
        with runtime.db() as db:
            row=db.execute('SELECT body FROM companion_materials WHERE id=? '+('AND revision=? ' if p.revision else '')+'ORDER BY revision DESC LIMIT 1',
                (p.material_id,p.revision) if p.revision else (p.material_id,)).fetchone()
            head=db.execute('SELECT MAX(revision) FROM companion_materials WHERE id=?',(p.material_id,)).fetchone()[0]
        if not row:raise KeyError('该版本资料不存在于本机')
        material=json.loads(row['body']);material['superseded']=material['revision']!=head
    if p.revision and p.revision!=material['revision']:raise ValueError('资料版本不匹配')
    if p.material_id and p.material_id!=material['id']:raise ValueError('资料与任务引用不匹配')
    if p.source_hash and p.source_hash!=material['source_hash']:raise ValueError('资料内容版本不匹配，请重新打开资料')
    end=p.end if p.end is not None else len(material['text'])
    if p.start>=end or end>len(material['text']):raise ValueError('所选文字范围无效')
    ref={k:material[k] for k in ['id','revision','source_hash','owner_ref']}
    ref['material_id']=ref.pop('id');ref.update(start=p.start,end=end)
    if p.task_id:ref['task_id']=p.task_id
    return {**material,'selection':material['text'][p.start:end],'selection_ref':ref,
            'quality':{'processing':'readable','domain_review':'unknown','task_fit':'requires_task_judgment'}}

def assessment_list(runtime,task_id,peer_id=None):
    task=authorized_task(runtime,task_id,peer_id)
    local=ledger(runtime,task_id)
    remote=task.get('companion_assessments',[]) if runtime.role=='student' and task.get('origin')=='teacher' else []
    entries={r['id']:r for r in local+remote}
    return {'task_id':task_id,'entries':sorted(entries.values(),key=lambda x:(x['created'],x['id'])),
            'legacy_review_count':sum(len(a.get('review_history',[])) for a in task.get('attempts',[])),
            'legacy_note':'旧评阅仍保留在原历史中，不伪造新账本记录。'}

def require_scope(runtime,r,p):
    if r.operation.startswith('bank.'):
        runtime.require_role('teacher')
    if r.operation=='activity.create':
        if runtime.role=='teacher':
            if not r.peer_id:raise ValueError('请先选择一位已配对学生')
            runtime.peer(r.peer_id)
        elif r.peer_id:raise PermissionError('学生只能创建本人的资料学习任务')
    if r.operation.startswith('assessment.'):
        task=authorized_task(runtime,p.task_id,r.peer_id)
        if r.operation=='assessment.record':
            if task['state']=='archived':raise ValueError('已归档活动只读，不能新增评价记录')
            if not any(a['id']==p.submission_id for a in task.get('attempts',[])):raise PermissionError('提交不属于所选任务')
            if p.source_type=='teacher_review':
                runtime.require_role('teacher')
                if not p.human_review_confirmed:raise ValueError('请确认已亲自查看作品及评价依据')
            elif p.outcome=='meets_criteria':raise PermissionError('自评和模型建议不能写入教师达标结论')
            if p.source_type=='self_report':runtime.require_role('student')
            required=task['pack'].get('companion_plan',{}).get('criteria',[])
            if p.outcome=='meets_criteria' and required:
                supported={d.get('criterion') for d in p.dimensions if d.get('status')=='supported' and d.get('observation','').strip()}
                if supported!=set(required):raise ValueError('确认本次达标前，请逐项填写观察，并确认每项已有支持证据')
            runtime_policy=task['pack'].get('companion_plan',{}).get('runtime_policy')
            if runtime_policy:
                from base.app.companion.aesthetic.engine import check_assessment
                attempt=next(a for a in task['attempts'] if a['id']==p.submission_id)
                sound=any(runtime.service.file(f)['mime'].startswith('audio/') for f in attempt['answer'].get('files',[]))
                check_assessment(runtime_policy,p.model_dump(),has_sound=sound)
            for d in p.dimensions:
                if set(d)-{'criterion','observation','evidence','status'} or not all(isinstance(v,str) and len(v)<=1500 for v in d.values()):
                    raise ValueError('分项观察字段无效')
                if d.get('status','ungraded') not in ['ungraded','partial','supported','needs_revision']:raise ValueError('分项观察状态无效')
                criteria=task['pack'].get('companion_plan',{}).get('criteria',[])
                if criteria and d.get('criterion') not in criteria:raise ValueError('评价维度应对应活动发布时的标准')
                if d.get('evidence'):
                    attempt=next(a for a in task['attempts'] if a['id']==p.submission_id)
                    if d['evidence'] not in attempt['answer'].get('text','') and d['evidence'] not in task['pack'].get('stimulus',''):
                        raise ValueError('分项引用须能在原答或本次资料中定位')
    if r.operation=='material.read' and p.task_id:authorized_task(runtime,p.task_id,r.peer_id)

def invoke(runtime,raw):
    if runtime.role not in ['student','teacher']:raise PermissionError('请先完成本机身份设置')
    try:
        r=StudyRequest.model_validate(raw)
        p=PAYLOADS[r.operation].model_validate(r.payload) if r.operation in PAYLOADS else None
        if p is None and r.payload:raise ValueError('此读取动作无需额外字段')
    except (ValidationError,ValueError):raise ValueError('学习请求格式无效，请核对必填项、长度和操作类型。') from None
    require_scope(runtime,r,p)
    initialize(runtime)
    write=r.operation in ['material.save','activity.create','assessment.record','bank.preview','bank.commit']
    def prepare():
        if r.operation=='material.save':
            if not all(x.strip() for x in [p.title,p.text,p.source]):raise ValueError('标题、正文和来源不能为空')
            normalized=p.text.replace('\r\n','\n').replace('\r','\n')
            mid=p.material_id or uuid4().hex
            with runtime.db() as db:head=db.execute('SELECT MAX(revision) FROM companion_materials WHERE id=?',(mid,)).fetchone()[0]
            if p.material_id and (head is None or p.expected_revision!=head):raise ValueError('资料已更新或不存在，请重新打开再修改')
            return {'id':mid,'revision':(head or 0)+1,'title':p.title.strip(),'text':normalized,'source':p.source.strip(),
                    'source_hash':digest(normalized),'owner_ref':'device:'+runtime.identity.id,'created':now()}
        if r.operation=='activity.create':
            if not p.goal.strip():raise ValueError('请填写本次希望做到什么')
            material=read_material(runtime,p,r.peer_id)
            if len(material['selection'])>12000:raise ValueError('一次学习片段请控制在12000字以内，可选择较小片段')
            plan=design(p.method,p.goal,p.obstacle,p.question,material['selection_ref'],p.target_operation,p.criteria)
            target=runtime.service.public_person(runtime.peer(r.peer_id)['learner_id'] if runtime.role=='teacher' else runtime.profile['learner_id'])
            exam=target['exam'];stage=target['stage']
            pack={'id':'reading-'+uuid4().hex,'family_id':material['id'],'title':material['title'],'purpose':'reading',
                'exam':exam,'stage':stage,'task_type':'source_response','instructions':plan['question'],'stimulus':material['selection'],
                'items':[],'source':{'kind':'user_material','title':material['source']},'companion_plan':plan,'audio':None}
            draft={'name':'超维成长','activity_title':pack['title'],'goal':p.goal,'deliverable':plan['operation'],
                'instructions':plan['question'],'material':pack['stimulus'],'criteria':'；'.join(plan['criteria']),
                'next_step':plan['verification'],'mode':'text','assessment_version':'source-response-1','growth':pack}
            return {'draft':draft,'plan':plan}
        if r.operation=='assessment.record':
            task=authorized_task(runtime,p.task_id,r.peer_id)
            attempt=next(a for a in task['attempts'] if a['id']==p.submission_id)
            return {'id':uuid4().hex,'task_id':p.task_id,'submission_id':p.submission_id,'created':now(),
                'source_type':p.source_type,'outcome':p.outcome,'comment':p.comment,'next_step':p.next_step,'dimensions':p.dimensions,
                'evidence':{'answer_hash':digest(attempt['answer']),'source_ref':task['pack'].get('companion_plan',{}).get('source_ref'),
                            'policy_refs':task['pack'].get('companion_plan',{}).get('policy_refs',[]),
                            'learning_conditions':attempt['answer'].get('learning_conditions','not_recorded'),
                            'policy_execution':task['pack'].get('companion_plan',{}).get('runtime_policy',{})},
                'authority':'teacher_declared_review' if p.source_type=='teacher_review' else 'non_authoritative_observation',
                'human_review_confirmed':p.human_review_confirmed if p.source_type=='teacher_review' else False}
        if r.operation=='bank.preview':
            body=preview(runtime,p.format,p.content);body.update(id=uuid4().hex,created=now())
            body['preview_hash']=digest(body)
            return body
        if r.operation=='bank.commit':
            with runtime.db() as db:row=db.execute('SELECT body FROM companion_previews WHERE id=?',(p.preview_id,)).fetchone()
            if not row:raise KeyError('请先生成导入预览')
            body=json.loads(row['body'])
            if body['preview_hash']!=p.preview_hash or body['errors']:raise ValueError('预览已变化或仍有错误，不能导入')
            return body
    def apply(body):
        require_scope(runtime,r,p)
        if r.operation=='material.save':
            with runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                old=db.execute('SELECT body FROM companion_materials WHERE id=? AND revision=?',(body['id'],body['revision'])).fetchone()
                if old and json.loads(old['body'])!=body:raise ValueError('版本冲突，请刷新资料')
                head=db.execute('SELECT MAX(revision) FROM companion_materials WHERE id=?',(body['id'],)).fetchone()[0]
                if not old and (head or 0)!=body['revision']-1:raise ValueError('资料已被其他操作更新')
                db.execute('INSERT OR IGNORE INTO companion_materials VALUES (?,?,?,?)',(body['id'],body['revision'],json.dumps(body,ensure_ascii=False),body['created']))
            return {'material':{k:v for k,v in body.items() if k!='text'}}
        if r.operation=='activity.create':
            if runtime.role=='teacher':
                learner=runtime.peer(r.peer_id)['learner_id']
            else:learner=runtime.profile['learner_id']
            person=runtime.service.public_person(learner)
            receipt=runtime.service.base.create(person['name'],body['draft'],'study:'+r.request_id,learner_id=learner)
            tid=receipt['id']
            if runtime.role=='teacher':
                with runtime.db() as db:db.execute('INSERT OR IGNORE INTO local_task_links VALUES (?,?)',(tid,r.peer_id))
                with runtime.db() as db:exists=db.execute('SELECT 1 FROM local_outbox WHERE id=?',('assign-'+tid,)).fetchone()
                if not exists:runtime.queue(r.peer_id,'task.assigned',{'task':runtime.service.session(tid)},event_id='assign-'+tid)
            return {'task_id':tid,'plan':body['plan'],'delivery':'queued_for_peer' if runtime.role=='teacher' else 'local'}
        if r.operation=='assessment.record':
            if p.source_type=='teacher_review':
                runtime.service.feedback(p.submission_id,p.comment,p.next_step,p.outcome if p.outcome in ['meets_criteria','needs_revision'] else None,None,'study-review:'+r.request_id)
            append_assessment(runtime,body)
            if runtime.role=='teacher':runtime.queue_task_update(r.peer_id,p.task_id)
            return {'record':body}
        if r.operation=='bank.preview':
            with runtime.db() as db:db.execute('INSERT OR IGNORE INTO companion_previews VALUES (?,?,?)',(body['id'],json.dumps(body,ensure_ascii=False),body['created']))
            return {k:v for k,v in body.items() if k!='packs'} | {'packs':[{'id':x['id'],'title':x['title'],'exam':x['exam'],'task_type':x['task_type'],'items':len(x['items'])} for x in body['packs']]}
        if r.operation=='bank.commit':
            inserted=[];skipped=[]
            with runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                for pack in body['packs']:
                    if db.execute('SELECT 1 FROM hd_resources WHERE id=?',(pack['id'],)).fetchone():skipped.append(pack['id']);continue
                    db.execute('INSERT INTO hd_resources VALUES (?,?)',(pack['id'],json.dumps(pack,ensure_ascii=False)))
                    inserted.append(pack['id'])
            return {'imported':inserted,'skipped_existing':skipped,'status':'pending_review'}
    if write:data=transact(runtime,r,prepare,apply)
    elif r.operation=='study.options':data={'methods':options(),'formats':['text','csv','json'],'limitations':['PDF/OCR与表格XLSX适配尚未接入','本次规则为候选，专业质量仍需审阅']}
    elif r.operation=='material.list':
        with runtime.db() as db:rows=db.execute('SELECT body FROM companion_materials m WHERE revision=(SELECT MAX(revision) FROM companion_materials WHERE id=m.id) ORDER BY created DESC').fetchall()
        data={'materials':[{k:v for k,v in json.loads(row['body']).items() if k!='text'} for row in rows]}
    elif r.operation=='material.read':data=read_material(runtime,p,r.peer_id)
    else:data=assessment_list(runtime,p.task_id,r.peer_id)
    return StudyResult.model_validate({'contract_version':'companion.capability.v2','request_id':r.request_id,'operation':r.operation,'status':'completed','data':data,
            'decision_trace':{'layers':['aesthetic','functional','assets'],'policy_version':'reading-design-1','professional_validation':'NOT_REVIEWED'},
            **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if write else {})}).model_dump(mode='json',exclude_none=True)

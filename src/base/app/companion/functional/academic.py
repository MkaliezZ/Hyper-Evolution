"""Academic Harness: scope/auth, frozen assets, K12 teaching and signed feedback."""
import base64,hashlib,json,re
from datetime import date
from pathlib import Path
from base.core import now
from base.app.companion.aesthetic.academic import SUBJECTS,LEVELS,TYPES,SKILLS,TRAPS,CAUSES,OPEN,CHOICE,policy,validate_draft,check_reviews,scope_check,next_step
from base.app.companion.assets.references import digest
from base.app.companion.assets.academic import seal,question_fingerprint
from base.app.companion.functional.academic_contracts import AcademicRequest,AcademicResult,PAYLOADS,EMPTY,DraftBody
from base.app.companion.functional import academic_store as store
from base.app.companion.functional.study_store import transact
from base.app.companion.functional.study import authorized_task

TEACHER={'k12.draft.review','k12.draft.publish','k12.target.confirm','k12.bank.retire','k12.problem.record','k12.explain.save','k12.score.record','k12.evidence.correct',
 'k12.class.save','k12.class.list','k12.class.assign','k12.class.report','k12.class.candidates','k12.notifications','k12.notifications.read'}

def check_peer(runtime,peer):
    if runtime.role=='teacher':
        if not peer:raise ValueError('请选择一位已配对学生')
        if runtime.peer(peer)['role']!='student':raise PermissionError('请选择学生身份')
    elif peer:raise PermissionError('学生只能操作本人的学科记录')

def read(runtime,kind,id,peer,revision=None):
    value=store.get(runtime,kind,id,revision)
    if kind not in ['class','batch','media','notification']:
        check_peer(runtime,peer)
        if value.get('peer_id')!=peer:raise PermissionError('记录不属于所选学生')
    elif kind in ['class','batch','notification']:runtime.require_role('teacher')
    return value

def route(runtime,id,peer,active=True):
    r=read(runtime,'route',id,peer)
    if active and r['archived']:raise ValueError('这条路线已归档，不能新增教学活动')
    return r

def refs(runtime,ids,route_id,peer):
    values=[read(runtime,'scope',id,peer) for id in ids]
    if any(s['route_id']!=route_id for s in values):raise ValueError('教材范围不属于本次路线')
    r=route(runtime,route_id,peer)
    if any(s['order']>r['scope_order'] for s in values):raise ValueError('所选单元超过当前明确登记的进度，请先核对路线进度')
    for s in values:
        if s.get('material_ref'):
            from base.app.companion.functional.study import read_material
            from base.app.companion.functional.study_contracts import MaterialRead
            source=read_material(runtime,MaterialRead.model_validate(s['material_ref']),None)
            if source['superseded']:raise ValueError('关联资料已有新版本，请核对并更新本范围引用后再出题')
    return values

def current_draft(runtime,id,peer,revision=None):
    d=read(runtime,'draft',id,peer,revision);rr=route(runtime,d['route_id'],peer)
    if d['route_ref']['content_hash']!=rr['content_hash']:raise ValueError('路线目标或进度已更新，请另存新草稿后重新审题')
    scopes={s['id']:s for s in refs(runtime,[v['id'] for v in d['scope_refs']],d['route_id'],peer)}
    for ref in d['scope_refs']:
        if scopes[ref['id']]['content_hash']!=ref['content_hash']:raise ValueError('范围已更新，请保存新的出题草稿再审校')
    if d['body'].get('audio_id'):audio(runtime,d['body']['audio_id'])
    return d

def audio(runtime,id):
    a=store.get(runtime,'media',id);p=runtime.folder/'peer-media'/a['sha256']
    if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=a['sha256']:raise ValueError('原始录音缺失或内容变化')
    return a,p

def task_work(runtime,task_id,submission_id,peer):
    t=authorized_task(runtime,task_id,peer)
    if not t['pack'].get('academic'):raise ValueError('请选择K12任务')
    a=next((a for a in t['attempts'] if a['id']==submission_id),None)
    if not a:raise PermissionError('这份原答不属于当前任务')
    return t,a

def question(t,id):
    q=next((q for q in t['pack']['items'] if q['id']==id),None)
    if not q:raise ValueError('题号不属于当前任务')
    return q

def route_tasks(runtime,r,peer):
    if runtime.role=='teacher':tasks=runtime.teacher_dashboard(peer)['tasks']
    else:tasks=runtime.student_dashboard()['tasks']
    return [t for t in tasks if t['pack'].get('academic',{}).get('route_id')==r['id']]

def seen(runtime,peer):
    tasks=runtime.teacher_dashboard(peer)['tasks'] if runtime.role=='teacher' else runtime.student_dashboard()['tasks']
    return {ref for t in tasks for ref in t['pack'].get('academic',{}).get('question_refs',{}).values()}

def report(runtime,route_id,peer):
    r=route(runtime,route_id,peer,False);tasks=route_tasks(runtime,r,peer);taskids={t['id'] for t in tasks}
    records=lambda k:[x for x in store.rows(runtime,k,peer) if x.get('task_id') in taskids]
    problems=records('problem');scores=records('score');errata=records('erratum');results=[];pending=0
    for t in tasks:
        if not t['attempts']:continue
        a=t['attempts'][-1];auto=a.get('automatic') or {};by_id={x['id']:x for x in auto.get('items',[])}
        recorded={v['question_id'] for v in problems if v['task_id']==t['id'] and v['submission_id']==a['id']}
        for row in auto.get('items',[]):
            if row.get('correct') is False and row['id'] not in recorded:
                problems.append({'task_id':t['id'],'submission_id':a['id'],'question_id':row['id'],'route_id':r['id'],
                    'state':'observation_only','observation':'本题实际作答：'+row['answer']+'；需要核对本次表现。','cause':'',
                    'selected_trap':row.get('selected_trap'),'source':'automatic_observation_not_causal_diagnosis'})
        scoremap={x['question_id']:x for x in scores if x['submission_id']==a['id']}
        pending+=len([q for q in t['pack']['items'] if q.get('open_response') and q['id'] not in scoremap])
        meta=t['pack']['academic'];target=meta.get('target');conditions=a['answer'].get('learning_conditions',{})
        if meta['mode']=='target':
            help_clear=conditions.get('additional_help') in ['none','没有额外帮助','无额外帮助']
            invalid={e['question_id'] for e in errata if e['task_id']==t['id'] and e['invalid_item']}
            outcomes=[]
            for label,ids in target['outcomes'].items():
                total=sum(question(t,id).get('points',1) for id in ids)
                unresolved=any((question(t,id).get('open_response') and id not in scoremap) or id in invalid for id in ids)
                actual=sum(scoremap[id]['score'] if id in scoremap else (question(t,id).get('points',1) if by_id.get(id,{}).get('correct') else 0) for id in ids)
                state='pending' if unresolved or not help_clear else 'meets_this_target' if actual/total>=target['threshold'] else 'needs_more_evidence'
                outcomes.append({'target':label,'question_ids':ids,'score':actual,'total':total,'state':state})
            results.append({'task_id':t['id'],'submission_id':a['id'],'outcomes':outcomes,'threshold':target['threshold'],
                'meaning':'本次预先声明目标及试行标准；不代表长期掌握、全国水平或托雅分数。'})
    value={'route':r,'tasks':len(tasks),'submitted':sum(bool(t['attempts']) for t in tasks),'pending_reviews':pending,
        'invalid_questions':sum(x['invalid_item'] for x in errata),'confirmed_problems':sum(p['state']=='supported_cause' for p in problems),
        'unconfirmed_problems':sum(p['state']!='supported_cause' for p in problems),'problems':problems,'target_results':results,
        'unmeasured':'未覆盖的目标、无录音的听辨及未验证原因均保持未知。','long_term_mastery':'not_inferred'}
    value['next']=next_step(value);return value

def task_feedback(runtime,peer,task_id):
    values=[]
    for kind in ['problem','explanation','score','erratum']:
        for record in store.rows(runtime,kind,peer):
            if record.get('task_id')!=task_id:continue
            public={k:v for k,v in record.items() if k not in ['tutor','peer_id','evidence_note','student_quote','check_task_id','check_submission_id']}
            public=seal({k:v for k,v in public.items() if k!='content_hash'})
            values.append({'kind':kind,**public})
    return values[-200:]

def invoke(runtime,raw):
    if runtime.role not in ['teacher','student']:raise PermissionError('先完成本机身份设置')
    try:
        r=AcademicRequest.model_validate(raw)
        if r.operation not in PAYLOADS and r.operation not in EMPTY:raise ValueError()
        p=PAYLOADS[r.operation].model_validate(r.payload) if r.operation in PAYLOADS else None
        if p is None and r.payload:raise ValueError()
    except ValueError:raise ValueError('学科请求无效，请核对操作、必填项及版本') from None
    store.initialize(runtime)
    op=r.operation;peer=r.peer_id
    if op.startswith(('academic.material.','academic.page.','academic.asset.')):
        from base.app.companion.functional.subject_materials import invoke as subject_invoke
        return subject_invoke(runtime,r,p)
    if op in TEACHER:runtime.require_role('teacher')
    if op.startswith('route.') or op.startswith('scope.') or op.startswith('k12.') and not op.startswith(('k12.class.','k12.media.','k12.notifications')):check_peer(runtime,peer)
    if hasattr(p,'route_id'):route(runtime,p.route_id,peer,op not in ['route.read','k12.report','scope.list','k12.draft.list','k12.bank.list'])
    if op=='k12.class.assign':return class_assign(runtime,r,p)
    writes=op in ['academic.select','route.save','scope.save','k12.draft.save','k12.draft.review','k12.draft.publish','k12.draft.self_practice','k12.draft.candidate_review','k12.target.confirm','k12.bank.retire',
        'k12.bank.pick','k12.bank.compose','k12.problem.record','k12.explain.save','k12.score.record','k12.evidence.correct','k12.class.save','k12.notifications.read','k12.media.save','k12.import.preview','k12.import.commit']
    def record(kind,content,old=None):
        return {'kind':kind,'value':seal({'id':old['id'] if old else kind+'-'+digest([r.request_id,kind])[:24],
            'revision':old['revision']+1 if old else 1,'peer_id':peer,'created':now(),**content})}
    def existing(kind):
        old=read(runtime,kind,p.id,peer) if getattr(p,'id',None) else None
        if (old['revision'] if old else 0)!=getattr(p,'expected_revision',0):raise ValueError('记录已更新，请刷新后重试')
        return old
    def prepare():
        if op=='academic.select':
            if p.track not in SUBJECTS[p.subject]['tracks']:raise ValueError('此学科尚未提供这条专用路线')
            return {'selection':p.model_dump()}
        if op=='route.save':
            old=existing('route');value=p.model_dump(exclude={'id','expected_revision'})
            if p.level=='primary' and p.grade>6 or p.level=='junior' and p.grade not in [7,8,9] or p.level=='senior' and p.grade<10:raise ValueError('学段与年级不一致，使用1—12年级编号')
            if p.exam_date:date.fromisoformat(p.exam_date)
            return record('route',value|{'subject':'english','track':'k12','authority':'user_declared_route'},old)
        if op=='scope.save':
            old=existing('scope');value=p.model_dump(exclude={'id','expected_revision','material_id'});material_ref=None
            if old and old['route_id']!=p.route_id:raise PermissionError('不能把范围改到另一条路线')
            if p.content_reviewed:runtime.require_role('teacher')
            if p.material_id:
                from base.app.companion.functional.study import read_material
                from base.app.companion.functional.study_contracts import MaterialRead
                material_ref=read_material(runtime,MaterialRead(material_id=p.material_id))['selection_ref']
            return record('scope',value|{'material_ref':material_ref,'quality':'teacher_declared' if p.content_reviewed else 'candidate'},old)
        if op=='k12.media.save':
            try:data=base64.b64decode(p.data_base64,validate=True)
            except ValueError:raise ValueError('录音编码无效') from None
            if not 12<=len(data)<=12*1024*1024:raise ValueError('录音须不超过12MB')
            if p.mime=='audio/wav' and not (data[:4]==b'RIFF' and data[8:12]==b'WAVE'):raise ValueError('WAV文件头无效')
            if p.mime=='audio/mpeg' and not (data[:3]==b'ID3' or data[0]==255 and data[1]&224==224):raise ValueError('MP3文件头无效')
            return record('media',{'name':p.name,'source':p.source,'mime':p.mime,'sha256':hashlib.sha256(data).hexdigest(),
                'speech_origin':p.speech_origin})
        if op=='k12.draft.save':
            old=existing('draft');value=p.body.model_dump();validate_draft(value)
            if old and old['route_id']!=p.route_id:raise PermissionError('草稿不能换到其他路线')
            scopes=refs(runtime,value['scope_ids'],p.route_id,peer)
            if value.get('audio_id'):audio(runtime,value['audio_id'])
            rr=route(runtime,p.route_id,peer)
            return record('draft',{'route_id':p.route_id,'route_ref':{k:rr[k] for k in ['id','revision','content_hash']},'body':value,'scope_refs':[{k:s[k] for k in ['id','revision','content_hash','textbook','unit']} for s in scopes],
                'question_refs':{q['id']:question_fingerprint(q) for q in value['questions']},'policy_ref':policy(),'status':'candidate'},old)
        if op in ['k12.draft.review','k12.draft.candidate_review','k12.draft.self_practice','k12.target.confirm','k12.draft.publish','k12.bank.retire']:
            d=current_draft(runtime,p.id,peer)
            if d['revision']!=p.expected_revision:raise ValueError('出题草稿已更新')
            if hasattr(p,'draft_hash') and d['content_hash']!=p.draft_hash:raise ValueError('审校依据的草稿指纹不一致')
            if op=='k12.bank.retire':return record('retirement',{'draft_id':d['id'],'draft_hash':d['content_hash']})
            if op in ['k12.draft.review','k12.draft.candidate_review']:
                issues=list(p.issues)
                if len({x.question_id for x in p.questions})!=len(d['body']['questions']) or {x.question_id for x in p.questions}!={q['id'] for q in d['body']['questions']}:raise ValueError('审题候选必须完整对应实际题号')
                if any(not isinstance(x,str) or len(x)>2000 for x in issues):raise ValueError('审题问题说明无效')
                if set(p.independent_answers)-{q['id'] for q in d['body']['questions']} or any(not v or len(v)>10 or any(not x.strip() or len(x)>500 for x in v) for v in p.independent_answers.values()):raise ValueError('独立作答须对应实际题号并保持有界')
                for q in d['body']['questions']:
                    normalize=lambda x:' '.join(x.strip().casefold().split())
                    if q['type'] not in OPEN and p.independent_answers.get(q['id']) and not any(normalize(x) in {normalize(k) for k in q['key']} for x in p.independent_answers[q['id']]):issues.append('独立作答与参考答案不同：'+q['id'])
                try:check=check_reviews(d['body'],[x.model_dump() for x in p.questions])
                except ValueError as error:
                    if op=='k12.draft.review':raise
                    check={'status':'needs_resolution','machine_proved_correct':False};issues.append(str(error))
                if op=='k12.draft.review':
                    pending=next((v for v in store.rows(runtime,'candidate_review',peer) if v['draft_hash']==d['content_hash']),None)
                    if pending and pending.get('issues') and len(p.resolution_note.strip())<4:raise ValueError('独立审题发现分歧，请先修题或记录具体处置理由')
                if op=='k12.draft.review' and d['body'].get('audio_id') and not p.audio_listened:raise ValueError('请先完整试听本次原始录音')
                return record('draft_review' if op=='k12.draft.review' else 'candidate_review',{'draft_id':d['id'],'draft_hash':d['content_hash'],'route_id':d['route_id'],
                    'questions':[x.model_dump() for x in p.questions],'check':check,'audio_listened':getattr(p,'audio_listened',False),
                    'independent_answers':p.independent_answers,'issues':list(dict.fromkeys(issues)),'resolution_note':getattr(p,'resolution_note',''),
                    'human_review_confirmed':op=='k12.draft.review','status':'teacher_declared' if op=='k12.draft.review' else 'model_candidate'})
            if op=='k12.target.confirm':
                ids={q['id'] for q in d['body']['questions']}
                if d['body']['supports']:raise ValueError('带提示练习不能作为独立目标测验')
                if not p.target.outcomes or any(not k.strip() or not v or set(v)-ids for k,v in p.target.outcomes.items()):raise ValueError('目标必须对应本草稿实际题号')
                if set().union(*(set(v) for v in p.target.outcomes.values()))!=ids:raise ValueError('目标覆盖需包含本次全部题目')
                return record('target',{'draft_id':d['id'],'draft_hash':d['content_hash'],'route_id':d['route_id'],'target':p.target.model_dump(),'human_review_confirmed':True})
            reviews=[v for v in store.rows(runtime,'draft_review',peer) if v['draft_id']==d['id'] and v['draft_hash']==d['content_hash']]
            self_practice=op=='k12.draft.self_practice'
            if self_practice:runtime.require_role('student')
            if not reviews and not self_practice:raise ValueError('请先逐题核对并确认审校，再布置')
            if any(v['draft_id']==d['id'] and v['draft_hash']==d['content_hash'] for v in store.rows(runtime,'retirement',peer)):raise ValueError('这份备题已停用')
            used=seen(runtime,peer)
            if any(h in used for h in d['question_refs'].values()):raise ValueError('该学生已见本草稿题目，请换新题，不作为未见练习重复布置')
            target=None
            if getattr(p,'mode','practice')=='target':
                target=next((x['target'] for x in store.rows(runtime,'target',peer) if x['draft_id']==d['id'] and x['draft_hash']==d['content_hash']),None)
                if not target:raise ValueError('目标测验须先确认目标覆盖，交卷后不能补录')
            return record('publication',{'route_id':d['route_id'],'draft_id':d['id'],'draft_hash':d['content_hash'],'draft_revision':d['revision'],
                'mode':getattr(p,'mode','practice'),'target':target,'self_practice':self_practice})
        if op=='k12.bank.pick':
            value=bank_pick(runtime,p,peer);stable='selection-'+digest([peer,p.route_id,p.skills,p.scope_ids,p.count])[:24]
            try:old=read(runtime,'selection',stable,peer)
            except KeyError:old=None
            result=record('selection',value,old)
            if not old:result['value']=seal({**result['value'],'id':stable})
            return result
        if op=='k12.bank.compose':
            selection=read(runtime,'selection',p.id,peer)
            if selection['revision']!=p.expected_revision:raise ValueError('库存选择已更新，请重新查找')
            if selection['missing'] or not selection['selected']:raise ValueError('库存尚有缺口，请补齐或明确重新选择题数，不自动减少题量')
            bodies=[];questions=[];scope_ids=[];audio_ids=set();used=seen(runtime,peer)
            for selected in selection['selected']:
                d=current_draft(runtime,selected['draft_id'],peer,selected['revision'])
                if not any(x['content_hash']==d['content_hash'] for x in bank(runtime,d['route_id'],peer)):raise ValueError('选中的备题已更新、停用或失效')
                q=next(q for q in d['body']['questions'] if q['id']==selected['question_id'])
                if question_fingerprint(q)!=selected['fingerprint'] or selected['fingerprint'] in used:raise ValueError('题目变化或已经见过，请重新查库存')
                questions.append({**q,'id':'q'+str(len(questions)+1)});bodies.append(d['body']);scope_ids.extend(d['body']['scope_ids'])
                if d['body'].get('audio_id'):audio_ids.add(d['body']['audio_id'])
            if len(audio_ids)>1:raise ValueError('本版一份活动只支持一份配套录音，请分开组题')
            body={**bodies[0],'title':p.title,'source':'已审备题重新组题；来源：'+'；'.join(dict.fromkeys(b['source'] for b in bodies)),
                'questions':questions,'scope_ids':list(dict.fromkeys(scope_ids)),'audio_id':next(iter(audio_ids),None),
                'supports':list(dict.fromkeys(s for b in bodies for s in b['supports']))}
            return {'compose':{'route_id':selection['route_id'],'body':body,'selection_hash':selection['content_hash']}}
        if op in ['k12.problem.record','k12.explain.save','k12.score.record']:
            t,a=task_work(runtime,p.task_id,p.submission_id,peer);q=question(t,p.question_id)
            value=p.model_dump()|{'route_id':t['pack']['academic']['route_id'],'answer_hash':digest(a['answer'])}
            kind={'k12.problem.record':'problem','k12.explain.save':'explanation','k12.score.record':'score'}[op]
            stable=kind+'-'+digest([p.task_id,p.submission_id,p.question_id])[:24]
            try:old=read(runtime,kind,stable,peer)
            except KeyError:old=None
            if (old['revision'] if old else 0)!=p.expected_revision:raise ValueError('这道题的记录已更新，请刷新再修改')
            def versioned(content):
                result=record(kind,content,old)
                if not old:result['value']=seal({**result['value'],'id':stable})
                return result
            if op=='k12.problem.record':
                if p.cause and p.cause not in CAUSES:raise ValueError('请选择允许的原因类型，无法判断可留空')
                supported=p.evidence_source!='unverified'
                if supported:
                    if not p.cause or not p.human_confirmed or len(p.evidence_note.strip())<4:raise ValueError('确认原因须有实际依据和教师确认')
                    if p.evidence_source=='student_explanation' and not p.student_quote.strip():raise ValueError('学生解释证据须保留实际原话，不能编造')
                    if p.evidence_source=='diagnostic_check':
                        if not p.check_task_id or not p.check_submission_id:raise ValueError('请关联实际补充检查的提交')
                        ct,ca=task_work(runtime,p.check_task_id,p.check_submission_id,peer)
                        if ct['id']==t['id'] and ca['id']==a['id']:raise ValueError('原始误选不能充当自己的验证证据')
                        value['check_answer_hash']=digest(ca['answer'])
                value.update(state='supported_cause' if supported else 'hypothesis' if p.cause else 'observation_only',
                    selected_answer=a['answer']['answers'].get(q['id'],''),selected_trap=q.get('traps',{}).get(a['answer']['answers'].get(q['id'],'')),
                    qualification='teacher_declared_evidence_not_identity_certification')
                return versioned(value)
            if op=='k12.explain.save':
                material=q.get('material','') or t['pack']['stimulus']
                if p.quote and p.quote not in material:raise ValueError('讲解引用不在本题原文中')
                if q.get('k12_type','').startswith('reading') and not p.quote:raise ValueError('阅读讲解需要真实原文引用')
                return versioned(value)
            if not q.get('open_response'):raise ValueError('客观题保留原核对；坏题请追加勘误，不覆盖成绩')
            answer=a['answer']['answers'].get(q['id'],'')
            if p.score>q['points'] or answer.strip() and (not p.evidence or p.evidence not in answer):raise ValueError('分值超出原题，或缺少可回查的学生原句')
            if q['k12_type'] in ['writing','writing_task']:
                if set(p.rubric)!={'内容','交际效果','组织','语言'} or any(type(x) is not int or not 0<=x<=3 for x in p.rubric.values()):raise ValueError('K12写作须填四维0—3量规；这不是托雅分数')
                if abs(p.score-sum(p.rubric.values())/12*q['points'])>.011:raise ValueError('本题分数应由四维量规按原题分值折算')
            return versioned(value)
        if op=='k12.evidence.correct':
            t=authorized_task(runtime,p.task_id,peer);q=question(t,p.question_id)
            if not t['pack'].get('academic'):raise ValueError('请选择K12题目')
            if p.quote and p.quote not in (q.get('material','') or t['pack']['stimulus']):raise ValueError('勘误引句须来自原始材料')
            return record('erratum',p.model_dump()|{'route_id':t['pack']['academic']['route_id'],'original_evidence':q['evidence'],'original_score_changed':False})
        if op=='k12.class.save':
            old=existing('class')
            if len(set(p.peers))!=len(p.peers):raise ValueError('班级学生不能重复')
            for id in p.peers:check_peer(runtime,id)
            return record('class',p.model_dump(exclude={'id','expected_revision'}),old)
        if op=='k12.notifications.read':
            # A read acknowledgement is separate from transport ACK and formal evaluation.
            if not any(v['id']==p.id for v in notifications(runtime)['notifications']):raise ValueError('通知不属于当前可见提交')
            return record('notification',{'submission_id':p.id,'read':True})
        if op=='k12.import.preview':
            try:raw=json.loads(p.content)
            except ValueError:raise ValueError('K12导入须为JSON草稿对象数组') from None
            if not isinstance(raw,list) or not 1<=len(raw)<=30:raise ValueError('一次导入1—30份草稿')
            valid=[];errors=[]
            for index,value in enumerate(raw,1):
                try:
                    body=DraftBody.model_validate(value).model_dump();validate_draft(body);refs(runtime,body['scope_ids'],p.route_id,peer)
                    valid.append(body)
                except (ValueError,PermissionError,KeyError):errors.append({'row':index,'message':'字段、来源或题目校验未通过，请按模板核对'})
            return record('import',{'route_id':p.route_id,'drafts':valid,'errors':errors})
        if op=='k12.import.commit':
            value=read(runtime,'import',p.id,peer)
            if value['content_hash']!=p.preview_hash or value['errors']:raise ValueError('预览变化或仍有错误，不导入')
            route(runtime,value['route_id'],peer);return {'import':value}
    def apply(body):
        if op=='academic.select':runtime.save_config('academic-selection',body['selection']);return body
        if op=='k12.bank.compose':
            check_peer(runtime,peer)
            selection=read(runtime,'selection',p.id,peer)
            if selection['content_hash']!=body['compose']['selection_hash']:raise ValueError('库存选择变化，请重新组题')
            if any(x['fingerprint'] in seen(runtime,peer) for x in selection['selected']):raise ValueError('已经布置了所选题目，请重新查库存')
            return invoke(runtime,{'contract_version':r.contract_version,'request_id':'compose-'+digest(r.request_id),'operation':'k12.draft.save','peer_id':peer,
                'payload':{k:body['compose'][k] for k in ['route_id','body']}})['data']
        if op=='k12.import.commit':
            ids=[]
            for i,b in enumerate(body['import']['drafts']):
                result=invoke(runtime,{'contract_version':r.contract_version,'request_id':'import-'+digest([r.request_id,i]),'operation':'k12.draft.save','peer_id':peer,
                    'payload':{'route_id':body['import']['route_id'],'body':b}})
                ids.append(result['data']['record']['id'])
            return {'imported_drafts':ids,'status':'candidate_requires_review'}
        kind=body['kind'];v=body['value']
        if kind=='media':
            data=base64.b64decode(p.data_base64);folder=runtime.folder/'peer-media';folder.mkdir(exist_ok=True)
            path=folder/v['sha256']
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=v['sha256']:raise ValueError('媒体文件冲突')
            path.write_bytes(data)
        elif kind=='publication':
            v=publish(runtime,r,v)
        elif kind not in ['class','notification']:
            check_peer(runtime,peer)
            if v.get('route_id'):route(runtime,v['route_id'],peer)
            if v.get('task_id'):authorized_task(runtime,v['task_id'],peer)
            if kind in ['draft_review','candidate_review','target','retirement']:
                d=current_draft(runtime,v['draft_id'],peer)
                if d['content_hash']!=v['draft_hash']:raise ValueError('执行前草稿已变化，请重新核对')
            if kind=='draft':
                if route(runtime,v['route_id'],peer)['content_hash']!=v['route_ref']['content_hash']:raise ValueError('执行前路线已变化')
                for ref in v['scope_refs']:
                    if read(runtime,'scope',ref['id'],peer)['content_hash']!=ref['content_hash']:raise ValueError('执行前范围已变化')
        saved=store.save(runtime,kind,v)
        if kind in ['problem','explanation','score','erratum']:
            authorized_task(runtime,v['task_id'],peer);runtime.queue_task_update(peer,v['task_id'],event_id='academic-'+digest(r.request_id))
        return {'record':saved}
    if writes:data=transact(runtime,r,prepare,apply)
    elif op=='academic.catalog':data={'subjects':SUBJECTS,'levels':LEVELS,'types':TYPES,'skills':SKILLS,'traps':TRAPS,'causes':CAUSES,'policy':policy(),
        'business_operations':'not_in_this_release','curriculum_authority':'user_provided_scope_not_complete_official_curriculum'}
    elif op=='academic.context':data={'selection':runtime.config('academic-selection',{'subject':'english','track':'study_abroad'}),'routes':visible_routes(runtime,peer),'role':runtime.role}
    elif op=='route.list':data={'routes':visible_routes(runtime,peer)}
    elif op=='route.read':data={'route':route(runtime,p.route_id,peer,False)}
    elif op in ['scope.list','k12.draft.list','k12.replenishment.list']:
        kind={'scope.list':'scope','k12.draft.list':'draft','k12.replenishment.list':'selection'}[op]
        data={'records':[v for v in store.rows(runtime,kind,peer) if v['route_id']==p.route_id]}
    elif op=='scope.read':data={'record':read(runtime,'scope',p.id,peer)}
    elif op=='scope.check':data={'check':scope_check(p.text,refs(runtime,p.scope_ids,p.route_id,peer),p.exempt_words)}
    elif op=='k12.draft.read':data={'record':read(runtime,'draft',p.id,peer),'reviews':[v for v in store.rows(runtime,'draft_review',peer) if v['draft_id']==p.id],
        'candidate_reviews':[v for v in store.rows(runtime,'candidate_review',peer) if v['draft_id']==p.id]}
    elif op=='k12.media.read':data={'record':audio(runtime,p.id)[0]}
    elif op=='k12.bank.list':data={'records':bank(runtime,p.route_id,peer)}
    elif op=='k12.problem.list':
        t,a=task_work(runtime,p.task_id,p.submission_id,peer)
        data={'records':[v for v in store.rows(runtime,'problem',peer) if v['task_id']==p.task_id and v['submission_id']==p.submission_id],
            'observations':(a.get('automatic') or {}).get('items',[])}
    elif op=='k12.report':data=report(runtime,p.route_id,peer)
    elif op=='k12.next':data=report(runtime,p.route_id,peer)['next']
    elif op=='k12.class.list':data={'classes':store.rows(runtime,'class')}
    elif op=='k12.class.report':data=class_report(runtime,p.id)
    elif op=='k12.class.candidates':data=class_candidates(runtime,p.route_id,peer)
    else:data=notifications(runtime)
    # Cached results do not bypass current pair authorization.
    if peer:check_peer(runtime,peer)
    return AcademicResult(request_id=r.request_id,operation=op,status='completed',data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'policy_ref':policy(),'professional_validation':'NOT_REVIEWED'},
        **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if writes else {})).model_dump(mode='json',exclude_none=True)

def visible_routes(runtime,peer):
    values=store.rows(runtime,'route',peer)
    return [v for v in values if (runtime.role=='student' and v.get('peer_id') is None) or (runtime.role=='teacher' and any(p['id']==v.get('peer_id') and p['state']=='active' for p in runtime.peers()))]

def bank(runtime,route_id,peer):
    reviews={v['draft_hash'] for v in store.rows(runtime,'draft_review',peer)};retired={v['draft_hash'] for v in store.rows(runtime,'retirement',peer)}
    values=[]
    for v in store.rows(runtime,'draft',peer):
        if v['route_id']!=route_id or v['content_hash'] not in reviews-retired:continue
        try:current_draft(runtime,v['id'],peer)
        except (ValueError,KeyError):continue
        values.append(v)
    return values

def bank_pick(runtime,p,peer):
    used=seen(runtime,peer);selected=[];unique=set()
    for d in bank(runtime,p.route_id,peer):
        if p.scope_ids and set(d['body']['scope_ids'])!=set(p.scope_ids):continue
        for q in d['body']['questions']:
            h=d['question_refs'][q['id']]
            if h in used or h in unique or p.skills and q['skill'] not in p.skills:continue
            unique.add(h);selected.append({'draft_id':d['id'],'revision':d['revision'],'question_id':q['id'],'fingerprint':h})
            if len(selected)==p.count:break
        if len(selected)==p.count:break
    return {'route_id':p.route_id,'selected':selected,'requested':p.count,'missing':p.count-len(selected),'skills':p.skills,'scope_ids':p.scope_ids,
        'next':'库存不足时独立备题，不改变当前题量或伪装已见题为新题。' if len(selected)<p.count else '逐题复核当前适配后布置'}

def publish(runtime,r,value):
    try:return read(runtime,'publication',value['id'],r.peer_id)
    except KeyError:pass
    d=current_draft(runtime,value['draft_id'],r.peer_id,value['draft_revision'])
    if d['content_hash']!=value['draft_hash']:raise ValueError('发布依据变化')
    rr=route(runtime,d['route_id'],r.peer_id);b=d['body'];items=[]
    for q in b['questions']:
        kind='mcq' if q['type'] in CHOICE else 'gap'
        items.append({**q,'kind':kind,'k12_type':q['type'],'open_response':q['type'] in OPEN})
    metadata={'version':'k12.task.v1','subject':'english','track':'k12','level':rr['level'],'grade':rr['grade'],'route_id':rr['id'],'route_ref':d['route_ref'],
        'scope_refs':d['scope_refs'],'mode':value['mode'],'target':value['target'],'supports':b['supports'],'question_refs':d['question_refs'],'policy_ref':d['policy_ref']}
    pack={'id':d['id'],'family_id':'k12-'+digest(d['question_refs']),'title':b['title'],'purpose':'reading','exam':'k12-'+rr['level'],
        'stage':rr['level'],'task_type':'k12_mixed','instructions':b['instructions'],'stimulus':'','items':items,'source':{'kind':'user_k12','title':b['source']},
        'academic':metadata,'rubric':b['criteria'],'audio':None,'companion_plan':{'goal':b['goal'],'criteria':b['criteria'],'question':b['instructions'],
            'operation':'依本次范围理解、作答和说明依据','verification':'原答保留，评价后用未见材料检查','policy_refs':[d['policy_ref']]}}
    if value.get('self_practice'):pack['review_state']='K12自主练习，未经教师审校'
    from base.app.companion.functional.teaching_workflow import rows as workflow_rows
    from base.app.companion.assets.teaching_workflow import ref as workflow_ref, public_blueprint
    blueprint=next((v for v in workflow_rows(runtime,'blueprint',r.peer_id) if v['draft_ref']==workflow_ref(d)),None)
    if blueprint:pack['teaching_blueprint']=public_blueprint(blueprint)
    extra={}
    if b.get('audio_id'):
        a,path=audio(runtime,b['audio_id']);pack.update(audio=a['sha256'],audio_sha256=a['sha256']);metadata['audio_ref']={k:a[k] for k in ['id','sha256','source','speech_origin']}
        extra={'audio':{'data':base64.b64encode(path.read_bytes()).decode(),'sha256':a['sha256']}}
    learner=runtime.peer(r.peer_id)['learner_id'] if runtime.role=='teacher' else runtime.profile['learner_id']
    person=runtime.service.public_person(learner)
    activity={'name':'超维成长','activity_title':b['title'],'goal':b['goal'],'instructions':b['instructions'],'material':'原始材料与录音按逐题内容查看。来源：'+b['source'],
        'deliverable':'按本次题目完成作答，说明帮助','criteria':'；'.join(b['criteria']),'next_step':'查看反馈后选择适当验证','mode':'text','assessment_version':'k12.grade.v1','growth':pack}
    receipt=runtime.service.base.create(person['name'],activity,'academic-publish:'+r.request_id,learner_id=learner);tid=receipt['id']
    if runtime.role=='teacher':
        with runtime.db() as db:db.execute('INSERT OR IGNORE INTO local_task_links VALUES (?,?)',(tid,r.peer_id))
        runtime.queue(r.peer_id,'task.assigned',{'task':runtime.service.session(tid),**extra},event_id='assign-'+tid)
    return seal({**value,'task_id':tid,'delivery':'queued_for_peer' if r.peer_id else 'local'})

def notifications(runtime):
    read_ids={v['submission_id'] for v in store.rows(runtime,'notification')};values=[]
    for p in runtime.peers():
        if p['role']!='student' or p['state']!='active':continue
        for t in runtime.teacher_dashboard(p['id'])['tasks']:
            if t['pack'].get('academic'):
                for a in t['attempts']:values.append({'id':a['id'],'task_id':t['id'],'peer_id':p['id'],'title':t['pack']['title'],'created':a['created'],'read':a['id'] in read_ids})
    return {'notifications':sorted(values,key=lambda x:x['created'],reverse=True)[:100]}

def class_report(runtime,id):
    c=store.get(runtime,'class',id);active={p['id'] for p in runtime.peers() if p['state']=='active'}
    batches=[b for b in store.rows(runtime,'batch') if b['class_id']==id];rows=[]
    for b in batches:
        for entry in b['entries']:
            if entry['peer_id'] not in active:rows.append({'state':'authorization_revoked'});continue
            if not entry.get('task_id'):rows.append(entry);continue
            t=authorized_task(runtime,entry['task_id'],entry['peer_id']);a=t['attempts'][-1] if t['attempts'] else None
            scored={s['question_id'] for s in store.rows(runtime,'score',entry['peer_id']) if a and s['submission_id']==a['id'] and s['task_id']==t['id']}
            pending=[q['id'] for q in t['pack']['items'] if q.get('open_response') and q['id'] not in scored]
            rows.append({'peer_id':entry['peer_id'],'task_id':t['id'],'state':'not_submitted' if not a else 'pending_review' if pending else 'submitted',
                'objective':None if not a else {k:(a.get('automatic') or {}).get(k) for k in ['score','total']}})
    return {'class':c,'rows':rows,'meaning':'按布置时冻结名单汇总；未交和待评不算零分，班级均分不代表个人掌握。'}

def class_candidates(runtime,route_id,peer):
    r=route(runtime,route_id,peer);values=[]
    def signatures(rr,who):
        rep=report(runtime,rr['id'],who);by_task={t['id']:t for t in route_tasks(runtime,rr,who)};result={}
        for evidence in rep['target_results']:
            if any(o['state']=='pending' for o in evidence['outcomes']):continue
            task=by_task[evidence['task_id']];meta=task['pack']['academic']
            # Comparable means the same frozen questions, targets, conditions and supplied scope.
            signature=digest({'questions':sorted(meta['question_refs'].values()),'target':meta['target'],
                'scope':sorted(s['content_hash'] for s in meta['scope_refs'])})
            result[signature]=evidence
        return result
    own=signatures(r,peer)
    for v in visible_routes(runtime,None):
        if v['id']==r['id'] or v['archived'] or (v['level'],v['grade'])!=(r['level'],r['grade']):continue
        other=signatures(v,v['peer_id']);common=set(own)&set(other)
        if common:values.append({'peer_id':v['peer_id'],'route_id':v['id'],'evidence':[other[k] for k in common]})
    return {'candidates':values,'meaning':'仅返回同学段年级、相同冻结题目/目标/范围且评分与独立帮助声明完整的候选；声明并非身份或独立过程认证，不自动分组。'}

def class_assign(runtime,r,p):
    bid='batch-'+digest(r.request_id)[:24]
    try:b=store.get(runtime,'batch',bid)
    except KeyError:b=None
    c=store.get(runtime,'class',p.id,p.expected_revision if b else None)
    if c['revision']!=p.expected_revision or c['archived']:raise ValueError('班级版本已变化或已归档')
    source=store.get(runtime,'draft',p.source_draft_id,p.source_revision);check_peer(runtime,source['peer_id'])
    current=current_draft(runtime,source['id'],source['peer_id'])
    if current['content_hash']!=source['content_hash']:raise ValueError('源草稿已变化，请重新选择当前版本')
    sr=route(runtime,source['route_id'],source['peer_id']);reviews=[x for x in store.rows(runtime,'draft_review',source['peer_id']) if x['draft_hash']==source['content_hash']]
    if not reviews:raise ValueError('源草稿尚未审校')
    if b is None:
        b=seal({'id':bid,'revision':1,'class_id':c['id'],'class_revision':c['revision'],'peer_id':None,'source_hash':source['content_hash'],
            'members':c['peers'],'entries':[],'created':now()});store.save(runtime,'batch',b)
    if b['source_hash']!=source['content_hash'] or b['class_id']!=c['id'] or b['class_revision']!=p.expected_revision:raise ValueError('批量请求标识不能用于另一份作业或名单')
    done={x['peer_id']:x for x in b['entries'] if x.get('task_id')};entries=[]
    for peer in b['members']:
        if peer in done:entries.append(done[peer]);continue
        try:
            check_peer(runtime,peer)
            rr=next((x for x in visible_routes(runtime,peer) if not x['archived'] and (x['level'],x['grade'])==(sr['level'],sr['grade'])),None)
            if not rr:raise ValueError('没有匹配的学段年级路线')
            if source['body']['scope_ids'] and rr['id']!=sr['id']:raise ValueError('教材范围须逐人映射确认，不能跨学生复制源范围')
            body={**source['body'],'scope_ids':source['body']['scope_ids'] if rr['id']==sr['id'] else []}
            def call(op,payload):return invoke(runtime,{'contract_version':r.contract_version,'request_id':'batch-'+digest([r.request_id,peer,op]),'operation':op,'peer_id':peer,'payload':payload})['data']['record']
            d=call('k12.draft.save',{'route_id':rr['id'],'body':body})
            call('k12.draft.review',{'id':d['id'],'expected_revision':d['revision'],'draft_hash':d['content_hash'],'questions':reviews[0]['questions'],'human_review_confirmed':True,'audio_listened':reviews[0]['audio_listened']})
            pub=call('k12.draft.publish',{'id':d['id'],'expected_revision':d['revision'],'mode':'practice','human_review_confirmed':True})
            entries.append({'peer_id':peer,'task_id':pub['task_id'],'state':'queued'})
        except (ValueError,PermissionError,KeyError) as error:entries.append({'peer_id':peer,'state':'failed','error':str(error)})
    updated=seal({**b,'revision':b['revision']+1,'entries':entries});store.save(runtime,'batch',updated)
    return AcademicResult(request_id=r.request_id,operation=r.operation,status='completed' if all(x.get('task_id') for x in entries) else 'partial',data={'batch':updated},
        decision_trace={'policy_ref':policy(),'target_confirmation_copied':False}).model_dump(mode='json',exclude_none=True)

"""Shared v3 Harness: policies, original pages and personal learning continuity."""
import base64
import json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from base.core import now
from base.app.companion.aesthetic.engine import catalog,compose,METHODS,SCENES
from base.app.companion.assets.pages import decode_original,check_original
from base.app.companion.assets.references import digest
from base.app.companion.functional.continuity_contracts import ContinuityRequest,ContinuityResult,PAYLOADS,Source
from base.app.companion.functional.study_store import initialize as study_initialize,transact
from base.app.companion.functional.study import authorized_task,read_material
from base.app.companion.functional.study_contracts import MaterialRead

def initialize(runtime):
    study_initialize(runtime)
    with runtime.db() as db:db.executescript('''
        CREATE TABLE IF NOT EXISTS companion_pages(id TEXT NOT NULL,revision INTEGER NOT NULL,body TEXT NOT NULL,PRIMARY KEY(id,revision));
        CREATE TABLE IF NOT EXISTS companion_memory_versions(id TEXT NOT NULL,revision INTEGER NOT NULL,scope TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(id,revision));
        CREATE TABLE IF NOT EXISTS companion_review_cards(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS companion_review_events(id TEXT PRIMARY KEY,card_id TEXT NOT NULL,body TEXT NOT NULL);
    ''')

def scope(runtime,peer_id=None):
    if runtime.role=='student':
        if peer_id:raise PermissionError('个人学习记录只能使用本机学生身份')
        return 'self'
    runtime.require_role('teacher')
    if not peer_id:raise ValueError('请先选择已配对学生')
    runtime.peer(peer_id)
    return 'peer:'+peer_id

def page(runtime,source,peer_id=None,include_image=True):
    """Current authorization before bytes, every time; source references are not credentials."""
    if source.task_id:
        task=authorized_task(runtime,source.task_id,peer_id)
        value=task['pack'].get('source_page')
        if not value:raise ValueError('这个任务未绑定原图')
        value=dict(value);encoded=value.pop('data_base64')
        raw,decoded=decode_original(encoded)
        if decoded['mime']!=value.get('mime'):raise ValueError('原图媒体类型不匹配')
    else:
        if not source.page_id:raise ValueError('请选择原图')
        with runtime.db() as db:
            row=db.execute('SELECT body FROM companion_pages WHERE id=? '+('AND revision=? ' if source.revision else '')+'ORDER BY revision DESC LIMIT 1',
                (source.page_id,source.revision) if source.revision else (source.page_id,)).fetchone()
        if not row:raise KeyError('本机没有该版本原图')
        value=json.loads(row['body'])
        # Filenames are generated from content hashes, never accepted as caller paths.
        raw=(runtime.folder/'uploads'/('page-'+value['source_hash'])).read_bytes()
    check_original(raw,value['source_hash'])
    if source.revision and source.revision!=value['revision']:raise ValueError('原图版本不匹配')
    if source.source_hash and source.source_hash!=value['source_hash']:raise ValueError('原图哈希不匹配')
    ref={'page_id':value['id'],'revision':value['revision'],'source_hash':value['source_hash'],'region':source.region or [0.,0.,1.,1.]}
    if source.task_id:ref={'task_id':source.task_id,**{k:v for k,v in ref.items() if k!='page_id'}}
    return {**value,'source_ref':ref,**({'data_base64':base64.b64encode(raw).decode()} if include_image else {})}

def source_value(runtime,source,peer_id=None):
    if source.page_id:return {'kind':'image','page':page(runtime,source,peer_id),'verified':True}
    if source.task_id:
        task=authorized_task(runtime,source.task_id,peer_id)
        if task['pack'].get('source_page'):return {'kind':'image','page':page(runtime,source,peer_id),'verified':True}
        if task['pack'].get('audio'):
            if runtime.role=='student' and task.get('origin')=='teacher':path=runtime.folder/'peer-media'/task['pack']['audio']
            else:
                resource=next((r for r in runtime.service.resources() if r.get('audio')==task['pack']['audio']),None)
                path=None if not resource else Path(resource['media_path'])
            if not path or not path.is_file():raise ValueError('录音原件缺失')
            check_original(path.read_bytes(),task['pack']['audio'])
            return {'kind':'audio','verified':True,'task':task,'ref':{'task_id':task['id'],'source_hash':task['pack']['audio']}}
    if source.task_id and not task['pack'].get('companion_plan'):
        text=task['pack'].get('stimulus','')
        end=source.end if source.end is not None else len(text)
        if not text or not 0<=source.start<end<=len(text):raise ValueError('该任务没有可用的文字范围')
        checksum=digest(text)
        if source.source_hash and source.source_hash!=checksum:raise ValueError('原任务文字版本不匹配')
        material={'id':'task:'+task['id'],'title':task['pack']['title'],'source':task['pack'].get('source',{}).get('title','原任务快照'),
            'text':text,'selection':text[source.start:end],'selection_ref':{'task_id':task['id'],'revision':1,'source_hash':checksum,'start':source.start,'end':end}}
        return {'kind':'text','verified':True,'material':material,'ref':material['selection_ref']}
    material=read_material(runtime,MaterialRead.model_validate({k:v for k,v in source.model_dump(exclude_none=True).items() if k not in ['page_id','region']}),peer_id)
    return {'kind':'text','verified':True,'material':material,'ref':material['selection_ref']}

def policy_plan(runtime,p,peer_id=None):
    subject=getattr(runtime,'workspace_subject',None)
    if subject:
        from base.app.companion.aesthetic.workspace_rules import require_scenario
        require_scenario(subject,p.scenario)
    value=source_value(runtime,p.source,peer_id) if p.source else {'kind':'none','verified':False}
    if value['kind']=='image':value['ref']=value['page']['source_ref']
    evidence=[]
    if p.source and p.source.task_id:
        task=authorized_task(runtime,p.source.task_id,peer_id)
        evidence=[{'task_id':task['id'],'submission_id':a['id'],'answer_hash':digest(a['answer'])} for a in task.get('attempts',[])[-2:]]
    if not evidence and (runtime.role=='student' or peer_id):
        from base.app.companion.functional.evidence import authorized_tasks
        tasks=authorized_tasks(runtime,peer_id)[1]
        evidence=[{'task_id':task['id'],'submission_id':a['id'],'answer_hash':digest(a['answer'])} for task in tasks for a in task.get('attempts',[])[-1:]][-3:]
    context=p.model_dump(exclude={'source'});context['material']={k:value.get(k) for k in ['kind','verified','ref']};context['evidence']=evidence
    if subject:context['subject']=subject
    decision=compose(context)
    if value['kind']=='image' and not p.question:
        decision['question']='观察原图并完成本次目标：'+p.goal+'。说明图中证据的位置，区分观察与推断；看不清的部分保留未知。'
    return decision,value

def anchor(runtime,task_id,peer_id=None):
    task=authorized_task(runtime,task_id,peer_id)
    if not task.get('attempts'):raise ValueError('还没有作品依据，请先完成一次学习再保存札记或安排复习')
    if task['pack'].get('source_page'):page(runtime,Source(task_id=task_id),peer_id,False)
    a=task['attempts'][-1]
    return task,{'task_id':task_id,'submission_id':a['id'],'answer_hash':digest(a['answer']),
        'evaluation_hash':digest(a.get('evaluation',{})),'source_hash':digest(task['pack'].get('stimulus','')),
        'page_hash':task['pack'].get('source_page',{}).get('source_hash')}

def anchor_state(runtime,ref,peer_id=None):
    task=authorized_task(runtime,ref['task_id'],peer_id)
    a=next((a for a in task.get('attempts',[]) if a['id']==ref['submission_id']),None)
    valid=bool(a and digest(a['answer'])==ref['answer_hash'] and digest(task['pack'].get('stimulus',''))==ref['source_hash'])
    if valid and ref.get('page_hash'):
        try:page(runtime,Source(task_id=task['id'],source_hash=ref['page_hash']),peer_id,False)
        except (ValueError,KeyError,FileNotFoundError):valid=False
    changed=bool(a and (digest(a.get('evaluation',{}))!=ref['evaluation_hash'] or task['attempts'][-1]['id']!=a['id']))
    return task,valid and not changed,'current' if valid and not changed else 'source_updated_or_missing'

def memory_rows(runtime,selected_scope):
    with runtime.db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_memory_versions'").fetchone():return []
        rows=db.execute('SELECT body FROM companion_memory_versions m WHERE scope=? AND revision=(SELECT MAX(revision) FROM companion_memory_versions WHERE id=m.id) ORDER BY rowid DESC LIMIT 100',(selected_scope,)).fetchall()
    return [json.loads(r['body']) for r in rows]

def memories(runtime,peer_id=None,include_hidden=False,for_model=False):
    selected_scope=scope(runtime,peer_id);entries=[];excluded=0
    for value in memory_rows(runtime,selected_scope):
        try:states=[anchor_state(runtime,r,peer_id) for r in value['source_refs']]
        except (PermissionError,KeyError):excluded+=1;continue
        current=all(x[1] for x in states)
        if value['hidden'] and not include_hidden:continue
        if for_model and (value['hidden'] or not current or not value.get('allow_for_model')):continue
        if for_model:
            entries.append({'id':value['id'],'revision':value['revision'],'body':value['body'][:1200],
                'source_refs':value['source_refs'],'authorship':value['authorship']})
        else:entries.append({**value,'current':current,'source_state':'current' if current else 'source_updated_or_missing'})
    if for_model:entries=entries[:3]
    return {'entries':entries,'excluded_unauthorized':excluded,'scope':selected_scope,'mastery':'not_inferred'}

def get_memory(runtime,memory_id,peer_id=None):
    selected_scope=scope(runtime,peer_id)
    with runtime.db() as db:row=db.execute('SELECT body FROM companion_memory_versions WHERE id=? AND scope=? ORDER BY revision DESC LIMIT 1',(memory_id,selected_scope)).fetchone()
    value=json.loads(row['body']) if row else None
    if not value:raise KeyError('札记不属于当前上下文')
    for ref in value['source_refs']:anchor_state(runtime,ref,peer_id)
    return value

def get_card(runtime,card_id):
    runtime.require_role('student')
    with runtime.db() as db:row=db.execute('SELECT body FROM companion_review_cards WHERE id=?',(card_id,)).fetchone()
    if not row:raise KeyError('复习卡不存在')
    card=json.loads(row['body']);task,_,_=anchor_state(runtime,card['source_ref'])
    return card,task

def review_list(runtime,include_paused=False):
    runtime.require_role('student');values=[];excluded=0
    with runtime.db() as db:rows=db.execute('SELECT body FROM companion_review_cards').fetchall()
    for row in rows:
        c=json.loads(row['body'])
        try:task,current,reason=anchor_state(runtime,c['source_ref'])
        except (PermissionError,KeyError):excluded+=1;continue
        if c['paused'] and not include_paused:continue
        with runtime.db() as db:history=db.execute('SELECT body FROM companion_review_events WHERE card_id=? ORDER BY rowid DESC LIMIT 5',(c['id'],)).fetchall()
        values.append({**c,'recent_events':[{'created':e['created'],'detail':e['detail']} for e in (json.loads(x['body']) for x in history)],'source_current':current,'source_state':reason,'task_state':task['state'],
            'due':not c['paused'] and task['state']=='active' and c['due_at']<=now()})
    return {'cards':sorted(values,key=lambda x:x['due_at']),'excluded_unauthorized':excluded,
        'interval_basis':'用户可调间隔与本人回忆声明；不是校准的记忆曲线或教师掌握判断'}

def invoke(runtime,raw):
    if runtime.role not in ['student','teacher']:raise PermissionError('请先设置本机身份')
    try:
        r=ContinuityRequest.model_validate(raw)
        p=PAYLOADS[r.operation].model_validate(r.payload) if r.operation in PAYLOADS else None
        if p is None and r.payload:raise ValueError()
    except ValueError:raise ValueError('v3 请求格式无效，请核对动作、来源、版本和必填项') from None
    initialize(runtime)
    def authorize():
        if runtime.role=='student' and r.peer_id:raise PermissionError('学生不能指定其他身份上下文')
        if r.operation=='activity.create' and runtime.role=='teacher':scope(runtime,r.peer_id)
        if r.operation.startswith('memory.'):
            scope(runtime,r.peer_id)
            if hasattr(p,'task_ids'):
                for tid in p.task_ids:authorized_task(runtime,tid,r.peer_id)
            if hasattr(p,'memory_id'):get_memory(runtime,p.memory_id,r.peer_id)
        if r.operation.startswith('review.'):
            runtime.require_role('student')
            if hasattr(p,'card_id'):get_card(runtime,p.card_id)
            if hasattr(p,'task_id'):authorized_task(runtime,p.task_id)
        if hasattr(p,'task_id') and p.task_id:authorized_task(runtime,p.task_id,r.peer_id)
        if hasattr(p,'source') and isinstance(p.source,Source) and p.source.task_id:authorized_task(runtime,p.source.task_id,r.peer_id)
    authorize()
    writes=r.operation in ['page.save','activity.create','memory.capture','memory.correct','memory.visibility','review.create','review.record','review.adjust']
    def prepare():
        if r.operation=='page.save':
            if not p.title.strip() or not p.source.strip():raise ValueError('原图标题和来源不能为空')
            raw,meta=decode_original(p.data_base64)
            pid=p.page_id or uuid4().hex
            with runtime.db() as db:head=db.execute('SELECT MAX(revision) FROM companion_pages WHERE id=?',(pid,)).fetchone()[0]
            if p.page_id and (head is None or head!=p.expected_revision):raise ValueError('原图版本已变化，请重新打开')
            return {'id':pid,'revision':(head or 0)+1,'title':p.title.strip(),'source':p.source.strip(),'caption':p.caption,
                'caption_role':'user_supplied_not_verified','created':now(),'owner_ref':'device:'+runtime.identity.id,
                **meta,'data_base64':base64.b64encode(raw).decode()}
        if r.operation=='activity.create':
            plan,value=policy_plan(runtime,p,r.peer_id)
            if plan['status'] in ['needs_input','blocked']:raise ValueError('规则检查未通过：'+ '；'.join(x['decision'] for x in plan['decisions'] if x['status'] in ['needs_input','blocked']))
            if value['kind']=='audio':raise ValueError('此处设计结果可审阅；音频任务请从现有已审核听力题包布置，不能丢失配套录音')
            if value['kind']=='text':
                m=value['material'];title=m['title'];text=m['selection'];source=m['source'];ref=m['selection_ref'];original=None
                if len(text)>12000:raise ValueError('一次活动资料不超过12000字')
            else:
                original=value['page'];title=original['title'];source=original['source'];ref=original['source_ref']
                text='本次依据是绑定版本的原图。附注仅为用户提供，未经OCR或专业核验。\n'+original.get('caption','')
            companion={'scenario_id':p.scenario,'version':'2.0.0','validation':'candidate_not_domain_validated',
                **{k:plan[k] for k in ['goal','method','method_id','name','rationale','operation','criteria','question','obstacle_hypothesis','normal_conditions','learner_responsibility','verification','policy_refs']},
                'source_ref':ref,'runtime_policy':plan}
            target=runtime.service.public_person(runtime.peer(r.peer_id)['learner_id'] if runtime.role=='teacher' else runtime.profile['learner_id'])
            pack={'id':'companion-'+uuid4().hex,'family_id':ref.get('material_id',ref.get('page_id',ref.get('task_id'))),
                'title':title,'purpose':'reading','exam':target['exam'],'stage':target['stage'],
                'task_type':'source_response','instructions':plan['question'],'stimulus':text,'items':[],'audio':None,
                'source':{'kind':'original_page' if original else 'user_material','title':source},'companion_plan':companion}
            if original:pack['source_page']=original
            draft={'name':'超维伴学','activity_title':title,'goal':p.goal,'deliverable':plan['operation'],'instructions':plan['question'],
                'material':text,'criteria':'；'.join(plan['criteria']),'next_step':plan['verification'],'mode':'text','assessment_version':'policy-runtime-0.3','growth':pack}
            return {'draft':draft,'plan':plan}
        if r.operation=='memory.capture':
            refs=[];lines=[]
            for tid in dict.fromkeys(p.task_ids):
                task,ref=anchor(runtime,tid,r.peer_id);a=task['attempts'][-1];refs.append(ref)
                lines.extend(['任务：'+task['pack']['title'],'本人作品片段：'+a['answer'].get('text','逐题作答或附件作品')[:450],
                    '本次反馈：'+a.get('evaluation',{}).get('comment','尚无评价')[:400],
                    '下一步：'+a.get('evaluation',{}).get('next_step','待确定')[:300],
                    '帮助条件：'+str(a['answer'].get('learning_conditions',{}).get('additional_help','未说明'))[:150]])
            return {'id':uuid4().hex,'revision':1,'scope':scope(runtime,r.peer_id),'created':now(),'title':p.title,
                'body':'\n'.join(lines)[:3000],'source_refs':refs,'authorship':'bounded_source_extract',
                'allow_for_model':True,'hidden':False,'policy_refs':['P02-R1','P08-R2','P10-R1'],'mastery':'not_inferred'}
        if r.operation in ['memory.correct','memory.visibility']:
            old=get_memory(runtime,p.memory_id,r.peer_id)
            if r.operation=='memory.correct' and not p.body.strip():raise ValueError('修订内容不能为空')
            if r.operation=='memory.correct' and p.expected_revision!=old['revision']:raise ValueError('札记已更新，请重新打开')
            return {**old,'revision':old['revision']+1,'updated':now(),**({'body':p.body,'authorship':'user_corrected_statement',
                'allow_for_model':p.allow_for_model} if r.operation=='memory.correct' else {'hidden':p.hidden})}
        if r.operation=='review.create':
            task,ref=anchor(runtime,p.task_id)
            if task['state']!='active':raise ValueError('先恢复原任务，再安排复习')
            # One active personal card per task, not an accidental pile from repeated clicks.
            with runtime.db() as db:rows=db.execute('SELECT body FROM companion_review_cards').fetchall()
            if any(json.loads(x['body'])['task_id']==p.task_id for x in rows):raise ValueError('这个任务已有复习卡，请调整现有安排')
            return {'id':uuid4().hex,'revision':1,'task_id':p.task_id,'title':task['pack']['title'],
                'source_ref':ref,'prompt':p.prompt or '先不看旧答案，重新解释本次要点，再打开原任务核对。',
                'intervals':p.intervals,'step':0,'due_at':(datetime.now(timezone.utc)+timedelta(days=p.intervals[0])).isoformat(),
                'paused':False,'created':now(),'policy_refs':['P09-R1','P10-R1'],'mastery':'not_inferred'}
        if r.operation in ['review.record','review.adjust']:
            old,task=get_card(runtime,p.card_id)
            if p.expected_revision!=old['revision']:raise ValueError('复习安排已更新，请刷新后再操作')
            if task['state']!='active' and r.operation=='review.record':raise ValueError('原任务已暂停或归档，不能新增复习尝试')
            updated={**old,'revision':old['revision']+1,'updated':now()}
            if r.operation=='review.record':
                if not p.response.strip():raise ValueError('请先记录本次回忆或再用的结果')
                if old['paused']:raise ValueError('复习卡已暂停，请先恢复')
                step=min(len(old['intervals'])-1,old['step']+1) if p.rating=='good' else 0 if p.rating=='again' else old['step']
                days=old['intervals'][step] if p.rating=='good' else 1 if p.rating=='again' else max(1,old['intervals'][step]//2)
                # Refresh the card's evidence anchor after a newly submitted source revision.
                _,ref=anchor(runtime,old['task_id']);updated.update(step=step,source_ref=ref,due_at=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat())
                if p.additional_help not in ['没有额外帮助','none','No additional help']:days=min(days,2);updated['due_at']=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat()
                detail={'kind':'self_reported_retrieval','response':p.response,'rating':p.rating,'additional_help':p.additional_help,
                    'interval_days':days,'meaning':'本人回忆难度声明，仅用于本次可调安排；不是教师达标判断'}
            else:
                if p.paused is not None:updated['paused']=p.paused
                if p.days_from_now is not None:updated['due_at']=(datetime.now(timezone.utc)+timedelta(days=p.days_from_now)).isoformat()
                detail={'kind':'user_schedule_adjustment','paused':updated['paused'],'due_at':updated['due_at']}
            return {'id':uuid4().hex,'card_id':old['id'],'expected_revision':old['revision'],'created':now(),
                'detail':detail,'card_after':updated,'policy_trace':{'rule':'P09-R1','basis':'user_configured_intervals_and_self_report','mastery_updated':False}}
    def apply(body):
        authorize()
        if r.operation=='page.save':
            raw=base64.b64decode(body['data_base64']);check_original(raw,body['source_hash'])
            folder=runtime.folder/'uploads';folder.mkdir(exist_ok=True);path=folder/('page-'+body['source_hash'])
            if path.exists():check_original(path.read_bytes(),body['source_hash'])
            else:
                with path.open('xb') as f:f.write(raw)
            value={k:v for k,v in body.items() if k!='data_base64'}
            with runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                previous=db.execute('SELECT body FROM companion_pages WHERE id=? AND revision=?',(body['id'],body['revision'])).fetchone()
                if previous and json.loads(previous['body'])!=value:raise ValueError('原图版本冲突')
                head=db.execute('SELECT MAX(revision) FROM companion_pages WHERE id=?',(body['id'],)).fetchone()[0]
                if not previous and (head or 0)!=body['revision']-1:raise ValueError('原图已经更新')
                db.execute('INSERT OR IGNORE INTO companion_pages VALUES (?,?,?)',(body['id'],body['revision'],json.dumps(value,ensure_ascii=False)))
            return {'page':value}
        if r.operation=='activity.create':
            learner=runtime.peer(r.peer_id)['learner_id'] if runtime.role=='teacher' else runtime.profile['learner_id']
            person=runtime.service.public_person(learner)
            receipt=runtime.service.base.create(person['name'],body['draft'],'continuity:'+r.request_id,learner_id=learner);tid=receipt['id']
            if runtime.role=='teacher':
                with runtime.db() as db:db.execute('INSERT OR IGNORE INTO local_task_links VALUES (?,?)',(tid,r.peer_id))
                with runtime.db() as db:existing=db.execute('SELECT 1 FROM local_outbox WHERE id=?',('assign-'+tid,)).fetchone()
                if not existing:runtime.queue(r.peer_id,'task.assigned',{'task':runtime.service.session(tid)},event_id='assign-'+tid)
            return {'task_id':tid,'plan':body['plan'],'delivery':'queued_for_peer' if runtime.role=='teacher' else 'local'}
        if r.operation.startswith('memory.'):
            with runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                old=db.execute('SELECT body FROM companion_memory_versions WHERE id=? AND revision=?',(body['id'],body['revision'])).fetchone()
                head=db.execute('SELECT MAX(revision) FROM companion_memory_versions WHERE id=?',(body['id'],)).fetchone()[0]
                if old and json.loads(old['body'])!=body:raise ValueError('札记版本冲突')
                if not old and (head or 0)!=body['revision']-1:raise ValueError('札记已被其他操作更新')
                db.execute('INSERT OR IGNORE INTO companion_memory_versions VALUES (?,?,?,?)',(body['id'],body['revision'],body['scope'],json.dumps(body,ensure_ascii=False)))
            return {'entry':body}
        if r.operation=='review.create':
            with runtime.db() as db:
                db.execute('BEGIN IMMEDIATE')
                rows=db.execute('SELECT id,body FROM companion_review_cards').fetchall()
                if any(json.loads(x['body'])['task_id']==body['task_id'] and x['id']!=body['id'] for x in rows):raise ValueError('该任务已有复习安排')
                db.execute('INSERT OR IGNORE INTO companion_review_cards VALUES (?,?,?)',(body['id'],body['revision'],json.dumps(body,ensure_ascii=False)))
            return {'card':body}
        with runtime.db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT body FROM companion_review_events WHERE id=?',(body['id'],)).fetchone()
            if existing:return {'event':json.loads(existing['body'])}
            updated=db.execute('UPDATE companion_review_cards SET revision=?,body=? WHERE id=? AND revision=?',
                (body['card_after']['revision'],json.dumps(body['card_after'],ensure_ascii=False),body['card_id'],body['expected_revision']))
            if updated.rowcount!=1:raise ValueError('复习卡已经更新，请刷新')
            db.execute('INSERT INTO companion_review_events VALUES (?,?,?)',(body['id'],body['card_id'],json.dumps(body,ensure_ascii=False)))
        return {'event':body}
    if writes:data=transact(runtime,r,prepare,apply)
    elif r.operation=='policy.catalog':data={'packs':catalog(),'methods':{k:{'id':v[0],'name':v[1],'rationale':v[2]} for k,v in METHODS.items()},'scenarios':SCENES}
    elif r.operation=='policy.plan':data={'plan':policy_plan(runtime,p,r.peer_id)[0]}
    elif r.operation=='policy.task':data={'plan':authorized_task(runtime,p.task_id,r.peer_id)['pack'].get('companion_plan',{}).get('runtime_policy'),'legacy_not_backfilled':True}
    elif r.operation=='page.list':
        with runtime.db() as db:rows=db.execute('SELECT body FROM companion_pages p WHERE revision=(SELECT MAX(revision) FROM companion_pages WHERE id=p.id) ORDER BY rowid DESC').fetchall()
        data={'pages':[json.loads(x['body']) for x in rows]}
    elif r.operation=='page.read':data=page(runtime,p,r.peer_id,p.include_image)
    elif r.operation=='memory.list':data=memories(runtime,r.peer_id,p.include_hidden)
    else:data=review_list(runtime,p.include_paused)
    status='completed'
    if r.operation=='policy.plan' and data['plan']['status'] in ['needs_input','blocked']:status='needs_input' if data['plan']['status']=='needs_input' else 'needs_review'
    return ContinuityResult(request_id=r.request_id,operation=r.operation,status=status,data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'policy_runtime':'0.3.0','actor':runtime.role,
            'professional_validation':'NOT_REVIEWED','mastery_updated':False},
        **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if writes else {})).model_dump(mode='json',exclude_none=True)

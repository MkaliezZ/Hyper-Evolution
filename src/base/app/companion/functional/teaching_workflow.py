"""Teacher workflow Harness. Composes existing routes, review and signed delivery."""
import copy
from base.core import now
from base.app.companion.aesthetic.teaching_workflow import (
    POLICY, catalog, lexical_check, scope_signature, validate_blueprint, fallback_questions)
from base.app.companion.aesthetic.academic import check_reviews
from base.app.companion.assets.references import digest
from base.app.companion.assets.academic import seal, question_fingerprint
from base.app.companion.assets.teaching_workflow import ref, review_dependencies, export_item, extract_curriculum
from base.app.companion.functional.teaching_contracts import TeachingRequest, TeachingResult, PAYLOADS
from base.app.companion.functional import academic, academic_store as store
from base.app.companion.functional.study_store import transact

READS={'workflow.catalog','roster.list','roster.resolve','curriculum.list','lexical.check','blueprint.read',
       'workflow.resume','bank.list','prep.list','goal.list','goal.history','report.read','class.report','class.evidence'}
DRAFT_OPS={'blueprint.save','draft.patch','draft.review_items','draft.finalize_review','bank.export','goal.bind','workflow.merge'}
KINDS={'roster.save':'roster','prep.state':'prep','goal.save':'goal'}

def rows(runtime,kind,peer=None):
    return [v for v in store.rows(runtime,'workflow_'+kind) if v.get('peer_id')==peer]

def get(runtime,kind,id,peer=None,revision=None):
    v=store.get(runtime,'workflow_'+kind,id,revision)
    if v.get('peer_id')!=peer:raise PermissionError('记录不属于当前学生范围')
    return v

def child(runtime,r,op,payload,peer=None,tag=None,version='v7'):
    return runtime.invoke_capability({'contract_version':'companion.capability.'+version,
        'request_id':'wf-'+digest([r.request_id,tag or op,peer]),'operation':op,
        'peer_id':r.peer_id if peer is None else peer,'payload':payload})['data']

def authorize(runtime,r,p):
    runtime.require_role('teacher')
    if r.peer_id:academic.check_peer(runtime,r.peer_id)
    if hasattr(p,'route_id'):academic.route(runtime,p.route_id,r.peer_id,False)
    if r.operation in DRAFT_OPS or r.operation in ['workflow.resume','blueprint.read']:
        academic.read(runtime,'draft',p.id,r.peer_id)
    if r.operation=='roster.save' and p.peer_id:academic.check_peer(runtime,p.peer_id)
    if r.operation.startswith('class.'):
        if r.operation in ['class.report','class.assign']:
            c=store.get(runtime,'class',p.id)
            for peer in c['peers']:academic.check_peer(runtime,peer)
        if r.operation=='class.assign':
            for m in p.mappings:academic.route(runtime,m.route_id,m.peer_id)
    if r.operation=='publication.withdraw':
        academic.authorized_task(runtime,p.task_id,r.peer_id)
        if p.replacement_task_id:academic.authorized_task(runtime,p.replacement_task_id,r.peer_id)

def snapshot(runtime,r,p):
    plan={'created':now(),'old':None}
    if r.operation in DRAFT_OPS:
        d=academic.current_draft(runtime,p.id,r.peer_id)
        if d['revision']!=p.expected_revision:raise ValueError('草稿已更新，请刷新后继续')
        plan['draft']=d
    if r.operation=='workflow.merge':plan['merge_source']=academic.current_draft(runtime,p.source_draft_id,r.peer_id)
    if r.operation=='workflow.prepare':plan['preparation']=prepare_questions(runtime,r,p)
    kind=KINDS.get(r.operation)
    if kind and getattr(p,'id',None):
        old=get(runtime,kind,p.id,r.peer_id if kind!='roster' else None)
        if old['revision']!=p.expected_revision:raise ValueError('记录已更新，请刷新版本')
        plan['old']=old
    elif kind and getattr(p,'expected_revision',0):raise ValueError('新记录的预期版本须为0')
    if r.operation=='bank.retire':plan['old']=get(runtime,'bank',p.id)
    if r.operation=='class.assign':
        from base.app.companion.functional.teaching_reports import prepare_class
        plan.update(prepare_class(runtime,r,p))
    return plan

def save(runtime,r,plan,kind,content,peer=None,old=None,tag=None):
    value=seal({'id':old['id'] if old else 'wf-'+kind+'-'+digest([r.request_id,tag or kind])[:24],
        'revision':old['revision']+1 if old else 1,'peer_id':peer,'created':plan['created'],**content})
    return store.save(runtime,'workflow_'+kind,value)

def review_state(runtime,d,peer):
    deps=review_dependencies(d);accepted={};source={}
    # Full human reviews and previous retained per-item records are both immutable.
    for review in reversed(store.rows(runtime,'draft_review',peer)):
        if review['draft_id']!=d['id']:continue
        old=next((v for revision in range(d['revision'],0,-1)
            if (v:=academic.read(runtime,'draft',d['id'],peer,revision))['content_hash']==review['draft_hash']),None)
        if not old:continue
        olddeps=review_dependencies(old)
        for q in review['questions']:
            qid=q['question_id']
            if deps.get(qid)==olddeps.get(qid):accepted[qid]=q;source[qid]=ref(review)
    for record in reversed(rows(runtime,'item_reviews',peer)):
        if record['draft_id']!=d['id']:continue
        for item in record['items']:
            qid=item['review']['question_id']
            if deps.get(qid)==item['dependency_hash']:accepted[qid]=item['review'];source[qid]=ref(record)
    return {'accepted':accepted,'sources':source,'pending':[q['id'] for q in d['body']['questions'] if q['id'] not in accepted],
            'dependencies':deps}

def available_bank(runtime,rr,scopes,focus=None,peer=None):
    used=academic.seen(runtime,peer);allowed={digest(scope_signature(s)) for s in scopes};found=[];unique=set()
    for item in rows(runtime,'bank'):
        if item.get('retired') or (item['level'],item['grade'])!=(rr['level'],rr['grade']):continue
        if any(digest(s) not in allowed for s in item['scope_specs']):continue
        q=item['question'];fp=question_fingerprint(q)
        if focus and q['skill']!=focus or fp in used or fp in unique:continue
        unique.add(fp);found.append({'question':q,'bank_ref':ref(item),'fingerprint':fp,'source':item['source']})
    # Existing student-scoped reviewed bank remains usable; no new duplicate library.
    for d in academic.bank(runtime,rr['id'],peer):
        if d['body'].get('audio_id'):continue  # Audio activities keep their existing whole-pack reuse path.
        if any(x['id'] not in {s['id'] for s in scopes} for x in d['scope_refs']):continue
        for q in d['body']['questions']:
            fp=question_fingerprint(q)
            if focus and q['skill']!=focus or fp in used or fp in unique:continue
            unique.add(fp);found.append({'question':q,'draft_ref':ref(d),'fingerprint':fp,'source':d['body']['source']})
    return found

def prepare_questions(runtime,r,p):
    peer=r.peer_id;rr=academic.route(runtime,p.route_id,peer);scopes=academic.refs(runtime,p.scope_ids,rr['id'],peer)
    candidates=available_bank(runtime,rr,scopes,p.focus,peer);excluded=set()
    if p.exclude_draft_id:
        other=academic.read(runtime,'draft',p.exclude_draft_id,peer)
        excluded={question_fingerprint(q) for q in other['body']['questions']}
    selected=[x for x in candidates if x['fingerprint'] not in excluded][:p.count]
    questions=[{**x['question'],'id':'q'+str(i+1)} for i,x in enumerate(selected)]
    bank_selected=len(questions);used=academic.seen(runtime,peer)|excluded|{question_fingerprint(q) for q in questions}
    sources=[x['source'] for x in selected]
    if len(questions)<p.count and p.use_fallback:
        for q in fallback_questions(p.focus,24,rr['grade']):
            fp=question_fingerprint(q)
            if fp in used:continue
            used.add(fp);questions.append({**q,'id':'q'+str(len(questions)+1)})
            sources.append('团队原创基础练习族 v1；候选待人工审校')
            if len(questions)==p.count:break
    return {'route':rr,'scopes':scopes,'questions':questions,'sources':sources,'bank_selected':bank_selected}

def invoke(runtime,raw):
    runtime.require_role('teacher')
    try:
        r=TeachingRequest.model_validate(raw)
        if r.operation not in PAYLOADS:raise ValueError('未知教学工作流操作')
        p=PAYLOADS[r.operation].model_validate(r.payload)
    except ValueError:raise ValueError('v10 教学工作流请求无效，请按教学契约核对字段、版本和确认项') from None
    store.initialize(runtime);authorize(runtime,r,p)
    if r.operation=='class.assign':
        frozen=transact(runtime,r,lambda:snapshot(runtime,r,p),lambda plan:{'plan':plan})['plan']
        data=execute(runtime,r,p,frozen)
    else:
        data=execute(runtime,r,p,{'created':now()}) if r.operation in READS else transact(runtime,r,
            lambda:snapshot(runtime,r,p),lambda plan:execute(runtime,r,p,plan))
    authorize(runtime,r,p)  # Replayed receipts also require current pair authorization.
    return TeachingResult(request_id=r.request_id,operation=r.operation,
        status='partial' if data.get('partial') else 'completed',data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'policy_ref':POLICY,
                        'professional_validation':'NOT_REVIEWED'},
        **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if r.operation not in READS else {})).model_dump(mode='json',exclude_none=True)

def execute(runtime,r,p,plan):
    op=r.operation;peer=r.peer_id
    if op=='workflow.catalog':return catalog()
    if op=='roster.list':return {'records':rows(runtime,'roster')}
    if op=='roster.resolve':
        query=p.query.strip().casefold();matches=[v for v in rows(runtime,'roster') if query in {x.casefold() for x in [v['name'],*v['aliases'],v['id']]}]
        return {'matches':matches,'state':'resolved' if len(matches)==1 else 'ambiguous' if matches else 'not_found',
                'selection_required':len(matches)!=1}
    if op=='roster.save':
        name=p.name.strip();aliases=list(dict.fromkeys(x.strip() for x in p.aliases if x.strip()))
        if not name or any(len(x)>80 for x in aliases):raise ValueError('姓名或别名需为1—80字')
        own_id=(plan.get('old') or {}).get('id') or 'wf-roster-'+digest([r.request_id,'roster'])[:24]
        others=[v for v in rows(runtime,'roster') if v['id']!=own_id]
        keys={x.casefold() for x in [name,*aliases]}
        if any(keys&{x.casefold() for x in [v['name'],*v['aliases']]} for v in others):raise ValueError('姓名或别名有重名，请加班级等区别信息')
        if p.peer_id and any(v.get('paired_peer_id')==p.peer_id for v in others):raise ValueError('这台学生设备已关联另一份预登记档案')
        value=save(runtime,r,plan,'roster',{'name':name,'aliases':aliases,'note':p.note,'paired_peer_id':p.peer_id},old=plan.get('old'))
        return {'record':value,'state':'paired' if p.peer_id else 'pre_registered'}
    if op=='curriculum.preview':
        value=p.model_dump()
        if len({u.order for u in p.units})!=len(p.units):raise ValueError('单元顺序号不能重复')
        return {'record':save(runtime,r,plan,'curriculum_preview',value|{'status':'needs_teacher_review'})}
    if op=='curriculum.extract':
        extracted=extract_curriculum(p.text)
        # Run the same typed limits as manual/imported catalog entries.
        from base.app.companion.functional.teaching_contracts import CatalogPreview
        CatalogPreview.model_validate({'title':p.title,'source':p.source,'units':extracted['units']})
        return {'record':save(runtime,r,plan,'curriculum_preview',{'title':p.title,'source':p.source,
            **extracted,'status':'needs_teacher_review'})}
    if op=='curriculum.commit':
        v=get(runtime,'curriculum_preview',p.id)
        if v['revision']!=p.expected_revision or v['content_hash']!=p.content_hash:raise ValueError('教材预览版本不一致')
        return {'record':save(runtime,r,plan,'curriculum',{k:v[k] for k in ['title','source','units']}|
            {'reviewed':True,'preview_ref':ref(v),'quality':'teacher_declared',
             **{k:v[k] for k in ['source_text_hash','line_refs','extraction_method','unparsed_lines'] if k in v}})}
    if op=='curriculum.list':return {'records':rows(runtime,'curriculum')}
    if op=='curriculum.apply':
        rr=academic.route(runtime,p.route_id,peer);v=get(runtime,'curriculum',p.catalog_id,revision=p.catalog_revision)
        selected=[u for u in v['units'] if u['order'] in p.unit_orders]
        if len(selected)!=len(set(p.unit_orders)):raise ValueError('教材目录不含所选单元')
        if any(u['order']>rr['scope_order'] for u in selected):raise ValueError('先调整当前路线的实际进度，再应用后续单元')
        records=[]
        for u in selected:
            body={'route_id':rr['id'],'textbook':v['title'],'source':v['source'],'content_reviewed':True,**u}
            existing=next((s for s in store.rows(runtime,'scope',peer) if s['route_id']==rr['id'] and not s.get('material_ref')
                           and scope_signature(s)==scope_signature(body)),None)
            records.append(existing or child(runtime,r,'scope.save',body,tag='scope-'+str(u['order']))['record'])
        return {'records':records,'catalog_ref':ref(v)}
    if op=='lexical.check':return {'check':lexical_check(p.text,academic.refs(runtime,p.scope_ids,p.route_id,peer),p.exemptions,p.proper_names)}
    if op=='workflow.resume':
        d=academic.current_draft(runtime,p.id,peer);state=review_state(runtime,d,peer)
        preparation=next((v for v in rows(runtime,'preparation',peer) if v.get('draft_ref',{} ) and v['draft_ref']['id']==d['id']),None)
        return {'draft':d,'review_state':state,'next_action':'review_pending_items' if state['pending'] else 'confirm_complete_review',
                'preparation':preparation,'missing_generation':max(0,preparation['requested']-len(d['body']['questions'])) if preparation else 0,
                'model_generation_entry':'/api/local/jobs (k12_workflow)','human_publication_required':True}
    if op=='blueprint.save':
        d=plan['draft'];check=validate_blueprint(d['body'],[s.model_dump() for s in p.sections])
        return {'record':save(runtime,r,plan,'blueprint',{'draft_id':d['id'],'draft_ref':ref(d),'template':p.template,**check},peer)}
    if op=='blueprint.read':
        d=academic.read(runtime,'draft',p.id,peer)
        values=[x for x in rows(runtime,'blueprint',peer) if x['draft_id']==p.id]
        v=values[0] if values else None
        return {'record':v,'current':bool(v and v['draft_ref']==ref(d))}
    if op=='draft.patch':
        d=plan['draft'];updates={q.id:q.model_dump() for q in p.questions}
        if len(updates)!=len(p.questions) or set(updates)-{q['id'] for q in d['body']['questions']}:raise ValueError('局部重做须对应现有题号且不重复')
        body=copy.deepcopy(d['body']);body['questions']=[updates.get(q['id'],q) for q in body['questions']]
        new=child(runtime,r,'k12.draft.save',{'id':d['id'],'expected_revision':d['revision'],'route_id':d['route_id'],'body':body})['record']
        return {'record':new,'review_state':review_state(runtime,new,peer),'patched':list(updates)}
    if op=='workflow.merge':
        d=plan['draft'];source=plan['merge_source']
        if source['id']==d['id'] or source['route_ref']!=d['route_ref'] or sorted(source['scope_refs'],key=lambda s:s['id'])!=sorted(d['scope_refs'],key=lambda s:s['id']):raise ValueError('合并候选须来自同一路线与同一范围版本')
        if d['body'].get('audio_id')!=source['body'].get('audio_id'):raise ValueError('不同录音不能直接合并')
        body=copy.deepcopy(d['body']);used={question_fingerprint(q) for q in body['questions']}
        additions=[]
        for q in source['body']['questions']:
            if question_fingerprint(q) in used:continue
            used.add(question_fingerprint(q));additions.append({**q,'id':'q'+str(len(body['questions'])+len(additions)+1)})
        if not additions:raise ValueError('补题候选均已存在，请更换情境后重试')
        body['questions']+=additions;body['source']=(body['source']+'；'+source['body']['source'])[:1000]
        new=child(runtime,r,'k12.draft.save',{'id':d['id'],'expected_revision':d['revision'],'route_id':d['route_id'],'body':body})['record']
        provenance=save(runtime,r,plan,'merge',{'draft_ref':ref(new),'source_ref':ref(source),
            'added_question_ids':[q['id'] for q in additions]},peer)
        return {'record':new,'provenance':provenance,'review_state':review_state(runtime,new,peer)}
    if op=='draft.review_items':
        d=plan['draft'];ids=[q.question_id for q in p.questions]
        if len(set(ids))!=len(ids) or set(ids)-{q['id'] for q in d['body']['questions']}:raise ValueError('审题须对应现有题号且不重复')
        sub={**d['body'],'questions':[q for q in d['body']['questions'] if q['id'] in ids]}
        check_reviews(sub,[q.model_dump() for q in p.questions]);deps=review_dependencies(d)
        if d['body'].get('audio_id') and not p.audio_listened:raise ValueError('含录音须先实际试听')
        value=save(runtime,r,plan,'item_reviews',{'draft_id':d['id'],'draft_ref':ref(d),
            'items':[{'dependency_hash':deps[q.question_id],'review':q.model_dump()} for q in p.questions],
            'audio_listened':p.audio_listened,'resolution_note':p.resolution_note},peer)
        return {'record':value,'review_state':review_state(runtime,d,peer)}
    if op=='draft.finalize_review':
        d=plan['draft'];state=review_state(runtime,d,peer)
        if state['pending']:raise ValueError('尚有题目待审：'+','.join(state['pending']))
        result=child(runtime,r,'k12.draft.review',{'id':d['id'],'expected_revision':d['revision'],'draft_hash':d['content_hash'],
            'questions':[state['accepted'][q['id']] for q in d['body']['questions']],
            'human_review_confirmed':True,'audio_listened':p.audio_listened,'resolution_note':p.resolution_note})
        return {**result,'retained_review_sources':state['sources']}
    if op=='bank.export':
        d=plan['draft'];rr=academic.route(runtime,d['route_id'],peer)
        if not any(x['draft_hash']==d['content_hash'] for x in store.rows(runtime,'draft_review',peer)):raise ValueError('先完成整份人工审校再加入教师题库')
        if d['body'].get('audio_id'):raise ValueError('带录音活动请通过现有已审题库整份复用，避免丢失音频配套关系')
        scopes=academic.refs(runtime,d['body']['scope_ids'],rr['id'],peer);result=[]
        existing={x['question_hash']:x for x in rows(runtime,'bank') if not x.get('retired')}
        for q in d['body']['questions']:
            value=export_item(q,p.reuse_source,[scope_signature(s) for s in scopes],rr['level'],rr['grade'])
            result.append(existing.get(value['question_hash']) or save(runtime,r,plan,'bank',value|{'retired':False},tag=q['id']))
        return {'records':result,'student_records_exported':False}
    if op=='bank.list':return {'records':rows(runtime,'bank')}
    if op=='bank.retire':
        old=plan['old'];return {'record':save(runtime,r,plan,'bank',{k:v for k,v in old.items() if k not in ['id','revision','created','content_hash','peer_id']}|
            {'retired':True,'retirement_reason':p.reason},old=old)}
    if op=='workflow.prepare':
        frozen=plan['preparation'];rr=frozen['route'];scopes=frozen['scopes'];questions=frozen['questions']
        sources=frozen['sources'];bank_selected=frozen['bank_selected']
        missing=p.count-len(questions);d=None
        if questions:
            body={'title':p.focus+' · 待审候选','instructions':'按题目给定条件独立完成。','goal':p.focus,
                'source':'；'.join(dict.fromkeys(sources))[:1000],'questions':questions,'criteria':['按当前题目条件核对作答'],
                'scope_ids':p.scope_ids}
            d=child(runtime,r,'k12.draft.save',{'route_id':rr['id'],'body':body})['record']
        scope_check=lexical_check('\n'.join(q['material'] for q in questions),scopes) if questions and scopes else None
        value=save(runtime,r,plan,'preparation',{'route_ref':ref(rr),'focus':p.focus,'requested':p.count,
            'draft_ref':ref(d) if d else None,'missing':missing,'bank_selected':bank_selected,
            'next_action':'generate_missing_then_review' if missing else 'review_candidate'},peer)
        return {'record':value,'draft':d,'missing':missing,'partial':bool(missing),'scope_check':scope_check,
            'model_request':{'mode':'k12_generate','peer_id':peer,'route_id':rr['id'],'scope_ids':p.scope_ids,
                'count':min(missing,10),'prompt':f'围绕{p.focus}补{missing}道原创候选题；避免已有题目。'} if missing else None}
    if op=='prep.forecast':
        rr=academic.route(runtime,p.route_id,peer);scopes=[academic.read(runtime,'scope',id,peer) for id in p.scope_ids]
        if len({s['id'] for s in scopes})!=len(scopes) or any(s['route_id']!=rr['id'] for s in scopes):raise ValueError('备课范围须属于本路线且不重复')
        values=[]
        for s in scopes:
            for skill in dict.fromkeys(p.skills):
                stock=len(available_bank(runtime,rr,[s],skill,peer));missing=max(0,p.count_per_skill-stock)
                values.append(save(runtime,r,plan,'prep',{'route_id':rr['id'],'scope_ref':ref(s),'skill':skill,
                    'requested':p.count_per_skill,'available':stock,'missing':missing,'due_date':p.due_date,
                    'state':'planned' if missing else 'done','progress_advanced':False},peer,tag=s['id']+skill))
        return {'records':values,'progress_advanced':False,'background_generation':False}
    if op=='prep.list':return {'records':[v for v in rows(runtime,'prep',peer) if v['route_id']==p.route_id]}
    if op=='prep.state':
        old=plan['old'];return {'record':save(runtime,r,plan,'prep',{k:v for k,v in old.items() if k not in ['id','revision','created','content_hash','peer_id']}|
            {'state':p.state},peer,old=old)}
    from base.app.companion.functional.teaching_reports import execute as extra
    return extra(runtime,r,p,plan)

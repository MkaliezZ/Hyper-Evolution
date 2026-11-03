import asyncio,copy,json
from pathlib import Path
from uuid import uuid4
import pytest
from test_academic import setup,call,review,reviews,publish,submit,route,body
from test_local_runtime import instance,pair,drain
from base.app.companion.functional.teaching_contracts import TeachingRequest,TeachingResult,PAYLOADS

def wf(runtime,operation,payload=None,peer=None,key=None):
    return runtime.invoke_capability({'contract_version':'companion.capability.v10','request_id':key or uuid4().hex,
        'operation':operation,'payload':payload or {},'peer_id':peer})['data']

def scope(t,s,r,words=None):
    return call(t,'scope.save',{'route_id':r['id'],'textbook':'原创课本','unit':'Unit 1','order':1,
        'source':'团队原创工程素材','words':words or ['I','be','a','student','child','run','library'],
        'complete':True,'content_reviewed':True},s.identity.id)['record']

def test_roster_preregistration_disambiguation_link_and_roles(tmp_path):
    t,s,r,b,d=setup(tmp_path)
    student=wf(t,'roster.save',{'name':'小林·七年级','aliases':['Lin7'],'note':'仅教师保留'},key='register')['record']
    assert student==wf(t,'roster.save',{'name':'小林·七年级','aliases':['Lin7'],'note':'仅教师保留'},key='register')['record']
    with pytest.raises(ValueError):wf(t,'roster.save',{'name':'另一位','aliases':['lin7']})
    assert wf(t,'roster.resolve',{'query':'LIN7'})['state']=='resolved'
    linked=wf(t,'roster.save',{'id':student['id'],'expected_revision':1,'name':student['name'],'aliases':student['aliases'],
        'peer_id':s.identity.id})['record']
    assert linked['paired_peer_id']==s.identity.id
    with pytest.raises(PermissionError):wf(s,'roster.list')

def test_curriculum_preview_review_reuse_and_conservative_lexical_check(tmp_path):
    t,s,r,b,d=setup(tmp_path);peer=s.identity.id
    preview=wf(t,'curriculum.preview',{'title':'原创课本','source':'团队原创工程素材',
        'units':[{'unit':'Unit 1','order':1,'words':['child','run','be','library'],'complete':True},
                 {'unit':'Unit 2','order':2,'words':['go']} ]})['record']
    with pytest.raises(ValueError):wf(t,'curriculum.commit',{'id':preview['id'],'expected_revision':1,'content_hash':'0'*64,'human_review_confirmed':True})
    book=wf(t,'curriculum.commit',{'id':preview['id'],'expected_revision':1,'content_hash':preview['content_hash'],'human_review_confirmed':True})['record']
    with pytest.raises(ValueError):wf(t,'curriculum.apply',{'route_id':r['id'],'catalog_id':book['id'],'catalog_revision':1,'unit_orders':[2]},peer)
    sc=wf(t,'curriculum.apply',{'route_id':r['id'],'catalog_id':book['id'],'catalog_revision':1,'unit_orders':[1]},peer)['records'][0]
    check=wf(t,'lexical.check',{'route_id':r['id'],'scope_ids':[sc['id']],
        'text':'Children were running. Alice visits a library. museum（博物馆）',
        'proper_names':['Alice'],'exemptions':['a','visits']},peer)['check']
    assert not check['unmatched_words'] and check['ok'] is True
    assert {x['match'] for x in check['matches']} >= {'irregular_inflection','regular_inflection','declared_proper_name','chinese_annotation'}
    assert check['source_refs'][0]['content_hash']==sc['content_hash']
    extracted=wf(t,'curriculum.extract',{'title':'导入词表','source':'合成教师原创词表',
        'text':'待核对的页眉\nUnit 1 Greeting\nWords: children 儿童, run 跑\nPhrases: look at\nGrammar: 主谓一致'})['record']
    assert extracted['units'][0]['words']==['children','run']
    assert extracted['unparsed_lines'][0]['line']==1 and not extracted['units'][0]['complete']
    assert extracted['source_text_hash'] and extracted['line_refs'][0]['line']==2

def test_partial_patch_retains_unaffected_human_review_and_dependencies(tmp_path):
    t,s,r,b,d=setup(tmp_path);peer=s.identity.id;review(t,s,b,d)
    changed=copy.deepcopy(d['body']['questions'][0]);changed['prompt']='Choose carefully: I ___ a student.'
    patched=wf(t,'draft.patch',{'id':d['id'],'expected_revision':1,'questions':[changed]},peer,key='patch')
    assert patched['record']==wf(t,'draft.patch',{'id':d['id'],'expected_revision':1,'questions':[changed]},peer,key='patch')['record']
    assert patched['review_state']['pending']==['q1'] and set(patched['review_state']['accepted'])=={'q2'}
    with pytest.raises(ValueError):wf(t,'draft.finalize_review',{'id':d['id'],'expected_revision':2,'human_review_confirmed':True},peer)
    item=reviews(patched['record']['body'])[0]
    wf(t,'draft.review_items',{'id':d['id'],'expected_revision':2,'questions':[item],'human_review_confirmed':True},peer)
    wf(t,'draft.finalize_review',{'id':d['id'],'expected_revision':2,'human_review_confirmed':True},peer)
    # Changing shared instructions invalidates both items, not just the patched question.
    body2=copy.deepcopy(patched['record']['body']);body2['instructions']='本轮请结合另一项条件作答。'
    call(t,'k12.draft.save',{'id':d['id'],'expected_revision':2,'route_id':r['id'],'body':body2},peer)
    assert wf(t,'workflow.resume',{'id':d['id']},peer)['review_state']['pending']==['q1','q2']

def test_bank_first_fallback_missing_and_seen_exclusion(tmp_path,monkeypatch):
    from base.app.companion.aesthetic.teaching_workflow import fallback_questions
    q=fallback_questions('be动词主谓一致',1,7)[0]
    answer=q['options'][ord(q['key'][0])-65]
    assert q['prompt'].removeprefix('Choose: ').replace('___',answer) not in q['material']
    assert fallback_questions('be动词主谓一致',1,3)[0]['prompt']!=q['prompt']
    t,s,r,b,d=setup(tmp_path);peer=s.identity.id;review(t,s,b,d)
    wf(t,'bank.export',{'id':d['id'],'expected_revision':1,'personal_content_checked':True,'reuse_source':'原创素材，可在本机教学复用'},peer)
    s2=instance(tmp_path/'s2','student','S2');pair(t,s2);r2=route(t,s2)
    prepared=wf(t,'workflow.prepare',{'route_id':r2['id'],'focus':'细节理解','count':4},s2.identity.id)
    assert len(prepared['draft']['body']['questions'])==4 and prepared['record']['bank_selected']==1 and prepared['missing']==0
    unknown=wf(t,'workflow.prepare',{'route_id':r2['id'],'focus':'修辞目的','count':3},s2.identity.id)
    assert unknown['draft'] is None and unknown['missing']==3 and unknown['model_request']['count']==3
    pub=publish(t,s,d);drain(t,s)
    own=wf(t,'workflow.prepare',{'route_id':r['id'],'focus':'细节理解','count':2,'use_fallback':False},peer)
    assert own['missing']==2  # Already assigned questions are excluded from both libraries.
    assert 'peer_id' not in wf(t,'bank.list')['records'][0]['question']
    # A crash after child draft save must recover the same selection even if stock changes.
    from base.app.companion.functional import academic_store
    s3=instance(tmp_path/'s3','student','S3');pair(t,s3);r3=route(t,s3)
    original_save=academic_store.save;lost=False
    def fail_once(runtime,kind,value):
        nonlocal lost
        if kind=='workflow_preparation' and not lost:
            lost=True;raise RuntimeError('injected after draft commit')
        return original_save(runtime,kind,value)
    monkeypatch.setattr(academic_store,'save',fail_once)
    payload={'route_id':r3['id'],'focus':'be动词主谓一致','count':1,'use_fallback':False}
    with pytest.raises(RuntimeError):wf(t,'workflow.prepare',payload,s3.identity.id,key='recover-selection')
    newer=copy.deepcopy(b);newer['questions']=newer['questions'][:1];newer['questions'][0]['prompt']='Choose carefully: I ___ a student.'
    newer_d=call(t,'k12.draft.save',{'route_id':r['id'],'body':newer},peer)['record'];review(t,s,newer,newer_d)
    wf(t,'bank.export',{'id':newer_d['id'],'expected_revision':1,'personal_content_checked':True,'reuse_source':'原创新增题目'},peer)
    recovered=wf(t,'workflow.prepare',payload,s3.identity.id,key='recover-selection')
    assert recovered['draft']['body']['questions'][0]['prompt']==b['questions'][0]['prompt']
    assert len(call(t,'k12.draft.list',{'route_id':r3['id']},s3.identity.id)['records'])==1

def test_blueprint_is_signed_to_student_and_bad_cover_rejected(tmp_path):
    t,s,r,b,d=setup(tmp_path);peer=s.identity.id
    section={'title':'综合练习','types':['grammar_mcq','reading_mcq'],'question_ids':['q1','q2'],'count':2,'points':2.0,'minutes':8}
    with pytest.raises(ValueError):wf(t,'blueprint.save',{'id':d['id'],'expected_revision':1,'sections':[{**section,'count':3}]},peer)
    wf(t,'blueprint.save',{'id':d['id'],'expected_revision':1,'sections':[section]},peer)
    review(t,s,b,d);pub=publish(t,s,d);drain(t,s)
    meta=s.task(pub['task_id'])['pack']['teaching_blueprint']
    assert meta['minutes']==8 and meta['total_points']==2 and not meta['official_score_conversion']
    assert 'key' not in s.task(pub['task_id'])['pack']['items'][0]

def test_future_prep_does_not_advance_progress_and_goal_retests_are_frozen(tmp_path):
    t,s,r,b,d=setup(tmp_path);peer=s.identity.id;sc=scope(t,s,r)
    forecast=wf(t,'prep.forecast',{'route_id':r['id'],'scope_ids':[sc['id']],
        'skills':['be动词主谓一致'],'count_per_skill':3,'due_date':'2026-11-05'},peer)
    assert forecast['records'][0]['missing']==3 and call(t,'route.read',{'route_id':r['id']},peer)['route']['scope_order']==1
    goal=wf(t,'goal.save',{'title':'主语与信息定位','outcomes':['语法','阅读'],'threshold':.8},peer)['record']
    wf(t,'goal.bind',{'id':d['id'],'expected_revision':1,'goal_id':goal['id'],'goal_revision':1,
        'outcomes':{'语法':['q1'],'阅读':['q2']},'coverage_note':'每项以一题检查，本次试行。','human_review_confirmed':True},peer)
    review(t,s,b,d);pub=publish(t,s,d,'target');submit(t,s,pub,{'q1':'A','q2':'A'},{'additional_help':'none'})
    history=wf(t,'goal.history',{'id':goal['id']},peer)['history']
    assert len(history)==1 and history[0]['results'][0]['outcomes'][0]['state']=='meets_this_target'
    with pytest.raises(ValueError):wf(t,'goal.bind',{'id':d['id'],'expected_revision':1,'goal_id':goal['id'],'goal_revision':1,
        'outcomes':{'语法':['q1'],'阅读':['q2']},'coverage_note':'已交后不能改预设目标。','human_review_confirmed':True},peer)
    parent=wf(t,'report.read',{'route_id':r['id'],'audience':'parent'},peer)
    assert len(parent['coverage'])==2 and 'evidence' not in parent and 'goal_histories' not in parent
    updated=wf(t,'goal.save',{'id':goal['id'],'expected_revision':1,'title':goal['title'],
        'outcomes':goal['outcomes'],'threshold':.9},peer)['record']
    assert not wf(t,'goal.history',{'id':updated['id']},peer)['history'][0]['current_goal_version']
    assert all(c['state']=='unmeasured' for c in wf(t,'report.read',{'route_id':r['id'],'audience':'parent'},peer)['coverage'])
    plan=wf(t,'report.weekly_plan',{'route_id':r['id'],'start_date':'2026-11-02'},peer)
    assert plan['published'] is False

def test_class_explicit_scope_mapping_and_retry_never_duplicates(tmp_path):
    t,s,r,b,d=setup(tmp_path);sc=scope(t,s,r);b['scope_ids']=[sc['id']]
    d=call(t,'k12.draft.save',{'route_id':r['id'],'body':b},s.identity.id)['record'];review(t,s,b,d)
    others=[]
    for i in range(2):
        student=instance(tmp_path/f's{i+2}','student',f'S{i+2}');pair(t,student);rr=route(t,student)
        ss=scope(t,student,rr,words=None if i==0 else ['wrong'])
        others.append((student,rr,ss))
    cl=call(t,'k12.class.save',{'title':'合成班级','peers':[x[0].identity.id for x in others]},None)['record']
    data={'id':cl['id'],'expected_revision':1,'source_draft_id':d['id'],'source_revision':1,
        'mappings':[{'peer_id':s2.identity.id,'route_id':rr['id'],'scope_ids':[ss['id']]} for s2,rr,ss in others],
        'human_review_confirmed':True}
    first=wf(t,'class.assign',data,key='mapped-batch');assert first['partial']
    success=next(e for e in first['batch']['entries'] if e.get('task_id'))['task_id']
    s3,rr,ss=others[1]
    call(t,'scope.save',{'id':ss['id'],'expected_revision':1,'route_id':rr['id'],
        **{k:sc[k] for k in ['textbook','unit','order','source','words','phrases','grammar','complete','content_reviewed']}},s3.identity.id)
    second=wf(t,'class.assign',data,key='mapped-batch');assert not second['partial']
    third=wf(t,'class.assign',data,key='mapped-batch');assert second==third
    assert success in [e['task_id'] for e in second['batch']['entries']]
    assert len(wf(t,'class.report',{'id':cl['id']})['rows'])==2

def test_withdrawal_retains_answers_and_is_signed(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d);pub=publish(t,s,d);submit(t,s,pub)
    wf(t,'publication.withdraw',{'task_id':pub['task_id'],'reason':'本次题组暂停使用，保留原答。','human_review_confirmed':True},s.identity.id)
    drain(t,s);task=s.task(pub['task_id']);assert task['state']=='archived' and len(task['attempts'])==1

def test_v10_contract_snapshots():
    root=Path(__file__).resolve().parents[1]/'docs/contracts'
    for kind,model in [('request',TeachingRequest),('result',TeachingResult)]:
        assert json.loads((root/f'companion.capability.v10.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    assert json.loads((root/'companion.capability.v10.payloads.schema.json').read_text(encoding='utf8'))=={k:v.model_json_schema() for k,v in PAYLOADS.items()}

def test_internal_agent_bank_then_model_merge_keeps_human_gate(tmp_path):
    from base.app.local_agent import run_agent
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse,ToolCallPart
    t,s,r,b,d=setup(tmp_path);peer=s.identity.id;review(t,s,b,d)
    wf(t,'bank.export',{'id':d['id'],'expected_revision':1,'personal_content_checked':True,'reuse_source':'团队原创工程素材'},peer)
    generated=copy.deepcopy(body());generated['questions']=[generated['questions'][1]]
    q=generated['questions'][0];q.update(id='q1',material='The club opens on Friday.',prompt='When does the club open?',
        options=['Friday','Tuesday'],evidence='The club opens on Friday.')
    def model(messages,info):
        tools={getattr(part,'tool_name','') for m in messages for part in m.parts}
        if 'get_k12_context' not in tools:return ModelResponse(parts=[ToolCallPart('get_k12_context',{})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'body':generated,'review_candidates':reviews(generated)})])
    out=asyncio.run(run_agent(t,{'mode':'k12_workflow','route_id':r['id'],'peer_id':peer,
        'focus':'细节理解','count':2,'scope_ids':[],'job_id':'synthetic-workflow','use_fallback':False},FunctionModel(model)))
    # Library contributes one item; the model fills only the missing item and merges.
    assert out['draft_id'] and out['state']=='needs_human_review' and not out['human_review_confirmed']
    assert out['model_generation'] and len(wf(t,'workflow.resume',{'id':out['draft_id']},peer)['draft']['body']['questions'])==2
    # Force model-only unsupported skill, still through the same entry.
    for q in generated['questions']:q['skill']='推理判断'
    out=asyncio.run(run_agent(t,{'mode':'k12_workflow','route_id':r['id'],'peer_id':peer,
        'focus':'推理判断','count':1,'scope_ids':[],'job_id':'synthetic-model-only'},FunctionModel(model)))
    assert out['model_generation']['tools_used']==['get_k12_context'] and not out['automatic_publication']

def test_class_joint_evidence_contains_actual_answers_without_cause_invention(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d)
    target={'title':'共同目标','outcomes':{'语法':['q1'],'阅读':['q2']},'threshold':.8,'coverage_note':'同一素材，两个具体目标。'}
    for student,rr,dd in [(s,r,d)]:
        call(t,'k12.target.confirm',{'id':dd['id'],'expected_revision':1,'draft_hash':dd['content_hash'],'target':target,'human_review_confirmed':True},student.identity.id)
        submit(t,student,publish(t,student,dd,'target'),conditions={'additional_help':'none'})
    s2=instance(tmp_path/'s2','student','S2');pair(t,s2);r2=route(t,s2)
    d2=call(t,'k12.draft.save',{'route_id':r2['id'],'body':b},s2.identity.id)['record'];review(t,s2,b,d2)
    call(t,'k12.target.confirm',{'id':d2['id'],'expected_revision':1,'draft_hash':d2['content_hash'],'target':target,'human_review_confirmed':True},s2.identity.id)
    submit(t,s2,publish(t,s2,d2,'target'),{'q1':'A','q2':'A'},{'additional_help':'none'})
    groups=wf(t,'class.evidence',{'route_id':r['id']},s.identity.id)['groups']
    assert len(groups)==1 and len(groups[0]['evidence'])==2
    evidence=groups[0]['evidence'][0]
    assert evidence['original_answer']['answers']['q1']=='B' and len(evidence['questions'])==2
    assert evidence['problems']==[] and evidence['submitted_at']

def test_v10_http_mcp_equivalence_and_subject_backup_boundary(tmp_path):
    from fastapi.testclient import TestClient
    from growth_local.web import create_app
    from growth_local.mcp import create_mcp
    from base.app.local_backup import export_backup,restore_backup
    from base.app.local_runtime import LocalRuntime
    from test_local_runtime import MemoryVault
    from test_workspaces import w,select
    t=instance(tmp_path/'root','teacher','Teacher');w(t,'initialize');select(t,'english')
    app=create_app(t.folder,runtime=t,network=False)
    raw={'contract_version':'companion.capability.v10','operation':'roster.save','request_id':'same-three-transports',
         'payload':{'name':'合成预登记'}}
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/local/session',json={'bootstrap':app.state.bootstrap})
        expected=t.invoke_capability(raw)
        response=client.post('/api/local/capabilities/invoke',json=raw);assert response.status_code==200 and response.json()==expected
        result=asyncio.run(create_mcp(t).call_tool('invoke_companion_capability',{'request':raw}))
        # FastMCP versions return a tuple of content blocks plus structured output.
        if isinstance(result,tuple):assert result[1]==expected
        elif isinstance(result,list):assert json.loads(result[0].text)==expected
        else:assert json.loads(result.content[0].text)==expected
        select(t,'mathematics')
        assert client.post('/api/local/capabilities/invoke',json={**raw,'operation':'roster.list','payload':{},'request_id':'denied'}).status_code==403
    data=export_backup(t,'synthetic-password-12')
    restored=LocalRuntime(tmp_path/'restored',MemoryVault());restore_backup(restored,data,'synthetic-password-12')
    restored=LocalRuntime(restored.folder,restored.vault);select(restored,'english')
    assert wf(restored,'roster.list')['records'][0]['name']=='合成预登记'

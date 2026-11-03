import asyncio,base64,copy,json
from uuid import uuid4
import pytest
from test_local_runtime import instance,pair,drain,MemoryVault
from base.app.local_runtime import LocalRuntime
from base.app.local_backup import export_backup,restore_backup

def call(r,op,payload=None,peer=None,key=None):return r.invoke_capability({'contract_version':'companion.capability.v7','request_id':key or uuid4().hex,
    'operation':op,'payload':payload or {},'peer_id':peer})['data']

def route(t,s):return call(t,'route.save',{'title':'七年级英语 · 明确考点试练','level':'junior','grade':7,'goal':'根据主语选择be动词'},s.identity.id)['record']

def body(open=False):
    return {'title':'校园花园 · 原创合成测试','instructions':'按当前材料作答，先保留原答。','goal':'区分主语与实际条件','source':'团队原创合成工程内容',
      'criteria':['回应实际问题','依据或过程可以核对'],'questions':[
       {'id':'q1','type':'grammar_mcq','skill':'be动词主谓一致','material':'I am a student.','prompt':'Choose: I ___ a student.',
        'options':['am','is','are'],'key':['A'],'evidence':'I am a student.','explanation':'先辨认主语I。','traps':{'B':'语法形式错误','C':'语法形式错误'}},
       {'id':'q2','type':'reading_response' if open else 'reading_mcq','skill':'细节理解','material':'The garden is open on Monday.',
        'prompt':'When is the garden open?','options':[] if open else ['Monday','Tuesday'],'key':[] if open else ['A'],
        'evidence':'The garden is open on Monday.','explanation':'回到原文核对日期。','traps':{} if open else {'B':'张冠李戴'}}]}

def reviews(b):
    return [{'question_id':q['id'],'basis':q['evidence'],'ambiguity_check':'已按给定材料核对，其他选项与本次条件不符。',
        'choices':[{'option':chr(65+i),'defensible':chr(65+i) in q['key'],'reasoning':'依据当前主语或原文的明确条件判断。',
            'why_not':'与本次主语或原文日期不匹配。','next_step':'换一个主语或日期再对照一次。'} for i in range(len(q['options']))]} for q in b['questions']]

def setup(folder,open=False):
    t=instance(folder/'t','teacher','合成老师');s=instance(folder/'s','student','合成学生');pair(t,s);r=route(t,s);b=body(open)
    d=call(t,'k12.draft.save',{'route_id':r['id'],'body':b},s.identity.id)['record']
    return t,s,r,b,d

def review(t,s,b,d):return call(t,'k12.draft.review',{'id':d['id'],'expected_revision':d['revision'],'draft_hash':d['content_hash'],
    'questions':reviews(b),'human_review_confirmed':True},s.identity.id)['record']

def publish(t,s,d,mode='practice',key=None):return call(t,'k12.draft.publish',{'id':d['id'],'expected_revision':d['revision'],'mode':mode,'human_review_confirmed':True},s.identity.id,key)['record']

def submit(t,s,p,answers=None,conditions=None):
    drain(t,s);s.submit(p['task_id'],answers or {'q1':'B','q2':'A'},'',[],'first',conditions);drain(s,t);drain(t,s)
    a=t.task(p['task_id'])['attempts'][-1];return {'task_id':p['task_id'],'submission_id':a['id']}

def test_subjects_are_separate_from_tracks_and_do_not_relabel_legacy_records(tmp_path):
    t=instance(tmp_path/'t','teacher','T');old=t.profile.copy();cat=call(t,'academic.catalog')
    assert set(cat['subjects']['english']['tracks'])=={'k12','study_abroad','materials'}
    call(t,'academic.select',{'subject':'english','track':'k12'})
    assert t.profile==old and call(t,'academic.context')['selection']['track']=='k12'
    with pytest.raises(ValueError):call(t,'academic.select',{'subject':'mathematics','track':'k12'})

def test_review_is_frozen_complete_and_student_cannot_confirm(tmp_path):
    t,s,r,b,d=setup(tmp_path)
    with pytest.raises(ValueError):publish(t,s,d)
    wrong=reviews(b);wrong[0]['choices'][1]['defensible']=True
    with pytest.raises(ValueError):call(t,'k12.draft.review',{'id':d['id'],'expected_revision':1,'draft_hash':d['content_hash'],
        'questions':wrong,'human_review_confirmed':True},s.identity.id)
    with pytest.raises(PermissionError):call(s,'k12.draft.review',{'id':d['id'],'expected_revision':1,'draft_hash':d['content_hash'],
        'questions':reviews(b),'human_review_confirmed':True})
    review(t,s,b,d);p=publish(t,s,d,key='publish');assert publish(t,s,d,key='publish')==p
    drain(t,s);before=s.task(p['task_id']);assert all('key' not in q and 'traps' not in q for q in before['pack']['items'])
    w=submit(t,s,p);assert t.task(w['task_id'])['attempts'][-1]['automatic']['score']==1
    assert s.task(w['task_id'])['pack']['academic']['track']=='k12'

def test_scope_cas_and_stale_unpublished_draft(tmp_path):
    t,s,r,b,d=setup(tmp_path)
    scope={'route_id':r['id'],'textbook':'自编讲义','unit':'Unit 1','order':1,'source':'团队原创，工程测试','words':['I','am','student'],'complete':False,'content_reviewed':False}
    sc=call(t,'scope.save',scope,s.identity.id)['record'];b['scope_ids']=[sc['id']]
    d=call(t,'k12.draft.save',{'route_id':r['id'],'body':b},s.identity.id)['record']
    result=call(t,'scope.check',{'route_id':r['id'],'scope_ids':[sc['id']],'text':'I am happy.'},s.identity.id)['check']
    assert result['ok'] is None and 'happy' in result['unmatched_words']
    call(t,'scope.save',{**scope,'id':sc['id'],'expected_revision':1,'words':['I','am','happy']},s.identity.id)
    with pytest.raises(ValueError):review(t,s,b,d)
    with pytest.raises(ValueError):call(t,'scope.save',{**scope,'id':sc['id'],'expected_revision':1},s.identity.id)

def test_wrong_option_is_observation_cause_requires_extra_evidence_and_versions(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d);w=submit(t,s,publish(t,s,d));before=t.task(w['task_id'])['attempts'][-1]['evaluation']
    obs=call(t,'k12.problem.list',w,s.identity.id)['observations'];assert obs[0]['selected_trap']=='语法形式错误' and obs[0]['cause_state']=='unknown'
    p={**w,'question_id':'q1','observation':'学生实际选择is而不是am。','cause':'语法形式'}
    first=call(t,'k12.problem.record',p,s.identity.id)['record'];assert first['state']=='hypothesis'
    with pytest.raises(ValueError):call(t,'k12.problem.record',{**p,'expected_revision':1,'evidence_source':'student_explanation','human_confirmed':True},s.identity.id)
    confirmed=call(t,'k12.problem.record',{**p,'expected_revision':1,'evidence_source':'student_explanation','human_confirmed':True,
        'evidence_note':'合成说明：学生解释其把I当第三人称。','student_quote':'I以为也用is。'},s.identity.id)['record']
    assert confirmed['id']==first['id'] and confirmed['revision']==2 and confirmed['state']=='supported_cause'
    assert t.task(w['task_id'])['attempts'][-1]['evaluation']==before
    assert call(t,'k12.report',{'route_id':r['id']},s.identity.id)['unconfirmed_problems']==0

def test_dual_explanations_sync_only_student_version_and_errata_keep_original_grade(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d);w=submit(t,s,publish(t,s,d));before=t.task(w['task_id'])['attempts'][-1]['automatic']
    call(t,'k12.explain.save',{**w,'question_id':'q1','student':'先看主语I，再匹配am。','tutor':'PRIVATE_TEACHER_LECTURE','next_step':'换成she重新判断一次。','quote':'I am a student.','human_confirmed':True},s.identity.id)
    call(t,'k12.evidence.correct',{'task_id':w['task_id'],'question_id':'q2','quote':'The garden is open on Monday.','reason':'合成测试追加勘误标记。','invalid_item':True,'human_confirmed':True},s.identity.id)
    drain(t,s);synced=json.dumps(s.task(w['task_id']),ensure_ascii=False)
    assert 'PRIVATE_TEACHER_LECTURE' not in synced and '先看主语I' in synced
    assert t.task(w['task_id'])['attempts'][-1]['automatic']==before
    assert call(t,'k12.next',{'route_id':r['id']},s.identity.id)['method']=='验证材料'

def test_target_coverage_precedes_publish_help_unknown_is_not_mastery_and_no_overwrite(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d)
    with pytest.raises(ValueError):publish(t,s,d,'target')
    call(t,'k12.target.confirm',{'id':d['id'],'expected_revision':1,'draft_hash':d['content_hash'],'human_review_confirmed':True,
        'target':{'title':'本次试行检查','outcomes':{'主语与日期':['q1','q2']},'coverage_note':'两题只作合成工程覆盖检查。'}},s.identity.id)
    p=publish(t,s,d,'target');w=submit(t,s,p,{'q1':'A','q2':'A'})
    result=call(t,'k12.report',{'route_id':r['id']},s.identity.id);assert result['target_results'][0]['outcomes'][0]['state']=='pending'
    with pytest.raises(ValueError):s.submit(p['task_id'],{'q1':'B','q2':'A'},'',[],'second')
    s.submit(p['task_id'],{'q1':'A','q2':'A'},'',[],'first')

def test_open_question_pending_not_zero_and_score_is_literal_evidence(tmp_path):
    t,s,r,b,d=setup(tmp_path,True);review(t,s,b,d);w=submit(t,s,publish(t,s,d),{'q1':'A','q2':'The garden is open on Monday.'})
    rep=call(t,'k12.report',{'route_id':r['id']},s.identity.id);assert rep['pending_reviews']==1
    payload={**w,'question_id':'q2','score':1,'comment':'日期与本次材料一致。','evidence':'An invented answer.','human_confirmed':True}
    with pytest.raises(ValueError):call(t,'k12.score.record',payload,s.identity.id)
    call(t,'k12.score.record',{**payload,'evidence':'open on Monday'},s.identity.id)
    assert call(t,'k12.report',{'route_id':r['id']},s.identity.id)['pending_reviews']==0

def test_bank_excludes_assigned_items_and_retirement(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d)
    request={'route_id':r['id'],'count':2};assert len(call(t,'k12.bank.pick',request,s.identity.id)['record']['selected'])==2
    publish(t,s,d)
    assert call(t,'k12.bank.pick',request,s.identity.id)['record']['missing']==2
    call(t,'k12.bank.retire',{'id':d['id'],'expected_revision':1},s.identity.id)
    assert call(t,'k12.bank.list',{'route_id':r['id']},s.identity.id)['records']==[]

def test_class_freezes_roster_and_retry_does_not_reassign_success(tmp_path):
    t,s,r,b,d=setup(tmp_path);u=instance(tmp_path/'u','student','另一合成学生');pair(t,u);route(t,u);review(t,s,b,d)
    c=call(t,'k12.class.save',{'title':'合成小班','peers':[s.identity.id,u.identity.id]})['record']
    p={'id':c['id'],'expected_revision':1,'source_draft_id':d['id'],'source_revision':1}
    first=call(t,'k12.class.assign',p,key='batch')['batch'];second=call(t,'k12.class.assign',p,key='batch')['batch']
    assert [e['task_id'] for e in first['entries']]==[e['task_id'] for e in second['entries']]
    assert len(t.teacher_dashboard(s.identity.id)['tasks'])==1
    report=call(t,'k12.class.report',{'id':c['id']});assert all(x['state']=='not_submitted' for x in report['rows'])

def test_revoked_scope_and_encrypted_backup_preserve_new_records(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d)
    encrypted=export_backup(t,'Synthetic-K12-test-password-123');fresh=LocalRuntime(tmp_path/'restored',MemoryVault());restore_backup(fresh,encrypted,'Synthetic-K12-test-password-123')
    fresh=LocalRuntime(fresh.folder,fresh.vault)
    assert call(fresh,'k12.draft.read',{'id':d['id']},s.identity.id)['record']['content_hash']==d['content_hash']
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError):call(t,'k12.draft.read',{'id':d['id']},s.identity.id)

def test_bank_composes_only_current_unseen_subset_and_requires_new_review(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d)
    pick=call(t,'k12.bank.pick',{'route_id':r['id'],'skills':['细节理解'],'count':1},s.identity.id)['record']
    composed=call(t,'k12.bank.compose',{'id':pick['id'],'expected_revision':pick['revision'],'title':'选取的未见细节题'},s.identity.id)['record']
    assert len(composed['body']['questions'])==1 and composed['body']['questions'][0]['skill']=='细节理解'
    with pytest.raises(ValueError):publish(t,s,composed)
    publish(t,s,d)
    with pytest.raises(ValueError):call(t,'k12.bank.compose',{'id':pick['id'],'expected_revision':pick['revision'],'title':'已经见过'},s.identity.id)

def test_future_scope_and_changed_route_invalidate_draft_and_bank(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d)
    scope=call(t,'scope.save',{'route_id':r['id'],'textbook':'合成教材','unit':'Unit2','order':2,'source':'原创测试'},s.identity.id)['record']
    with pytest.raises(ValueError):call(t,'k12.draft.save',{'route_id':r['id'],'body':{**b,'scope_ids':[scope['id']]}},s.identity.id)
    call(t,'route.save',{**{k:r[k] for k in ['title','level','grade','goal']},'id':r['id'],'expected_revision':1,'scope_order':2},s.identity.id)
    assert call(t,'k12.bank.list',{'route_id':r['id']},s.identity.id)['records']==[]
    with pytest.raises(ValueError):publish(t,s,d)

def test_independent_disagreement_is_preserved_until_teacher_resolves(tmp_path):
    t,s,r,b,d=setup(tmp_path)
    p={'id':d['id'],'expected_revision':1,'draft_hash':d['content_hash'],'questions':reviews(b),'independent_answers':{'q1':['B'],'q2':['A']}}
    candidate=call(t,'k12.draft.candidate_review',p,s.identity.id)['record']
    assert candidate['issues'] and not candidate['human_review_confirmed']
    with pytest.raises(ValueError):review(t,s,b,d)
    resolved=call(t,'k12.draft.review',{**p,'human_review_confirmed':True,'resolution_note':'核对原文I与am；审题候选误选，当前原题保留。'},s.identity.id)['record']
    assert resolved['resolution_note'] and resolved['issues']

def test_independent_model_must_solve_before_reading_keys(tmp_path):
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse,ToolCallPart
    from base.app.local_agent import run_agent
    t,s,r,b,d=setup(tmp_path)
    def model(messages,info):
        tools={getattr(p,'tool_name','') for m in messages for p in m.parts}
        if 'get_questions_without_keys' not in tools:return ModelResponse(parts=[ToolCallPart('get_questions_without_keys',{})])
        if 'record_independent_answers' not in tools:
            # The question-only tool payload must actually hide keys and explanations.
            returned=[p.content for m in messages for p in m.parts if getattr(p,'tool_name','')=='get_questions_without_keys' and hasattr(p,'content')][-1]
            assert all('key' not in q and 'traps' not in q and 'explanation' not in q for q in returned['questions'])
            return ModelResponse(parts=[ToolCallPart('record_independent_answers',{'proposed_answers':{'q1':['am'],'q2':['A']}})])
        if 'get_reference_keys' not in tools:return ModelResponse(parts=[ToolCallPart('get_reference_keys',{})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'questions':reviews(b),'issues':[]})])
    result=asyncio.run(run_agent(t,{'mode':'k12_review','draft_id':d['id'],'peer_id':s.identity.id},FunctionModel(model)))
    assert result['tools_used']==['get_questions_without_keys','record_independent_answers','get_reference_keys']
    assert not result['automatic_publication'] and not call(t,'k12.draft.read',{'id':d['id']},s.identity.id)['reviews']
    assert call(t,'k12.draft.read',{'id':d['id']},s.identity.id)['candidate_reviews'][0]['independent_answers']['q1']==['A']

def test_generation_reads_actual_route_and_only_saves_candidate(tmp_path):
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse,ToolCallPart
    from base.app.local_agent import run_agent
    t,s,r,b,d=setup(tmp_path)
    def model(messages,info):
        names={getattr(p,'tool_name','') for m in messages for p in m.parts}
        if 'get_k12_context' not in names:return ModelResponse(parts=[ToolCallPart('get_k12_context',{})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'body':b,'review_candidates':reviews(b)})])
    result=asyncio.run(run_agent(t,{'mode':'k12_generate','route_id':r['id'],'peer_id':s.identity.id,'count':2,'prompt':'主语与细节'},FunctionModel(model)))
    assert result['tools_used']==['get_k12_context'] and not result['human_review_confirmed']
    with pytest.raises(ValueError):publish(t,s,call(t,'k12.draft.read',{'id':result['draft_id']},s.identity.id)['record'])

def test_class_retry_keeps_old_frozen_roster_and_marks_scored_open_work(tmp_path):
    t,s,r,b,d=setup(tmp_path,True);review(t,s,b,d)
    c=call(t,'k12.class.save',{'title':'合成小班','peers':[s.identity.id]})['record'];params={'id':c['id'],'expected_revision':1,'source_draft_id':d['id'],'source_revision':1}
    first=call(t,'k12.class.assign',params,key='frozen')['batch']
    call(t,'k12.class.save',{'id':c['id'],'expected_revision':1,'title':'改名不改已布置名单','peers':[s.identity.id]})
    again=call(t,'k12.class.assign',params,key='frozen')['batch'];assert again['members']==first['members'] and again['entries']==first['entries']
    w=submit(t,s,first['entries'][0],{'q1':'A','q2':'On Monday.'})
    assert call(t,'k12.class.report',{'id':c['id']})['rows'][0]['state']=='pending_review'
    call(t,'k12.score.record',{**w,'question_id':'q2','score':1,'comment':'日期符合本题实际材料。','evidence':'Monday','human_confirmed':True},s.identity.id)
    assert call(t,'k12.class.report',{'id':c['id']})['rows'][0]['state']=='submitted'

def test_feedback_integrity_and_listening_original_are_not_leaked_before_submission(tmp_path):
    from base.app.companion.assets.academic import verify_task
    t,s,r,b,d=setup(tmp_path)
    wav=b'RIFF'+(36).to_bytes(4,'little')+b'WAVE'+b'\0'*32
    media=call(t,'k12.media.save',{'name':'合成静音头，仅测试字节','source':'工程合成文件，不是真人','mime':'audio/wav','data_base64':base64.b64encode(wav).decode()})['record']
    b['audio_id']=media['id'];b['questions'][1]['type']='listening'
    d=call(t,'k12.draft.save',{'route_id':r['id'],'body':b},s.identity.id)['record']
    with pytest.raises(ValueError):review(t,s,b,d)
    call(t,'k12.draft.review',{'id':d['id'],'expected_revision':1,'draft_hash':d['content_hash'],'questions':reviews(b),'audio_listened':True,'human_review_confirmed':True},s.identity.id)
    p=publish(t,s,d);drain(t,s);assert 'material' not in s.task(p['task_id'])['pack']['items'][1]
    w=submit(t,s,p);call(t,'k12.problem.record',{**w,'question_id':'q1','observation':'实际误选主语对应形式。'},s.identity.id);drain(t,s)
    task=s.task(p['task_id']);verify_task(task);task['academic_feedback'][0]['observation']='被改写的内容'
    with pytest.raises(ValueError):verify_task(task)

def test_import_preview_does_not_publish_and_notifications_are_explicit(tmp_path):
    t,s,r,b,d=setup(tmp_path)
    preview=call(t,'k12.import.preview',{'route_id':r['id'],'content':json.dumps([b],ensure_ascii=False)},s.identity.id)['record']
    result=call(t,'k12.import.commit',{'id':preview['id'],'preview_hash':preview['content_hash']},s.identity.id)
    assert result['status']=='candidate_requires_review' and len(t.teacher_dashboard(s.identity.id)['tasks'])==0
    review(t,s,b,d);w=submit(t,s,publish(t,s,d))
    notices=call(t,'k12.notifications')['notifications'];assert len(notices)==1 and not notices[0]['read']
    call(t,'k12.notifications.read',{'id':w['submission_id']});assert call(t,'k12.notifications')['notifications'][0]['read']

def test_report_proposes_check_for_unclassified_wrong_answer(tmp_path):
    t,s,r,b,d=setup(tmp_path);review(t,s,b,d);submit(t,s,publish(t,s,d))
    rep=call(t,'k12.report',{'route_id':r['id']},s.identity.id)
    assert rep['unconfirmed_problems']==1 and rep['confirmed_problems']==0 and rep['next']['method']=='提问与探究'
    assert rep['problems'][0]['source']=='automatic_observation_not_causal_diagnosis'

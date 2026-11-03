import asyncio,copy,json
from uuid import uuid4
import pytest
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse,ToolCallPart
from test_local_runtime import instance,pair,drain,MemoryVault
from base.app.local_runtime import LocalRuntime
from base.app.local_agent import run_agent
from base.app.local_backup import export_backup,restore_backup

def call(r,op,payload=None,peer=None,key=None):
    return r.invoke_capability({'contract_version':'companion.capability.v6','request_id':key or uuid4().hex,
        'operation':op,'payload':payload or {},'peer_id':peer})['data']

def fixture(folder,purpose='writing'):
    t=instance(folder/'t','teacher','T');s=instance(folder/'s','student','S');pair(t,s)
    task=t.assign(s.identity.id,purpose,'first');drain(t,s)
    s.submit(task['id'],{},'A garden help people. It offers shade.',[],'first');drain(s,t);drain(t,s)
    sid=t.task(task['id'])['attempts'][-1]['id']
    return t,s,{'task_id':task['id'],'submission_id':sid}

def report(c):return {'summary':'合成预审，仅判断当前文字。','comment':'观点可辨认；建议先核对主语与动词。','next_step':'先解释主语，再修改一个动词。',
    'dimensions':[{'criterion':x,'status':'partial','observation':'当前稿能找到一句表达，但需要人工核对是否满足本维度。','evidence':'A garden help people.'} for x in c['source']['criteria']],
    'uncertainties':['合成用例，未进行专业审定。']}

def captured(t,s,target):
    c=call(t,'review.context',target,s.identity.id)
    p=call(t,'review.capture',{**target,'context_hash':c['context_hash'],'report':report(c),'model_name':'Synthetic external model'},s.identity.id)['prereview']
    return c,p

def draft(t,s,target,c,p,**fields):
    value={k:p['report'][k] for k in ['comment','next_step','dimensions']}|{'outcome':'ungraded',**fields}
    return call(t,'review.draft.save',{**target,'context_hash':c['context_hash'],'prereview_id':p['id'],'fields':value},s.identity.id)['draft']

def publish(t,s,d,key=None,**kw):return call(t,'review.publish',{'draft_id':d['id'],'expected_revision':d['revision'],'draft_hash':d['content_hash'],
    'human_review_confirmed':True,**kw},s.identity.id,key)

def test_context_is_teacher_scoped_bounded_actual_work_without_notes_or_keys(tmp_path):
    t,s,target=fixture(tmp_path);u=instance(tmp_path/'u','student','U');pair(t,u)
    t.save_teacher_notes(s.identity.id,'PRIVATE_NOTE_MUST_NOT_ENTER_MODEL')
    t.save_model({'provider':'deepseek','base_url':'https://api.deepseek.com','model':'test'},'PRIVATE_TEST_KEY',remember=False)
    c=call(t,'review.context',target,s.identity.id);serialized=json.dumps(c)
    assert c['source']['work'].startswith('A garden') and len(c['source']['criteria'])==4
    assert 'PRIVATE_NOTE_MUST_NOT_ENTER_MODEL' not in serialized and 'PRIVATE_TEST_KEY' not in serialized
    with pytest.raises(PermissionError):call(s,'review.context',target)
    with pytest.raises(PermissionError):call(t,'review.context',target,u.identity.id)

def test_model_candidate_has_exact_refs_but_no_formal_review_or_student_sync(tmp_path):
    t,s,target=fixture(tmp_path);before=t.task(target['task_id'])['attempts'][0]['evaluation'];c,p=captured(t,s,target)
    assert p['source_type']=='model_candidate' and p['evidence_refs'][0]['start']==0 and not p['formal_review_written']
    assert t.task(target['task_id'])['attempts'][0]['evaluation']==before and not t.pending(s.identity.id)
    bad=report(c);bad['dimensions'][0]['evidence']='A fabricated quotation.'
    with pytest.raises(ValueError):call(t,'review.capture',{**target,'context_hash':c['context_hash'],'report':bad,'model_name':'test'},s.identity.id)

def test_teacher_edits_versioned_draft_then_explicit_publication_and_replay(tmp_path):
    t,s,target=fixture(tmp_path);c,p=captured(t,s,target);d=draft(t,s,target,c,p,comment='教师修改后的具体反馈。')
    assert d['teacher_modified'] and not t.task(target['task_id'])['attempts'][0]['review_history']
    with pytest.raises(ValueError):publish(t,s,d,human_review_confirmed=False)
    value=publish(t,s,d,key='publish');assert publish(t,s,d,key='publish')==value
    assert len(t.task(target['task_id'])['attempts'][0]['review_history'])==1
    drain(t,s);task=s.task(target['task_id']);assert task['attempts'][0]['evaluation']['comment']=='教师修改后的具体反馈。'
    assert task['companion_review_assistance'][0]['used_ai'] and task['companion_review_assistance'][0]['teacher_modified']
    assert 'report' not in json.dumps(task['companion_review_assistance'])

def test_draft_cas_and_new_submission_or_revocation_invalidate_old_work(tmp_path):
    t,s,target=fixture(tmp_path);c,p=captured(t,s,target);d=draft(t,s,target,c,p)
    payload={**target,'context_hash':c['context_hash'],'draft_id':d['id'],'expected_revision':1,'prereview_id':p['id'],
        'fields':{**d['fields'],'next_step':'教师重新安排的一步。'}}
    new=call(t,'review.draft.save',payload,s.identity.id)['draft'];assert new['revision']==2
    with pytest.raises(ValueError):call(t,'review.draft.save',payload,s.identity.id)
    with pytest.raises(ValueError):publish(t,s,d)
    s.submit(target['task_id'],{},'A new learner revision.',[],'second');drain(s,t)
    with pytest.raises(ValueError):publish(t,s,new)
    assert not call(t,'review.list',{'task_id':target['task_id']},s.identity.id)['prereviews'][0]['current']
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError):call(t,'review.draft.read',{'draft_id':d['id']},s.identity.id)

def model_for(c,counts=None):
    def model(messages,info):
        if counts is not None:counts.append('request')
        seen={getattr(p,'tool_name','') for m in messages for p in m.parts}
        if 'get_review_context' not in seen:return ModelResponse(parts=[ToolCallPart('get_review_context',{})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,report(c))])
    return FunctionModel(model)

def test_real_agent_tool_path_only_captures_candidate_and_rechecks_midflight_changes(tmp_path):
    t,s,target=fixture(tmp_path);c=call(t,'review.context',target,s.identity.id)
    result=asyncio.run(run_agent(t,{'mode':'prereview','peer_id':s.identity.id,**target},model_for(c)))
    assert result['tools_used']==['get_review_context'] and not result['automatic_teacher_judgement']
    assert not t.task(target['task_id'])['attempts'][0]['review_history']
    def changed(messages,info):
        seen={getattr(p,'tool_name','') for m in messages for p in m.parts}
        if 'get_review_context' not in seen:return ModelResponse(parts=[ToolCallPart('get_review_context',{})])
        s.submit(target['task_id'],{},'Changed during model request.',[],'changed');drain(s,t)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,report(c))])
    with pytest.raises(ValueError):asyncio.run(run_agent(t,{'mode':'prereview','peer_id':s.identity.id,**target},FunctionModel(changed)))
    assert len(call(t,'review.list',{'task_id':target['task_id']},s.identity.id)['prereviews'])==1

def test_auto_on_receipt_is_opt_in_deduplicated_and_two_workers_claim_once(tmp_path):
    t,s,target=fixture(tmp_path);assert not call(t,'review.settings')['settings']['automatic']
    t.save_model({'provider':'deepseek','base_url':'https://api.deepseek.com','model':'test'},'synthetic-key',remember=False)
    call(t,'review.settings.save',{'automatic':True})
    s.submit(target['task_id'],{},'A garden help people. It offers shade.',[],'second');envelope=s.pending(t.identity.id)[0]
    t.receive(envelope);t.receive(envelope);s.ack(t.identity.id,envelope['body']['id'])
    latest=t.task(target['task_id'])['attempts'][-1]['id'];new_target={'task_id':target['task_id'],'submission_id':latest}
    with t.db() as db:jobs=db.execute("SELECT id FROM local_jobs WHERE id LIKE 'review-job-%'").fetchall()
    assert len(jobs)==1
    c=call(t,'review.context',new_target,s.identity.id);counts=[]
    async def run():
        from base.app.companion.functional.review_agent import review_worker
        background=set();workers=[asyncio.create_task(review_worker(t,background,model_for(c,counts))) for _ in range(2)]
        try:
            for _ in range(120):
                if t.job(jobs[0]['id'])['status'] in ['completed','failed']:break
                await asyncio.sleep(.05)
            assert t.job(jobs[0]['id'])['status']=='completed'
        finally:
            for task in workers+list(background):task.cancel()
            await asyncio.gather(*workers,*list(background),return_exceptions=True)
    asyncio.run(run());assert len(counts)==2
    assert not t.task(target['task_id'])['attempts'][-1]['review_history']

def test_failure_after_formal_feedback_recovers_audit_without_double_review(tmp_path,monkeypatch):
    from base.app.companion.functional import study
    t,s,target=fixture(tmp_path);c,p=captured(t,s,target);d=draft(t,s,target,c,p)
    original=study.append_assessment
    monkeypatch.setattr(study,'append_assessment',lambda *a:(_ for _ in ()).throw(RuntimeError('Synthetic crash after feedback')))
    with pytest.raises(RuntimeError):publish(t,s,d,key='recover')
    assert len(t.task(target['task_id'])['attempts'][0]['review_history'])==1
    monkeypatch.setattr(study,'append_assessment',original)
    value=publish(t,s,d,key='recover');assert value['publication']['assessment_id']
    assert len(t.task(target['task_id'])['attempts'][0]['review_history'])==1

def test_backup_restores_candidates_and_teacher_edits_without_sending_them(tmp_path):
    t,s,target=fixture(tmp_path);c,p=captured(t,s,target);d=draft(t,s,target,c,p)
    encrypted=export_backup(t,'Synthetic-test-password-123');fresh=LocalRuntime(tmp_path/'restored',MemoryVault());restore_backup(fresh,encrypted,'Synthetic-test-password-123')
    restored=LocalRuntime(fresh.folder,fresh.vault)
    assert call(restored,'review.draft.read',{'draft_id':d['id']},s.identity.id)['draft']['content_hash']==d['content_hash']
    assert not restored.task(target['task_id'])['attempts'][0]['review_history']

def test_unread_sound_cannot_become_automatic_support_or_formal_mastery(tmp_path):
    from base.app.companion.aesthetic.prereview import normalize_report,check_teacher_fields
    criteria=['Pronunciation and fluency','说明自己的观点'];work='My garden is useful.'
    rows=[{'criterion':c,'status':'supported','observation':'有候选表现','evidence':work} for c in criteria]
    value=normalize_report({'dimensions':rows,'uncertainties':[]},criteria,work,'',
        {'requires_unread_media':True,'limitations':['未听取声音']})
    assert [d['status'] for d in value['dimensions']]==['ungraded','partial']
    fields={'dimensions':rows,'outcome':'meets_criteria'}
    with pytest.raises(ValueError):check_teacher_fields(fields,criteria,work,'',True,False,True)
    with pytest.raises(ValueError):check_teacher_fields(fields,criteria,work,'',True,True,False)
    check_teacher_fields(fields,criteria,work,'',True,True,True)
    t,s,target=fixture(tmp_path)
    with pytest.raises(ValueError):call(t,'review.start',target,s.identity.id)
    assert not t.task(target['task_id'])['attempts'][0]['review_history']

def test_publication_queue_recovers_if_interrupted_after_sidecar(tmp_path,monkeypatch):
    t,s,target=fixture(tmp_path);c,p=captured(t,s,target);d=draft(t,s,target,c,p)
    original=t.queue_task_update
    def interrupted(peer,task_id,event_id=None):
        if event_id and event_id.startswith('review-published-'):raise RuntimeError('Synthetic queue interruption')
        return original(peer,task_id,event_id)
    monkeypatch.setattr(t,'queue_task_update',interrupted)
    with pytest.raises(RuntimeError):publish(t,s,d,key='queue-recovery')
    assert len(t.task(target['task_id'])['attempts'][0]['review_history'])==1
    monkeypatch.setattr(t,'queue_task_update',original)
    publish(t,s,d,key='queue-recovery');drain(t,s)
    assert s.task(target['task_id'])['companion_review_assistance'][0]['used_ai']
    assert len(t.task(target['task_id'])['attempts'][0]['review_history'])==1

def test_repeated_unverifiable_model_quote_is_discarded_never_promoted(tmp_path):
    t,s,target=fixture(tmp_path);c=call(t,'review.context',target,s.identity.id);bad=report(c)
    bad['dimensions'][0].update(evidence='A garden helps people.',status='supported')
    bad['uncertainties']=['模型原有说明'+str(i) for i in range(10)]
    def model(messages,info):
        seen={getattr(p,'tool_name','') for m in messages for p in m.parts}
        if 'get_review_context' not in seen:return ModelResponse(parts=[ToolCallPart('get_review_context',{})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,bad)])
    result=asyncio.run(run_agent(t,{'mode':'prereview','peer_id':s.identity.id,**target},FunctionModel(model)))
    row=result['output']['dimensions'][0]
    assert row['evidence']=='' and row['status']=='ungraded' and '已弃用' in result['output']['uncertainties'][0]
    assert not t.task(target['task_id'])['attempts'][0]['review_history']

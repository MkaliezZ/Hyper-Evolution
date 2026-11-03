import asyncio
import copy
import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from base.app.local_agent import learning_context, run_agent
from base.app.local_runtime import LocalRuntime
from base.app.companion.assets.references import Locator
from growth_local.web import create_app
from growth_local.mcp import create_mcp
from test_local_runtime import instance, pair, drain, MemoryVault


def invoke(runtime, operation='evidence.read', **kwargs):
    return runtime.invoke_capability({'request_id': 'foundation-test', 'operation': operation, **kwargs})


def assignment(tmp_path, purpose='writing'):
    t = instance(tmp_path/'t', 'teacher', 'PRIVATE TEACHER')
    s = instance(tmp_path/'s', 'student', 'PRIVATE STUDENT')
    pair(t, s)
    task = t.assign(s.identity.id, purpose, 'assign')
    drain(t, s)
    return t, s, task


def test_shared_self_teacher_evidence_private_fields_and_read_only_history(tmp_path, monkeypatch):
    t,s,task = assignment(tmp_path)
    own = s.start_self('writing', 'own')
    s.submit(own['id'], {}, 'Own submitted work', [], 'own-first')
    s.save_config('draft:'+task['id'], {'text': 'UNSUBMITTED SECRET'})
    t.save_teacher_notes(s.identity.id, 'SECRET TEACHER NOTE')
    s.submit(task['id'], {}, 'Teacher assigned first draft', [], 'remote-first')
    queued = invoke(s)['data']
    remote = next(x for x in queued['tasks'] if x['id']==task['id'])
    assert remote['local_submission_queue'][0]['answer']['text']=='Teacher assigned first draft'
    assert not remote['attempts']
    drain(s,t);drain(t,s)
    sid = t.task(task['id'])['attempts'][0]['id']
    t.feedback(sid, 'VISIBLE TEACHER FEEDBACK', 'Try a new argument', 'needs_revision', None, 'review')
    drain(t,s)
    # Evidence must not run current grading code, mutate history, or read provider credentials.
    import base.app.growth as growth
    monkeypatch.setattr(growth, 'grade', lambda *a: pytest.fail('historical work regraded'))
    before = hashlib.sha256((s.folder/'base.sqlite3').read_bytes()).hexdigest()
    view = invoke(s)['data']
    assert {x['origin'] for x in view['tasks']}=={'self','teacher'}
    item = next(x for x in view['tasks'] if x['id']==task['id'])
    assert item['attempts'][0]['assessment_authority']=='signed_teacher_review'
    assert item['attempts'][0]['evaluation']['comment']=='VISIBLE TEACHER FEEDBACK'
    assert item['attempts'][0]['additional_help']=='not_recorded'
    assert item['attempts'][0]['automatic'] is None
    context = learning_context(s)
    assert 'VISIBLE TEACHER FEEDBACK' in json.dumps(context)
    raw = json.dumps(view)+json.dumps(context)+json.dumps(invoke(t, peer_id=s.identity.id))
    for secret in ['PRIVATE','SECRET','owner_token','media_path','reviewer_id','accepted','transcript']:
        assert secret not in raw
    assert hashlib.sha256((s.folder/'base.sqlite3').read_bytes()).hexdigest()==before


def test_asset_reference_version_tampering_locator_and_current_authorization(tmp_path):
    t,s,task = assignment(tmp_path)
    first = invoke(s, task_id=task['id'])['data']['tasks'][0]
    ref = first['source_ref']
    result = invoke(s,'asset.resolve',input_refs=[ref])
    assert result['status']=='completed' and result['data']['text']==first['material']['stimulus']
    sliced = copy.deepcopy(ref);sliced['locator']={'kind':'text','start':0,'end':12}
    assert invoke(s,'asset.resolve',input_refs=[sliced])['data']['text']==first['material']['stimulus'][:12]
    unsupported = copy.deepcopy(ref);unsupported['locator']={'kind':'page','page':1}
    assert invoke(s,'asset.resolve',input_refs=[unsupported])['status']=='unavailable'
    bad = copy.deepcopy(ref);bad['owner_ref']='device:forged'
    assert invoke(s,'asset.resolve',input_refs=[bad])['status']=='needs_input'
    # A new source version cannot silently satisfy the old reference.
    with s.db() as db:
        body=json.loads(db.execute('SELECT body FROM local_remote_tasks WHERE id=?',(task['id'],)).fetchone()['body'])
        body['pack']['stimulus']='Changed source'
        db.execute('UPDATE local_remote_tasks SET body=? WHERE id=?',(json.dumps(body),task['id']))
    assert invoke(s,'asset.resolve',input_refs=[ref])['status']=='needs_input'
    s.unpair(t.identity.id)
    assert invoke(s)['data']['coverage']['excluded_revoked_tasks']==1
    with pytest.raises(PermissionError):invoke(s,'asset.resolve',input_refs=[ref])
    # Existing copies remain, but are excluded from new authorized contexts.
    assert s.task(task['id'])


def test_teacher_scope_and_revocation_cannot_be_bypassed_with_a_reference(tmp_path):
    t,s,task = assignment(tmp_path)
    other=instance(tmp_path/'other','student','OTHER PRIVATE')
    pair(t,other)
    with pytest.raises(PermissionError):invoke(t,peer_id=other.identity.id,task_id=task['id'])
    with pytest.raises(ValueError):invoke(t)
    with pytest.raises(PermissionError):invoke(s,peer_id=t.identity.id)
    ref=invoke(t,peer_id=s.identity.id)['data']['tasks'][0]['snapshot_ref']
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError):invoke(t,'asset.resolve',peer_id=s.identity.id,input_refs=[ref])


def test_old_conditions_unknown_keys_not_exposed_and_no_grade_replay(tmp_path, monkeypatch):
    s=instance(tmp_path,'student','PRIVATE')
    task=s.start_self('diagnostic','diag')
    first=invoke(s)['data']['tasks'][0]
    assert all('key' not in q for q in first['material']['items'])
    answers={i['id']:'B' for i in task['pack']['items']}
    s.submit(task['id'],answers,'Submitted',[],'attempt')
    import base.app.growth as growth
    monkeypatch.setattr(growth,'grade',lambda *a:pytest.fail('historical grading'))
    view=invoke(s)['data']['tasks'][0]
    assert view['attempts'][0]['answer']['answers']==answers
    assert view['attempts'][0]['assessment_authority']=='objective_check'
    assert view['missing'] and 'accepted' not in json.dumps(view)
    assert view['quality']['task_fit']=='unknown'


def test_history_refs_and_current_evaluation_version(tmp_path):
    t,s,task=assignment(tmp_path)
    s.submit(task['id'],{},'Draft',[],'one');drain(s,t);drain(t,s)
    sid=t.task(task['id'])['attempts'][0]['id']
    t.feedback(sid,'First visible review','Revise',None,None,'first');drain(t,s)
    attempt=invoke(s)['data']['tasks'][0]['attempts'][0]
    old_eval=attempt['evaluation_ref'];old_review=attempt['review_history'][0]['asset_ref']
    t.feedback(sid,'Second review','New task','meets_criteria',None,'second');drain(t,s)
    assert invoke(s,'asset.resolve',input_refs=[old_eval])['status']=='needs_input'
    assert invoke(s,'asset.resolve',input_refs=[old_review])['data']['comment']=='First visible review'
    assert len(invoke(s)['data']['tasks'][0]['attempts'][0]['review_history'])==2


def test_legacy_remote_recomputed_automatic_not_promoted_to_historical_evidence(tmp_path):
    t,s,task=assignment(tmp_path,'diagnostic')
    answers={i['id']:'B' for i in task['pack']['items']}
    s.submit(task['id'],answers,'Work',[],'one');drain(s,t);drain(t,s)
    sid=t.task(task['id'])['attempts'][0]['id']
    t.feedback(sid,'Reviewed','Next',None,None,'review');drain(t,s)
    # Current legacy session still supplies computed automatic values for display.
    assert s.task(task['id'])['attempts'][0]['automatic']
    projected=invoke(s)['data']['tasks'][0]['attempts'][0]
    assert projected['automatic'] is None
    assert projected['historical_automatic']=='not_preserved_or_not_applicable'


def test_contract_validates_without_reflecting_credentials_and_reports_coverage(tmp_path):
    s=instance(tmp_path,'student','S')
    for i in range(3):s.start_self('writing','task-'+str(i))
    result=invoke(s,limits={'tasks':1,'attempts':1})
    assert result['status']=='partial' and result['data']['coverage']['tasks_total']==3
    assert 'commit_receipt' not in result
    for extra in [{'actor_scope':'SECRET TOKEN'},{'contract_version':'invalid'},{'limits':{'tasks':1000}}]:
        with pytest.raises(ValueError) as caught:invoke(s,**extra)
        assert 'SECRET TOKEN' not in str(caught.value)
    with pytest.raises(ValueError):Locator(kind='region',page=1,region=[0.9,0.2,0.3,0.4])


def test_web_mcp_same_contract_and_bootstrap_guard(tmp_path):
    t,s,task=assignment(tmp_path)
    request={'request_id':'same-transport-request','operation':'evidence.read','task_id':task['id']}
    app=create_app(s.folder,runtime=s,network=False)
    with TestClient(app,base_url='http://127.0.0.1') as web:
        assert web.post('/api/local/capabilities/invoke',json=request).status_code==401
        assert web.post('/api/local/session',json={'bootstrap':app.state.bootstrap}).status_code==200
        http=web.post('/api/local/capabilities/invoke',json=request)
        assert http.status_code==200
        async def call():
            server=create_mcp(s)
            names={tool.name for tool in await server.list_tools()}
            assert {'submit_work','get_authorized_evidence','invoke_companion_capability'}<=names
            assert 'record_teacher_feedback' not in names
            result=await server.call_tool('invoke_companion_capability',{'request':request})
            if isinstance(result,tuple):return result[1]
            return json.loads(result[0].text)
        mcp=asyncio.run(call())
        assert mcp==http.json()
        assert web.get('/api/local/evidence').json()['data']==invoke(s)['data']
        assert web.get('/api/local/capabilities').json()['data']['version']=='three-layer.v1'


def test_authorization_rechecked_after_model_call(tmp_path):
    t,s,_=assignment(tmp_path)
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    def model(messages,info):
        t.unpair(s.identity.id)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'message':'x','next_steps':['y'],'boundary':'z'})])
    with pytest.raises(PermissionError):asyncio.run(run_agent(t,{'peer_id':s.identity.id},FunctionModel(model)))


def test_model_cannot_save_ungrounded_draft_without_reading_evidence(tmp_path):
    s=instance(tmp_path,'student','S')
    model=TestModel(call_tools=[],custom_output_args={'message':'An unsupported suggestion','next_steps':['x'],'boundary':'y'})
    with pytest.raises(ValueError,match='未读取必要'):
        asyncio.run(run_agent(s,{},model))
    assert not s.service.resources()


def test_uninitialized_device_has_no_new_capabilities(tmp_path):
    r=LocalRuntime(tmp_path,MemoryVault())
    with pytest.raises(PermissionError):invoke(r,'architecture.describe')
    async def check():assert {t.name for t in await create_mcp(r).list_tools()}=={'get_local_status'}
    asyncio.run(check())

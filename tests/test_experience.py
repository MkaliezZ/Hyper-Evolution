import asyncio,json
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse,ToolCallPart
from test_local_runtime import instance,pair,drain,MemoryVault
from test_companion_study import material
from test_workspaces import w,select
from base.app.local_runtime import LocalRuntime
from base.app.local_agent import run_agent
from base.app.local_backup import export_backup,restore_backup
from base.app.companion.functional.experience_contracts import ExperienceRequest,ExperienceResult,PAYLOADS
from growth_local.web import create_app
from growth_local.mcp import create_mcp

def call(r,op,payload=None,key=None,version='v11'):
    return r.invoke_capability({'contract_version':'companion.capability.'+version,'request_id':key or uuid4().hex,
        'operation':op,'payload':payload or {}})['data']

def self_work(s):
    call(s,'experience.select',{'experience':'self'})
    m=material(s)
    result=call(s,'self.start',{'source':{'material_id':m['id'],'revision':m['revision'],'source_hash':m['source_hash']},
        'goal':'说明观察与条件','method':'apply'})
    tid=result['task_id'];s.submit(tid,{},'A garden offers shade.',[],'first')
    return tid,s.task(tid)['attempts'][-1]['id']

def test_mode_changes_projection_not_role_and_legacy_archive_stays_readonly(tmp_path):
    s=instance(tmp_path/'s','student','S');t=instance(tmp_path/'t','teacher','T');pair(t,s)
    assert s.status()['experience']['id']=='student' and s.status()['experience']['brand']=='Evolver' and t.status()['experience']['brand']=='Enlighter'
    w(s,'initialize');call(s,'experience.select',{'experience':'self'})
    assert s.role=='student' and len(s.peers())==1 and s.status()['experience']['id']=='self'
    assert s.status()['experience']['brand']=='Self-Evolver'
    with pytest.raises(PermissionError):call(s,'experience.select',{'experience':'teacher'})
    with pytest.raises(PermissionError):call(t,'experience.select',{'experience':'self'})
    select(s,'english');assert s.status()['experience']['id']=='self'
    select(s,'mathematics');assert s.status()['experience']['id']=='self'
    again=LocalRuntime(s.folder,s.vault);assert again.status()['experience']['id']=='self'
    with pytest.raises(PermissionError):call(s,'roster.list',version='v10')

def test_source_policy_work_reflection_review_restart_and_no_teacher_review(tmp_path):
    s=instance(tmp_path,'student','S');tid,sid=self_work(s);task=s.task(tid)
    assert task['pack']['companion_plan']['runtime_policy']
    p={'task_id':tid,'submission_id':sid,'comment':'找到理由了，还需要更清楚地表达','next_step':'用新例子解释相同观点'}
    a=call(s,'self.reflect',p,key='same');assert a['record']['source_type']=='self_report'
    assert call(s,'self.reflect',p,key='same')['record']==a['record']
    call(s,'self.reflect',{**p,'comment':'补充一次反思'})
    assert len(call(s,'review.list',version='v3')['cards'])==1
    assert not s.task(tid)['attempts'][0]['review_history']
    restarted=LocalRuntime(s.folder,s.vault)
    assert call(restarted,'self.context')['tasks'][0]['id']==tid
    assert len(call(restarted,'assessment.list',{'task_id':tid},version='v2')['entries'])==2
    archive=export_backup(s,'synthetic-password-12');restored=LocalRuntime(tmp_path/'restored',MemoryVault())
    restore_backup(restored,archive,'synthetic-password-12');restored=LocalRuntime(restored.folder,restored.vault)
    assert restored.status()['experience']['id']=='self' and call(restored,'self.context')['tasks'][0]['id']==tid

def test_self_scope_rejects_teacher_assignment_and_independent_means_do_not_change(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s)
    task=t.assign(s.identity.id,'writing','assigned');drain(t,s)
    s.submit(task['id'],{},'Teacher assignment.',[],'attempt')
    call(s,'experience.select',{'experience':'self'});sid='local-submission-not-yet-synced'
    assert not call(s,'self.context')['tasks']
    with pytest.raises(PermissionError):call(s,'self.feedback_context',{'task_id':task['id'],'submission_id':sid})
    with pytest.raises(PermissionError):call(s,'self.start',{'source':{'task_id':task['id']},'goal':'改变任务要求'})
    call(s,'experience.select',{'experience':'student'})
    assert s.task(task['id'])['origin']=='teacher'
    with pytest.raises(PermissionError):call(s,'self.context')

@pytest.mark.parametrize('quotes',[['A garden offers shade.'],['A garden','offers shade.']])
def test_own_api_agent_reads_evidence_saves_suggestion_and_rejects_changed_mode(tmp_path,quotes):
    s=instance(tmp_path,'student','S');tid,sid=self_work(s)
    def model(messages,info):
        seen={getattr(p,'tool_name','') for m in messages for p in m.parts}
        if 'get_self_work' not in seen:return ModelResponse(parts=[ToolCallPart('get_self_work',{})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'outcome':'partial','comment':'有理由，可以再解释怎样帮助人。',
            'next_step':'补充一个具体场景。','evidence_quotes':quotes,'limitations':[]})])
    result=asyncio.run(run_agent(s,{'mode':'self_review','task_id':tid,'submission_id':sid},FunctionModel(model)))
    record=result['assessment']['record'];assert record['source_type']=='model_suggestion' and not result['teacher_review_created']
    assert result['output']['evidence_quotes']==quotes
    assert record['dimensions'][0]['evidence']==quotes[0]
    assert record['evidence']['answer_hash']==call(s,'self.feedback_context',{'task_id':tid,'submission_id':sid})['answer_hash']
    assert not s.task(tid)['attempts'][0]['review_history']
    def changed(messages,info):
        response=model(messages,info)
        if response.parts[0].tool_name!='get_self_work':call(s,'experience.select',{'experience':'student'})
        return response
    with pytest.raises((ValueError,PermissionError)):asyncio.run(run_agent(s,{'mode':'self_review','task_id':tid,'submission_id':sid},FunctionModel(changed)))
    assert len(call(s,'assessment.list',{'task_id':tid},version='v2')['entries'])==1

def test_self_feedback_validation_no_unseen_media_or_fabricated_quotes():
    from base.app.companion.aesthetic.self_feedback import validate
    c={'text':'','answers':{},'material':'Example','unobserved':['audio_not_listened']}
    p={'outcome':'partial','evidence_quotes':[],'limitations':['audio not heard']}
    with pytest.raises(ValueError):validate(p,c)
    validate({**p,'outcome':'ungraded'},c)
    with pytest.raises(ValueError):validate({**p,'outcome':'ungraded','evidence_quotes':['invented']},c)
    with pytest.raises(ValueError):validate({**p,'outcome':'partial'},dict(c,text='Visible answer'))

def test_v11_http_mcp_and_setup_role_mapping(tmp_path):
    r=LocalRuntime(tmp_path/'s',MemoryVault());app=create_app(r.folder,runtime=r,network=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/local/session',json={'bootstrap':app.state.bootstrap})
        bad=client.post('/api/local/setup',json={'role':'teacher','experience':'self','name':'S'})
        assert bad.status_code==400 and not r.profile
        response=client.post('/api/local/setup',json={'role':'self','name':'S'})
        assert response.status_code==200 and response.json()['profile']['role']=='student' and response.json()['experience']['id']=='self'
        raw={'contract_version':'companion.capability.v11','request_id':'same-view','operation':'experience.read','payload':{}}
        expected=r.invoke_capability(raw);assert client.post('/api/local/capabilities/invoke',json=raw).json()==expected
        result=asyncio.run(create_mcp(r).call_tool('invoke_companion_capability',{'request':raw}))
        actual=result[1] if isinstance(result,tuple) else json.loads(result[0].text if isinstance(result,list) else result.content[0].text)
        assert actual==expected
        assert client.post('/api/local/jobs',json={'mode':'self_review','task_id':'missing','submission_id':'missing'}).status_code in [400,403,404]

def test_v11_schema_snapshot():
    root=Path(__file__).resolve().parents[1]/'docs/contracts'
    for kind,model in [('request',ExperienceRequest),('result',ExperienceResult)]:
        assert json.loads((root/f'companion.capability.v11.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    assert json.loads((root/'companion.capability.v11.payloads.schema.json').read_text(encoding='utf8'))=={k:v.model_json_schema() for k,v in PAYLOADS.items()}

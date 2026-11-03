import asyncio,copy,json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from test_local_runtime import instance,pair,drain,MemoryVault
from base.app.local_runtime import LocalRuntime
from base.app.companion.functional.workspaces import host
from base.app.companion.functional.planning import agent_context
from base.app.local_backup import export_backup,restore_backup
from growth_local.web import create_app
from growth_local.mcp import create_mcp


def req(op,payload=None,peer=None,key=None):
    return {'contract_version':'companion.capability.v9','operation':'planning.'+op,
        'payload':payload or {},'peer_id':peer,'request_id':key or uuid4().hex}


def call(r,op,payload=None,peer=None,key=None):return r.invoke_capability(req(op,payload,peer,key))['data']


def content(**kw):return {'current_situation':'正在准备一次合成项目展示','stage':'preparing','goal':'用一个具体例子说明观点',
    'requirements':[{'requirement':'能够提出观点并说明依据','current_evidence':'已有一次文字初稿','gap':'观点和例子需要衔接',
        'next_action':'选择一份新材料写一段说明','completion_standard':'用自己的例子说清理由，请老师反馈'}],**kw}


def save(r,peer=None,**kw):return call(r,'save',{'content':content(**kw)},peer)['plan']


def share(r,p,peer=None,receiver=None,key=None):return call(r,'share',{'id':p['id'],'expected_revision':p['revision'],
    'content_hash':p['content_hash'],'receiver_id':receiver},peer,key)


def select(r,subject):
    return r.invoke_capability({'contract_version':'companion.capability.v8','operation':'workspace.select','request_id':uuid4().hex,'payload':{'subject':subject}})


def test_versions_cas_idempotence_and_recovery_without_automatic_sharing(tmp_path):
    s=instance(tmp_path,'student','合成学生');raw=req('save',{'content':content()},key='save-one')
    a=s.invoke_capability(raw)['data']['plan']
    with s.db() as db:assert db.execute('SELECT COUNT(*) FROM local_outbox').fetchone()[0]==0
    assert s.invoke_capability(raw)['data']['plan']==a
    with s.db() as db:db.execute('UPDATE companion_requests SET result=NULL WHERE id=?',('save-one',))
    assert s.invoke_capability(raw)['data']['plan']==a
    b=call(s,'save',{'id':a['id'],'expected_revision':1,'content':content(goal='第二版目标')})['plan']
    assert b['revision']==2 and b['parent_hash']==a['content_hash']
    with pytest.raises(ValueError):call(s,'save',{'id':a['id'],'expected_revision':1,'content':content()})
    with s.db() as db:assert db.execute('SELECT COUNT(*) FROM companion_growth_plans').fetchone()[0]==2


def test_direction_unknown_is_saved_without_fixed_english_gaps_or_scores(tmp_path):
    s=instance(tmp_path,'student','合成学生')
    result=call(s,'save',{'content':{'current_situation':'还在探索合成研究方向'}})
    assert result['plan']['content']['goal']=='' and result['plan']['content']['requirements']==[]
    assert result['policy']['score']=='not_generated' and result['policy']['opportunity_search']=='not_connected'
    assert result['policy']['stage_source']=='填写者声明'
    assert result['policy']['missing'] and '听力' not in json.dumps(result,ensure_ascii=False)


def test_teacher_scope_and_remote_copy_are_separate_and_readonly(tmp_path):
    t=instance(tmp_path/'t','teacher','合成老师');s=instance(tmp_path/'s','student','合成学生');u=instance(tmp_path/'u','student','另一学生');pair(t,s);pair(t,u)
    with pytest.raises(ValueError):call(t,'context')
    p=save(s);share(s,p,receiver=t.identity.id);drain(s,t)
    remote=call(t,'read',{'id':p['id']},s.identity.id)['plan'];assert remote['signature_verified']
    with pytest.raises(PermissionError):call(t,'read',{'id':p['id']},u.identity.id)
    with pytest.raises(PermissionError):call(t,'save',{'id':p['id'],'expected_revision':1,'content':content()},s.identity.id)
    proposal=save(t,s.identity.id,goal='老师提供的另一个目标');share(t,proposal,s.identity.id,key='teacher-share');share(t,proposal,s.identity.id,key='teacher-share');drain(t,s)
    assert call(s,'read',{'id':proposal['id']})['plan']['signature_verified']
    assert call(s,'read',{'id':p['id']})['plan']['content']['goal']!=proposal['content']['goal']
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError):call(t,'read',{'id':proposal['id']},s.identity.id)
    assert call(s,'read',{'id':p['id']})['plan']


def test_share_requires_exact_version_valid_receiver_and_current_protocol(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s);p=save(s)
    with pytest.raises(PermissionError):share(s,p,receiver='unpaired')
    with pytest.raises(ValueError):share(s,{**p,'content_hash':'a'*64},receiver=t.identity.id)
    s.save_config('peer-planning:'+t.identity.id,None)
    with pytest.raises(ValueError,match='更新'):share(s,p,receiver=t.identity.id)
    assert not s.pending(t.identity.id)


def test_signed_records_keep_subject_scope_and_do_not_switch_recipient(tmp_path):
    tr=instance(tmp_path/'t','teacher','T');sr=instance(tmp_path/'s','student','S');pair(tr,sr)
    for r in [tr,sr]:r.invoke_capability({'contract_version':'companion.capability.v8','operation':'workspace.initialize','payload':{},'request_id':'init'})
    t,s=host(tr),host(sr);select(t,'mathematics');select(s,'english')
    p=save(t,s.identity.id);share(t,p,s.identity.id);drain(t,s)
    assert s.current()=='english' and not call(s,'context')['plans']
    select(s,'mathematics');assert call(s,'read',{'id':p['id']})['plan']['content_hash']==p['content_hash']
    select(t,'science')
    with pytest.raises(KeyError):call(t,'read',{'id':p['id']},s.identity.id)


def test_forged_content_and_subject_identity_are_rejected(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s);p=save(s);share(s,p,receiver=t.identity.id)
    envelope=copy.deepcopy(s.pending(t.identity.id)[0]);envelope['body']['payload']['plan']['content']['goal']='篡改内容'
    with pytest.raises(Exception):t.receive(envelope)
    from base.app.companion.assets.planning import seal
    wrong=seal({**p,'subject_device':'someone-else'})
    raw={k:v for k,v in wrong.items() if k not in ['scope','signature_verified']}
    signed=s.identity.envelope(t.identity.id,'growth.plan',{'plan':raw},uuid4().hex)
    with pytest.raises(PermissionError):t.receive(signed)


def test_public_contract_rejects_spoofed_scores_and_bad_source_links(tmp_path):
    s=instance(tmp_path,'student','S')
    with pytest.raises(ValueError):call(s,'save',{'content':{**content(),'readiness_score':99}})
    with pytest.raises(ValueError):call(s,'save',{'content':content(requirements=[{'requirement':'source','source_url':'javascript:alert(1)'}])})


def test_http_mcp_and_own_agent_use_same_local_planning(tmp_path):
    s=instance(tmp_path,'student','S');app=create_app(s.folder,runtime=s,network=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/local/session',json={'bootstrap':app.state.bootstrap})
        p=client.post('/api/local/capabilities/invoke',json=req('save',{'content':content()})).json()['data']['plan']
        server=create_mcp(s);out=asyncio.run(server.call_tool('invoke_companion_capability',{'request':req('read',{'id':p['id']})}))
        assert not getattr(out,'isError',False)
        assert p['content_hash'] in str(out)
        from base.app.local_agent import learning_context
        context=learning_context(s);assert context['growth_orientation'][0]['goal']==p['content']['goal']
        assert 'source_url' not in str(context['growth_orientation'][0]['requirements'])


def test_growth_records_survive_encrypted_backup(tmp_path):
    s=instance(tmp_path/'s','student','S');p=save(s)
    raw=export_backup(s,'synthetic-growth-password');assert b'current_situation' not in raw
    restored=LocalRuntime(tmp_path/'restored',MemoryVault());restore_backup(restored,raw,'synthetic-growth-password')
    restored=LocalRuntime(restored.folder,restored.vault)
    assert call(restored,'read',{'id':p['id']})['plan']['content_hash']==p['content_hash']


def test_teacher_can_share_first_plan_in_new_subject_without_assigning_dummy_task(tmp_path):
    tr=instance(tmp_path/'t','teacher','T');sr=instance(tmp_path/'s','student','S');pair(tr,sr)
    for r in [tr,sr]:r.invoke_capability({'contract_version':'companion.capability.v8','operation':'workspace.initialize','payload':{},'request_id':'init'})
    t,s=host(tr),host(sr)
    created=t.invoke_capability({'contract_version':'companion.capability.v8','operation':'workspace.create','payload':{'name':'合成新学科'},'request_id':'create-subject'})['data']
    sid=created['subject']['id'];select(t,sid);p=save(t,s.identity.id);share(t,p,s.identity.id);drain(t,s)
    assert s.current()=='english';select(s,sid)
    assert call(s,'read',{'id':p['id']})['plan']['signature_verified']
    assert not call(s,'context')['tasks']


def test_v9_schema_snapshots_and_bounded_agent_context(tmp_path):
    from pathlib import Path
    from base.app.companion.functional.planning_contracts import PlanningRequest,PlanningResult
    folder=Path(__file__).resolve().parents[1]/'docs/contracts'
    for kind,model in [('request',PlanningRequest),('result',PlanningResult)]:
        assert json.loads((folder/f'companion.capability.v9.{kind}.schema.json').read_text(encoding='utf-8'))==model.model_json_schema()
    s=instance(tmp_path,'student','S');save(s,current_situation='界'*2000,goal='目'*1000,question='问'*1000,
        requirements=[{'requirement':'要'*500,'current_evidence':'证'*1000,'gap':'差'*500,'next_action':'行'*1000,'completion_standard':'标'*1000}]*6)
    assert len(json.dumps(agent_context(s),ensure_ascii=False))<2400

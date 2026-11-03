import asyncio,json
from uuid import uuid4
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from test_local_runtime import instance,pair,drain,MemoryVault
from test_companion_study import material,create
from base.app.local_runtime import LocalRuntime
from base.app.local_backup import export_backup,restore_backup
from base.app.companion.functional.workspaces import host
from growth_local.web import create_app
from growth_local.mcp import create_mcp

def w(r,op,payload=None,key=None):return r.invoke_capability({'contract_version':'companion.capability.v8','request_id':key or uuid4().hex,'operation':'workspace.'+op,'payload':payload or {}})['data']
def cap(r,op,payload=None,version='v2',peer=None,key=None):return r.invoke_capability({'contract_version':'companion.capability.'+version,'request_id':key or uuid4().hex,'operation':op,'payload':payload or {},'peer_id':peer})['data']
def select(r,subject):return w(r,'select',{'subject':subject})

def test_independent_databases_sources_tasks_and_cross_subject_id_rejection(tmp_path):
    root=instance(tmp_path,'student','合成学生');w(root,'initialize');r=host(root)
    select(r,'english');e=material(r);et=create(r,e)['data']['task_id']
    select(r,'mathematics');assert cap(r,'material.list')['materials']==[];assert r.student_dashboard()['tasks']==[]
    with pytest.raises(PermissionError):r.start_self('diagnostic','no-english-exam-in-math')
    with pytest.raises((KeyError,PermissionError)):r.task(et)
    with pytest.raises((KeyError,PermissionError)):cap(r,'material.read',{'material_id':e['id']})
    m=material(r);mt=create(r,m)['data']['task_id'];assert r.task(mt)
    assert (tmp_path/'subjects/english/base.sqlite3').is_file() and (tmp_path/'subjects/mathematics/base.sqlite3').is_file()
    assert (tmp_path/'subjects/mathematics/materials'/m['id']/'v1.txt').read_text(encoding='utf8')==cap(r,'material.read',{'material_id':m['id']})['text']
    select(r,'english');assert [t['id'] for t in r.student_dashboard()['tasks']]==[et]
    assert [v['id'] for v in cap(r,'material.list')['materials']]==[e['id']]
    assert [v['id'] for v in cap(r,'academic.material.list',{'subject':'all'},'v7')['materials']]==[e['id']]
    with pytest.raises(PermissionError):cap(r,'academic.material.list',{'subject':'mathematics'},'v7')
    assert cap(r,'academic.context',version='v7')['selection']['subject']=='english'

def test_only_explicit_legacy_sources_migrate_and_history_is_preserved(tmp_path):
    root=instance(tmp_path,'student','合成学生')
    known=cap(root,'academic.material.save',{'subject':'mathematics','title':'明确归属','source':'合成','text':'Six times four equals twenty-four.'},'v7')['material']
    unknown=material(root);old=create(root,unknown)['data']['task_id']
    result=w(root,'initialize');assert result['migration']['classified_sources_copied']==1
    r=host(root);select(r,'mathematics');assert [v['id'] for v in cap(r,'material.list')['materials']]==[known['id']]
    select(r,'english');assert cap(r,'material.list')['materials']==[] and r.student_dashboard()['tasks']==[]
    select(r,'legacy');assert any(t['id']==old for t in r.student_dashboard()['tasks'])
    assert {v['id'] for v in cap(r,'material.list')['materials']}=={known['id'],unknown['id']}
    with pytest.raises(PermissionError):cap(r,'material.save',{'title':'bad','source':'bad','text':'bad'})
    with pytest.raises(PermissionError):r.submit(old,{},'bad',[],'bad')
    w(r,'legacy.import',{'subject':'science','asset_kind':'text','asset_id':unknown['id'],'revision':unknown['revision'],'source_hash':unknown['source_hash'],'human_confirmed':True})
    select(r,'science');assert [v['id'] for v in cap(r,'material.list')['materials']]==[unknown['id']]

def test_signed_pair_delivery_routes_to_subject_without_changing_student_selection(tmp_path):
    tr=instance(tmp_path/'t','teacher','合成老师');sr=instance(tmp_path/'s','student','合成学生');pair(tr,sr)
    w(tr,'initialize');w(sr,'initialize');t,s=host(tr),host(sr)
    select(t,'mathematics');select(s,'english');m=material(t);tid=create(t,m,s.identity.id)['data']['task_id']
    drain(t,s);assert s.current()=='english' and s.student_dashboard()['tasks']==[]
    with pytest.raises((KeyError,PermissionError)):s.task(tid)
    select(s,'mathematics');assert s.task(tid)['signature_verified']
    s.submit(tid,{},'The supported relationship is proportional.',[],'first');drain(s,t);drain(t,s)
    task=t.task(tid);sid=task['attempts'][0]['id'];t.feedback(sid,'Use the actual quantities.','Try a different quantity.','needs_revision',None,'feedback')
    drain(t,s);assert s.task(tid)['attempts'][-1]['evaluation']['judgement']=='needs_revision'
    select(s,'science');assert s.student_dashboard()['tasks']==[]
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError):t.teacher_dashboard(s.identity.id)

def test_custom_subject_creates_new_folder_and_cannot_escape(tmp_path):
    root=instance(tmp_path,'student','合成学生');w(root,'initialize');r=host(root)
    created=w(r,'create',{'name':'物理研习'},key='custom-physics');subject=created['subject']['id']
    assert w(r,'create',{'name':'物理研习'},key='custom-physics')['subject']['id']==subject
    with pytest.raises(ValueError):w(r,'create',{'name':'Different'},key='custom-physics')
    select(r,subject);m=material(r)
    assert Path(created['folder']).is_relative_to(tmp_path.resolve()) and Path(created['folder'],'materials',m['id'],'v1.txt').is_file()
    assert subject in cap(r,'academic.catalog',version='v7')['subjects']
    with pytest.raises(ValueError):select(r,'../../outside')
    select(r,'english');assert cap(r,'material.list')['materials']==[]

def test_request_pin_does_not_change_mid_job_and_shared_model_config_is_consistent(tmp_path):
    root=instance(tmp_path,'student','合成学生');w(root,'initialize');r=host(root);select(r,'mathematics')
    with r.bind():
        pinned=r.active();select(r,'science')
        assert r.active() is pinned
        job=r.create_job({'mode':'learn','prompt':'synthetic bounded fixture'})
    assert r.current()=='science'
    with pytest.raises(KeyError):r.job(job)
    select(r,'mathematics');assert r.job(job)
    r.save_model({'provider':'deepseek','base_url':'https://api.deepseek.com','model':'synthetic-model'},'synthetic-key',remember=False)
    select(r,'science');assert r.model_status()['configured'] and r.active().model_key()=='synthetic-key'

def test_encrypted_backup_restores_all_subject_databases_and_originals(tmp_path):
    root=instance(tmp_path/'original','student','合成学生');w(root,'initialize');r=host(root)
    select(r,'english');e=material(r);select(r,'mathematics');m=material(r)
    raw=export_backup(r,'synthetic-password-12');assert b'Some nearby paths cooled' not in raw
    target=LocalRuntime(tmp_path/'restored',MemoryVault());restore_backup(target,raw,'synthetic-password-12')
    target=LocalRuntime(target.folder,target.vault);rr=host(target)
    select(rr,'mathematics');assert [v['id'] for v in cap(rr,'material.list')['materials']]==[m['id']]
    select(rr,'english');assert [v['id'] for v in cap(rr,'material.list')['materials']]==[e['id']]
    assert rr.identity.id==r.identity.id

def test_http_and_mcp_share_workspace_switch_and_reject_cross_subject_ids(tmp_path):
    root=instance(tmp_path,'student','合成学生');w(root,'initialize');r=host(root);select(r,'mathematics');m=material(r)
    app=create_app(root.folder,runtime=root,network=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.post('/api/local/session',json={'bootstrap':app.state.bootstrap})
        server=create_mcp(root)
        raw={'contract_version':'companion.capability.v8','operation':'workspace.select','payload':{'subject':'science'},'request_id':'select-science'}
        result=asyncio.run(server.call_tool('invoke_companion_capability',{'request':raw}));assert not getattr(result,'isError',False)
        assert client.get('/api/local/status').json()['workspace']['active']=='science'
        denied=client.post('/api/local/capabilities/invoke',json={'contract_version':'companion.capability.v2','request_id':'read-math','operation':'material.read','payload':{'material_id':m['id']}})
        assert denied.status_code in [403,404]
        stale=client.get('/api/local/dashboard',headers={'X-Growth-Workspace':'mathematics'})
        assert stale.status_code==409

def test_material_file_integrity_and_generic_model_context_do_not_use_english_exam(tmp_path):
    from base.app.local_agent import learning_context,run_agent
    from pydantic_ai.models.test import TestModel
    root=instance(tmp_path,'student','合成学生');w(root,'initialize');r=host(root);select(r,'science')
    m=material(r);create(r,m);context=learning_context(r)
    assert context['workspace_subject']=='science' and context['exam'] is None
    out=asyncio.run(run_agent(r,{'mode':'coach'},TestModel(custom_output_args={'message':'比较实验条件。','next_steps':['核对控制变量。'],'boundary':'需要专业核对'})))
    assert not out['automatic_teacher_judgement']
    with pytest.raises(ValueError):asyncio.run(run_agent(r,{'mode':'draft'},TestModel()))
    file=r.folder/'materials'/m['id']/'v1.txt';file.write_text('unrecorded external edit',encoding='utf8')
    with pytest.raises(ValueError,match='文件'):cap(r,'material.read',{'material_id':m['id']})

def test_existing_english_audio_migrates_with_hash_and_broken_source_stays_in_legacy(tmp_path):
    import hashlib
    root=instance(tmp_path,'teacher','合成老师');folder=root.folder/'media';folder.mkdir(exist_ok=True)
    raw=b'synthetic engineering audio bytes';old=folder/'fixture.mp3';old.write_bytes(raw)
    pack={'id':'synthetic-audio-fixture','exam':'ielts','audio_sha256':hashlib.sha256(raw).hexdigest(),'media_path':str(old),'status':'pending_review'}
    broken={**pack,'id':'missing-fixture','media_path':str(folder/'missing.mp3')}
    with root.db() as db:
        for value in [pack,broken]:db.execute('INSERT INTO hd_resources VALUES (?,?)',(value['id'],json.dumps(value)))
    result=w(root,'initialize');migration=result['migration']['english_resources_migration']
    assert migration['copied']==1 and migration['issues'][0]['id']=='missing-fixture'
    r=host(root);select(r,'english');resources=r.service.resources();assert len(resources)==1
    assert Path(resources[0]['media_path']).read_bytes()==raw and Path(resources[0]['media_path']).is_relative_to(root.folder/'subjects/english')
    assert len(root.service.resources())==2 and old.read_bytes()==raw

def test_subject_signature_is_verified_before_creating_unknown_folders(tmp_path):
    import copy
    tr=instance(tmp_path/'teacher','teacher','合成老师');sr=instance(tmp_path/'student','student','合成学生');pair(tr,sr)
    w(tr,'initialize');w(sr,'initialize');t,s=host(tr),host(sr);select(t,'mathematics');m=material(t);create(t,m,s.identity.id)
    forged=copy.deepcopy(t.pending(s.identity.id)[0]);forged['body']['payload']['subject_workspace']['id']='subject-'+'a'*16
    with pytest.raises(PermissionError):s.receive(forged)
    assert not (sr.folder/'subjects'/('subject-'+'a'*16)).exists()

def test_teaching_scenario_catalog_and_execution_follow_the_subject_policy(tmp_path):
    root=instance(tmp_path,'student','合成学生');w(root,'initialize');r=host(root);select(r,'mathematics')
    scenarios=cap(r,'policy.catalog',version='v3')['scenarios']
    assert 'math_concept' in scenarios and 'rhetorical_purpose' not in scenarios and 'listening' not in scenarios
    with pytest.raises(ValueError,match='情境'):cap(r,'policy.plan',{'goal':'Synthetic task','scenario':'rhetorical_purpose'},'v3')
    select(r,'english');scenarios=cap(r,'policy.catalog',version='v3')['scenarios']
    assert 'rhetorical_purpose' in scenarios and 'math_concept' not in scenarios

def test_signed_transport_ack_drains_an_inactive_subject_queue_and_old_peers_are_not_sent_scoped_data(tmp_path):
    tr=instance(tmp_path/'teacher','teacher','合成老师');sr=instance(tmp_path/'student','student','合成学生');pair(tr,sr)
    w(tr,'initialize');w(sr,'initialize');t,s=host(tr),host(sr);select(t,'mathematics');m=material(t);create(t,m,s.identity.id)
    envelope=t.pending(s.identity.id)[0];s.receive(envelope);select(t,'science')
    ack=s.identity.envelope(t.identity.id,'ack',{'id':envelope['body']['id']},uuid4().hex);t.receive(ack)
    assert not any(e['body']['id']==envelope['body']['id'] for e in t.pending(s.identity.id))
    tr.save_config('peer-workspace:'+s.identity.id,None);select(t,'mathematics')
    with pytest.raises(ValueError,match='旧版'):t.active().queue(s.identity.id,'task.updated',{'task':{}},'blocked-old-peer')

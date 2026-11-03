import asyncio,json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from test_local_runtime import instance,pair,drain,MemoryVault
from test_companion_continuity import activity,answer,save_page
from base.app.local_runtime import LocalRuntime
from base.app.local_backup import export_backup,restore_backup
from base.app.companion.aesthetic.cases import case_catalog
from growth_local.web import create_app
from growth_local.mcp import create_mcp

def call(r,op,payload=None,peer=None,key=None):
    return r.invoke_capability({'contract_version':'companion.capability.v4','request_id':key or uuid4().hex,
        'operation':op,'payload':payload or {},'peer_id':peer})['data']

def source(r,title='Garden',text='A garden cooled local paths. Distant streets changed little.',**extra):
    saved=r.invoke_capability({'contract_version':'companion.capability.v2','request_id':uuid4().hex,'operation':'material.save',
        'payload':{'title':title,'text':text,'source':'Team original synthetic fixture',**extra}})['data']['material']
    return {**saved,'text':text}

def index(r,peer=None,**config):return call(r,'index.build',config,peer)['index']
def search(r,i,query,peer=None,**kw):return call(r,'index.search',{'index_id':i['id'],'query':query,**kw},peer)
def bench(r,m,peer=None):
    return call(r,'benchmark.save',{'title':'Fixed synthetic queries','label_origin':'synthetic','cases':[
        {'case_id':'exact','query':'Distant streets','expected':[{'source':{'material_id':m['id']},'quote':'Distant streets changed little.'}]},
        {'case_id':'reordered','query':'streets garden','expected':[{'source':{'material_id':m['id']}}]},
        {'case_id':'negative','query':'Mars garden','expected':[]}]},peer)['benchmark']

def test_index_versions_reuse_same_manifest_and_exclude_superseded_sources(tmp_path):
    s=instance(tmp_path,'student','S');m=source(s);first=index(s)
    assert index(s)['id']==first['id']
    assert search(s,first,'Distant streets')['hits'][0]['text'] in m['text']
    changed=source(s,text='A new garden revision.',material_id=m['id'],expected_revision=1)
    assert search(s,first,'Distant streets')['state']=='source_unavailable'
    second=index(s)
    assert second['generation']==2 and second['parent_id']==first['id'] and second['manifest_hash']!=first['manifest_hash']
    assert search(s,second,'no such expression')['state']=='no_match'
    assert len(call(s,'index.list')['indexes'])==2

def test_fixed_suite_compares_real_paths_and_preserves_negative_regressions(tmp_path):
    s=instance(tmp_path,'student','S');m=source(s);i=index(s);b=bench(s,m)
    report=call(s,'benchmark.run',{'benchmark_id':b['id'],'index_ids':[i['id']]},key='run')['run']
    baseline,candidate=report['results']
    assert baseline['metrics']['hit_at_k']==.5 and candidate['metrics']['hit_at_k']==1
    assert baseline['metrics']['negative_false_positive_rate']==0 and candidate['metrics']['negative_false_positive_rate']==1
    assert candidate['cases'][0]['hits'][0]['source_ref']['source_hash']==m['source_hash']
    assert report['comparison_basis']=='same_current_corpus'
    assert call(s,'benchmark.run',{'benchmark_id':b['id'],'index_ids':[i['id']]},key='run')['run']==report
    other=index(s,chunk_size=160,overlap=20)
    assert other['manifest_hash']!=i['manifest_hash']
    assert len(call(s,'benchmark.run',{'benchmark_id':b['id'],'index_ids':[i['id'],other['id']]})['run']['results'])==4

def test_changed_ground_truth_is_not_scored_and_old_suite_is_immutable(tmp_path):
    s=instance(tmp_path,'student','S');m=source(s);i=index(s);b=bench(s,m)
    source(s,text='New source with a different conclusion.',material_id=m['id'],expected_revision=1)
    run=call(s,'benchmark.run',{'benchmark_id':b['id'],'index_ids':[i['id']]})['run']
    assert all(r['metrics']['not_scored']==2 and r['metrics']['positive_cases']==0 for r in run['results'])
    assert call(s,'benchmark.read',{'benchmark_id':b['id']})['benchmark']['case_set_hash']==b['case_set_hash']
    with pytest.raises(ValueError):call(s,'benchmark.save',{'title':'Bad quotation','cases':[{'case_id':'x','query':'x','expected':[{'source':{'material_id':m['id']},'quote':'fabricated'}]}]})

def test_teacher_student_scope_revocation_and_no_answer_or_note_indexing(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');u=instance(tmp_path/'u','student','U');pair(t,s);pair(t,u)
    m=source(t,text='SAFE_STIMULUS about gardens.');tid=activity(t,m,s.identity.id);drain(t,s)
    t.save_teacher_notes(s.identity.id,'PRIVATE_TEACHER_NOTE')
    i=index(t,s.identity.id);other=index(t,u.identity.id)
    assert search(t,i,'SAFE_STIMULUS',s.identity.id)['hits']
    with pytest.raises(PermissionError):search(t,i,'SAFE',u.identity.id)
    assert 'PRIVATE_TEACHER_NOTE' not in json.dumps(call(t,'index.read',{'index_id':i['id']},s.identity.id))
    si=index(s);assert search(s,si,'SAFE_STIMULUS')['hits']
    s.unpair(t.identity.id)
    assert not search(s,si,'SAFE_STIMULUS')['hits']
    assert call(s,'index.read',{'index_id':si['id']})['sources']==[]
    with pytest.raises(PermissionError):call(s,'index.list',peer=t.identity.id)

def test_original_image_only_indexes_declared_metadata(tmp_path):
    s=instance(tmp_path,'student','S');im=save_page(s,caption='UNVERIFIED_CAPTION only')
    i=index(s);found=search(s,i,'UNVERIFIED_CAPTION')
    assert found['hits'][0]['kind']=='image_metadata'
    assert found['hits'][0]['quality']['parsed']=='metadata_only_no_ocr'
    assert found['hits'][0]['source_ref']['source_hash']==im['source_hash']
    assert search(s,i,'ELEPHANT86243')['state']=='no_match'

def test_execution_failure_is_saved_separately_from_no_match(tmp_path):
    s=instance(tmp_path,'student','S');m=source(s);i=index(s);b=bench(s,m)
    with s.db() as db:
        row=db.execute('SELECT body FROM companion_indexes WHERE id=?',(i['id'],)).fetchone();body=json.loads(row['body'])
        body['config']['tokenizer']='retired-tokenizer'
        db.execute('UPDATE companion_indexes SET body=? WHERE id=?',(json.dumps(body),i['id']))
    assert search(s,i,'garden')['state']=='execution_failed'
    run=call(s,'benchmark.run',{'benchmark_id':b['id'],'index_ids':[i['id']]})['run']
    assert all(r['metrics']['execution_failed_cases']==3 and r['metrics']['positive_cases']==0 for r in run['results'])

def test_all_policy_pairs_execute_without_claiming_semantic_validation(tmp_path):
    s=instance(tmp_path,'student','S');cases=call(s,'policy.cases')['cases'];assert len(cases)==20
    result=call(s,'policy.check')['check']
    assert result['engineering_passed'] and result['professional_status']=='NOT_REVIEWED'
    assert next(c for c in result['cases'] if c['case_id']=='P07-counterexample')['actual_decision']['status']=='pass'
    assert next(c for c in cases if c['case_id']=='P07-counterexample')['professional_acceptance'].startswith('人工应拒绝')
    with pytest.raises(PermissionError):call(s,'policy.review.list')
    from base.app.companion.aesthetic.cases import validate_suite
    import copy
    invalid=copy.deepcopy(case_catalog());invalid['cases'][0]['expected']={}
    with pytest.raises(ValueError,match='空断言'):validate_suite(invalid)

def review_payload(check,pack='P04'):
    return {'check_id':check['id'],'pack':pack,'reviewer_name':'Synthetic reviewer','expertise_statement':'Self-declared test teacher',
        'intended_scope':'Engineering acceptance only; not a real pilot approval','conclusion':'approved_for_pilot',
        'human_confirmed':True,'observations':[{'case_id':c['case_id'],'verdict':'appropriate','reason':'Synthetic fixture review of the response boundary.'}
            for c in check['cases'] if c['pack']==pack]}

def test_policy_review_binds_exact_cases_and_pack_versions_and_does_not_publish(tmp_path,monkeypatch):
    t=instance(tmp_path,'teacher','T');check=call(t,'policy.check')['check'];payload=review_payload(check)
    saved=call(t,'policy.review.record',payload,key='review')['review']
    assert saved['effect']=='local_scoped_pilot_only_no_runtime_rule_change'
    assert call(t,'policy.review.record',payload,key='review')['review']==saved
    assert call(t,'policy.review.list',{'pack':'P04'})['reviews'][0]['current_binding']
    with pytest.raises(ValueError):call(t,'policy.review.record',{**payload,'human_confirmed':False})
    with pytest.raises(ValueError):call(t,'policy.review.record',{**payload,'observations':payload['observations'][:1]})
    with pytest.raises(ValueError):call(t,'policy.review.record',{**payload,'observations':[{**o,'verdict':'uncertain'} for o in payload['observations']]})
    from base.app.companion.functional import retrieval_service
    old=retrieval_service.binding
    monkeypatch.setattr(retrieval_service,'binding',lambda:{**old(),'engine_version':'changed'})
    assert not call(t,'policy.review.list')['reviews'][0]['current_binding']
    with pytest.raises(ValueError,match='变化'):call(t,'policy.review.record',payload)

def test_chinese_and_english_search_config_is_independent_of_user_model(tmp_path):
    s=instance(tmp_path,'student','S');source(s,'数学概念','连续不保证可导，需要用反例检验。');i=index(s)
    assert search(s,i,'连续 反例')['hits']
    s.save_config('model',{'model':'a-different-user-model'})
    assert index(s)['id']==i['id'] and i['config']['embedding'] is None

def test_v4_shared_web_and_mcp_and_backup(tmp_path):
    s=instance(tmp_path/'s','student','S');m=source(s);i=index(s);b=bench(s,m)
    request={'contract_version':'companion.capability.v4','request_id':'same','operation':'index.search','payload':{'index_id':i['id'],'query':'garden'}}
    with TestClient(create_app(s.folder,runtime=s,network=False),base_url='http://127.0.0.1',headers={'Authorization':'Bearer '+s.service.base.owner_token}) as web:
        response=web.post('/api/local/capabilities/invoke',json=request);assert response.status_code==200
    async def mcp():
        value=await create_mcp(s).call_tool('invoke_companion_capability',{'request':request})
        return value[1] if isinstance(value,tuple) else json.loads(value[0].text)
    result=asyncio.run(mcp())
    assert result['data']['hits']==response.json()['data']['hits']
    encrypted=export_backup(s,'Synthetic-restore-password-123');fresh=LocalRuntime(tmp_path/'restored',MemoryVault());restore_backup(fresh,encrypted,'Synthetic-restore-password-123')
    restored=LocalRuntime(fresh.folder,fresh.vault)
    assert call(restored,'benchmark.read',{'benchmark_id':b['id']})['benchmark']['case_set_hash']==b['case_set_hash']
    assert search(restored,i,'garden')['hits']


def test_index_chunk_tampering_is_not_returned_as_original_evidence(tmp_path):
    s=instance(tmp_path,'student','S');source(s);i=index(s)
    with s.db() as db:
        row=db.execute('SELECT body FROM companion_indexes WHERE id=?',(i['id'],)).fetchone();body=json.loads(row['body'])
        body['documents'][0]['chunks'][0]['text']='FABRICATED_EVIDENCE'
        db.execute('UPDATE companion_indexes SET body=? WHERE id=?',(json.dumps(body),i['id']))
    result=search(s,i,'FABRICATED_EVIDENCE')
    assert not result['hits'] and result['state']=='source_unavailable'


def test_local_agent_really_searches_authorized_index_and_keeps_source_version(tmp_path):
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse,ToolCallPart
    from base.app.local_agent import run_agent
    s=instance(tmp_path,'student','S');m=source(s);i=index(s)
    def model(messages,info):
        seen={getattr(part,'tool_name','') for message in messages for part in message.parts}
        for name,args in [('get_learning_evidence',{}),('get_exam_blueprint',{}),('search_local_sources',{'query':'Distant streets','index_id':i['id']})]:
            if name not in seen:return ModelResponse(parts=[ToolCallPart(name,args)])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'message':'A synthetic source-backed suggestion.','next_steps':['Check the original passage.'],'boundary':'Not a professional learning judgment.'})])
    result=asyncio.run(run_agent(s,{'prompt':'Use my indexed sources.'},FunctionModel(model)))
    assert 'search_local_sources' in result['tools_used'] and not result['automatic_teacher_judgement']


def test_benchmark_versions_history_and_recovery_do_not_overwrite_results(tmp_path):
    s=instance(tmp_path,'student','S');m=source(s);i=index(s);b=bench(s,m)
    payload={'benchmark_id':b['id'],'index_ids':[i['id']]};first=call(s,'benchmark.run',payload,key='recover')['run']
    with s.db() as db:db.execute("UPDATE companion_requests SET result=NULL WHERE id='recover'")
    assert call(s,'benchmark.run',payload,key='recover')['run']==first
    assert call(s,'benchmark.runs',{'benchmark_id':b['id']})['runs'][0]['id']==first['id']
    new=call(s,'benchmark.save',{'title':b['title'],'benchmark_id':b['id'],'expected_revision':1,'cases':b['cases'],'label_origin':'synthetic'})['benchmark']
    assert new['revision']==2
    assert call(s,'benchmark.read',{'benchmark_id':b['id'],'revision':1})['benchmark']['case_set_hash']==b['case_set_hash']
    assert call(s,'benchmark.result',{'run_id':first['id']})['run']['benchmark_revision']==1

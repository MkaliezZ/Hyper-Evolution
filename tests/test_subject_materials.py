import asyncio,base64,copy,json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from test_local_runtime import instance,pair,drain,MemoryVault
from test_companion_continuity import png
from base.app.local_runtime import LocalRuntime
from base.app.local_backup import export_backup,restore_backup
from growth_local.web import create_app
from growth_local.mcp import create_mcp

def request(op,payload=None,key=None,peer=None):return {'contract_version':'companion.capability.v7','request_id':key or uuid4().hex,
    'operation':op,'peer_id':peer,'payload':payload or {}}
def call(runtime,op,payload=None,key=None,peer=None):return runtime.invoke_capability(request(op,payload,key,peer))['data']
def legacy(runtime,op,payload=None):return runtime.invoke_capability({'contract_version':'companion.capability.v2','request_id':uuid4().hex,
    'operation':op,'payload':payload or {}})['data']
def text(subject='mathematics',**kw):return {'subject':subject,'title':subject+' synthetic material','source':'团队原创合成工程测试',
    'text':'Unit price stays six. Total cost equals six times the number of notebooks.',**kw}
def ids(runtime,subject,kind='materials'):return [m['id'] for m in call(runtime,'academic.material.list',{'subject':subject})[kind]]
def classify(runtime,m,subject,revision=0,kind='text',key=None):return call(runtime,'academic.asset.classify',{
    'asset_kind':kind,'asset_id':m['id'],'asset_revision':m['revision'],'source_hash':m['source_hash'],
    'subject':subject,'expected_revision':revision,'human_confirmed':True},key)

def test_existing_material_is_unclassified_without_guessing_from_text(tmp_path):
    s=instance(tmp_path,'student','合成学生');m=legacy(s,'material.save',{k:v for k,v in text('english').items() if k!='subject'})['material']
    assert ids(s,'english')==ids(s,'mathematics')==[] and ids(s,'unclassified')==[m['id']]
    classify(s,m,'english');assert ids(s,'english')==[m['id']] and ids(s,'mathematics')==ids(s,'unclassified')==[]
    assert legacy(s,'material.read',{'material_id':m['id']})['text']==text()['text']

def test_new_material_subjects_are_real_and_replay_does_not_duplicate(tmp_path):
    s=instance(tmp_path,'student','合成学生')
    m=call(s,'academic.material.save',text(),key='new-math')['material'];same=call(s,'academic.material.save',text(),key='new-math')['material']
    e=call(s,'academic.material.save',text('english'))['material']
    assert m==same and ids(s,'mathematics')==[m['id']] and ids(s,'english')==[e['id']]
    assert len(legacy(s,'material.list')['materials'])==2
    with pytest.raises(ValueError):call(s,'academic.material.save',text('science'),key='new-math')

def test_all_categories_lists_own_text_and_images_including_pending_without_changing_selection(tmp_path):
    s=instance(tmp_path/'student','student','合成学生');other=instance(tmp_path/'teacher','teacher','合成老师')
    before=call(s,'academic.context')['selection']
    math=call(s,'academic.material.save',text())['material'];english=call(s,'academic.material.save',text('english'))['material']
    pending=legacy(s,'material.save',{'title':'待分类合成材料','source':'原创','text':'A fixture with no assigned category.'})['material']
    page=call(s,'academic.page.save',{'subject':'science','title':'科学原图','source':'原创','data_base64':base64.b64encode(png()).decode()})['page']
    result=call(s,'academic.material.list',{'subject':'all'})
    assert set(v['id'] for v in result['materials'])=={math['id'],english['id'],pending['id']}
    assert [v['id'] for v in result['pages']]==[page['id']]
    assert result['counts']['science']==1 and result['unclassified_count']==1
    assert sum(result['counts'].values())==4
    assert call(s,'academic.context')['selection']==before
    assert not ids(other,'all') and not ids(other,'all','pages')

def test_classification_pins_current_source_and_uses_compare_and_save(tmp_path):
    s=instance(tmp_path,'student','合成学生');m=call(s,'academic.material.save',text())['material']
    classify(s,m,'science',revision=1)
    with pytest.raises(ValueError):classify(s,m,'english',revision=1)
    newer=legacy(s,'material.save',{'material_id':m['id'],'expected_revision':1,'title':m['title'],'source':m['source'],'text':'A genuinely different source revision.'})['material']
    assert ids(s,'science')==[] and ids(s,'unclassified')==[m['id']]
    info=call(s,'academic.asset.info',{'asset_kind':'text','asset_id':m['id']})['classification']
    assert info['state']=='needs_reclassification' and info['previous_subject']=='science'
    with pytest.raises(ValueError):classify(s,m,'english',revision=2)
    classify(s,newer,'english',revision=2);assert ids(s,'english')==[m['id']]

def test_scoped_revision_carries_explicit_category_without_rewriting_history(tmp_path):
    s=instance(tmp_path,'student','合成学生');m=call(s,'academic.material.save',text())['material']
    revised=call(s,'academic.material.save',text(material_id=m['id'],expected_revision=1,classification_revision=1,text='Updated math material.'))['material']
    assert revised['revision']==2 and revised['classification']['revision']==2 and ids(s,'mathematics')==[m['id']]
    assert legacy(s,'material.read',{'material_id':m['id'],'revision':1})['text']==text()['text']
    with pytest.raises(ValueError):call(s,'academic.material.save',text(material_id=m['id'],expected_revision=2,classification_revision=1))

def test_original_pages_are_subject_filtered_and_bytes_are_preserved(tmp_path):
    s=instance(tmp_path,'student','合成学生');raw=png()
    p=call(s,'academic.page.save',{'subject':'mathematics','title':'合成图示','source':'合成像素，仅工程用','data_base64':base64.b64encode(raw).decode()})['page']
    assert ids(s,'mathematics','pages')==[p['id']] and ids(s,'english','pages')==[]
    classify(s,p,None,revision=1,kind='page');assert ids(s,'unclassified','pages')==[p['id']]
    actual=s.invoke_capability({'contract_version':'companion.capability.v3','request_id':uuid4().hex,'operation':'page.read','payload':{'page_id':p['id']}})['data']
    assert base64.b64decode(actual['data_base64'])==raw

def test_categories_do_not_grant_access_to_peer_libraries(tmp_path):
    t=instance(tmp_path/'t','teacher','合成教师');s=instance(tmp_path/'s','student','合成学生');pair(t,s)
    m=call(t,'academic.material.save',text())['material']
    with pytest.raises(PermissionError):call(t,'academic.material.list',{'subject':'mathematics'},peer=s.identity.id)
    with pytest.raises(PermissionError):call(s,'academic.material.save',text(),peer=t.identity.id)
    with pytest.raises(KeyError):call(s,'academic.asset.info',{'asset_kind':'text','asset_id':m['id']})
    assert ids(s,'mathematics')==[]

def test_reclassifying_source_does_not_rewrite_signed_historical_task(tmp_path):
    t=instance(tmp_path/'t','teacher','合成教师');s=instance(tmp_path/'s','student','合成学生');pair(t,s)
    m=call(t,'academic.material.save',text())['material']
    task=t.invoke_capability({'contract_version':'companion.capability.v2','request_id':uuid4().hex,'operation':'activity.create','peer_id':s.identity.id,
        'payload':{'material_id':m['id'],'goal':'Explain the conditions in this source.','method':'understand'}})['data']['task_id']
    drain(t,s);before=copy.deepcopy(s.task(task));classify(t,m,'science',revision=1)
    assert s.task(task)==before and t.task(task)['pack']['stimulus']==text()['text']

def test_http_and_mcp_same_subject_contract_and_encrypted_restore(tmp_path):
    s=instance(tmp_path/'s','student','合成学生');app=create_app(s.folder,runtime=s,network=False)
    with TestClient(app,base_url='http://127.0.0.1',headers={'Authorization':'Bearer '+s.service.base.owner_token}) as web:
        saved=web.post('/api/local/capabilities/invoke',json=request('academic.material.save',text())).json()['data']['material']
        body=request('academic.material.list',{'subject':'mathematics'},key='same-subject-list')
        result=web.post('/api/local/capabilities/invoke',json=body);assert result.status_code==200
        mcp=asyncio.run(create_mcp(s).call_tool('invoke_companion_capability',{'request':body}))
        actual=json.loads(mcp[0].text) if isinstance(mcp,list) else mcp.structuredContent or json.loads(mcp.content[0].text)
        assert actual==result.json() and actual['data']['materials'][0]['id']==saved['id']
    encrypted=export_backup(s,'Synthetic-subject-recovery-123');fresh=LocalRuntime(tmp_path/'fresh',MemoryVault())
    restore_backup(fresh,encrypted,'Synthetic-subject-recovery-123');fresh=LocalRuntime(fresh.folder,fresh.vault)
    assert ids(fresh,'mathematics')==[saved['id']] and ids(fresh,'english')==[]

def test_interrupted_label_commit_can_resume_without_duplicate_material(tmp_path,monkeypatch):
    from base.app.companion.functional import academic_store
    s=instance(tmp_path,'student','合成学生');saved=academic_store.save;interrupt=[True]
    def crash_after_commit(runtime,kind,value):
        result=saved(runtime,kind,value)
        if kind=='asset_subject' and interrupt[0]:interrupt[0]=False;raise RuntimeError('synthetic interruption after label commit')
        return result
    monkeypatch.setattr(academic_store,'save',crash_after_commit)
    with pytest.raises(RuntimeError):call(s,'academic.material.save',text(),key='resumable')
    result=call(s,'academic.material.save',text(),key='resumable')['material']
    assert ids(s,'mathematics')==[result['id']] and len(legacy(s,'material.list')['materials'])==1

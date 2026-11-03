import asyncio,base64,hashlib,io,json
from datetime import datetime,timezone,timedelta
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel
from test_local_runtime import instance,pair,drain,MemoryVault
from test_companion_study import material
from base.app.local_runtime import LocalRuntime
from base.app.local_agent import run_agent,learning_context
from base.app.local_backup import export_backup,restore_backup
from base.app.companion.functional.continuity import memories,page,initialize
from base.app.companion.functional.continuity_contracts import Source
from growth_local.web import create_app
from growth_local.mcp import create_mcp

def call(r,operation,payload=None,peer=None,key=None):
    from uuid import uuid4
    return r.invoke_capability({'contract_version':'companion.capability.v3','request_id':key or uuid4().hex,
        'operation':operation,'payload':payload or {},'peer_id':peer})

def png(color='orange'):
    stream=io.BytesIO();Image.new('RGB',(80,50),color).save(stream,format='PNG');return stream.getvalue()

def save_page(r,color='orange',**kw):
    raw=png(color)
    return call(r,'page.save',{'title':'Original diagram','source':'Original synthetic example',
        'data_base64':base64.b64encode(raw).decode(),**kw})['data']['page']

def activity(r,m=None,peer=None,image=False,**kw):
    if m is None:m=save_page(r) if image else material(r)
    return call(r,'activity.create',{'source':{'page_id' if image else 'material_id':m['id'],'revision':m['revision'],'source_hash':m['source_hash']},
        'goal':'说明观察与条件','scenario':'visual_reading' if image else 'general','method':'apply',**kw},peer)['data']['task_id']

def answer(r,tid,key='first'):
    r.submit(tid,{},'Synthetic original work with a stated limitation.',[],key,{'additional_help':'No additional help in this synthetic check'})

def test_policy_v3_planning_uses_actual_source_and_gates_missing_media(tmp_path):
    s=instance(tmp_path,'student','S');m=material(s)
    base={'source':{'material_id':m['id']},'goal':'辨识声音中的改口','scenario':'listening'}
    p=call(s,'policy.plan',base)
    assert p['status']=='needs_input' and 'P05-R3' in p['data']['plan']['missing']
    with pytest.raises(ValueError,match='规则检查'):call(s,'activity.create',base)
    base.update(scenario='writing',method='apply')
    assert call(s,'policy.plan',base)['data']['plan']['form']=='draft_revision'
    base.update(form='matching')
    assert call(s,'policy.plan',base)['status']=='needs_input'

def test_original_bytes_and_frozen_versions_cross_signed_pairing(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s)
    image=save_page(t);tid=activity(t,image,s.identity.id,image=True);drain(t,s)
    got=call(s,'page.read',{'task_id':tid})['data']
    assert base64.b64decode(got['data_base64'])==png()
    assert got['source_hash']==hashlib.sha256(png()).hexdigest()
    assert call(t,'policy.task',{'task_id':tid},s.identity.id)['data']['plan']['scenario_id']=='visual_reading'
    save_page(t,'blue',page_id=image['id'],expected_revision=1)
    assert call(s,'page.read',{'task_id':tid})['data']['source_hash']==image['source_hash']
    assert len(call(t,'page.list')['data']['pages'])==1
    s.unpair(t.identity.id)
    with pytest.raises(PermissionError):call(s,'page.read',{'task_id':tid})

def test_invalid_image_hash_region_and_unsafe_payload_fail(tmp_path):
    s=instance(tmp_path,'student','S')
    with pytest.raises(ValueError):call(s,'page.save',{'title':'x','source':'x','data_base64':base64.b64encode(b'<svg>unsafe</svg>').decode()})
    image=save_page(s)
    with pytest.raises(ValueError):call(s,'page.read',{'page_id':image['id'],'region':[.8,.1,.2,.9]})
    with pytest.raises(ValueError):call(s,'page.read',{'page_id':image['id'],'source_hash':'0'*64})
    file=s.folder/'uploads'/('page-'+image['source_hash']);file.write_bytes(b'changed')
    with pytest.raises(ValueError,match='变化'):call(s,'page.read',{'page_id':image['id']})

def test_memory_correction_history_scope_and_explicit_model_opt_in(tmp_path):
    s=instance(tmp_path,'student','S');tid=activity(s);answer(s,tid)
    saved=call(s,'memory.capture',{'task_ids':[tid],'title':'Synthetic note'},key='capture')['data']['entry']
    assert call(s,'memory.capture',{'task_ids':[tid],'title':'Synthetic note'},key='capture')['data']['entry']==saved
    assert len(memories(s,for_model=True)['entries'])==1
    corrected=call(s,'memory.correct',{'memory_id':saved['id'],'expected_revision':1,'body':'My correction, not a verified mastery claim.'})['data']['entry']
    assert corrected['revision']==2 and not memories(s,for_model=True)['entries']
    with s.db() as db:assert db.execute('SELECT COUNT(*) FROM companion_memory_versions').fetchone()[0]==2
    call(s,'memory.correct',{'memory_id':saved['id'],'expected_revision':2,'body':'Explicitly permitted note.','allow_for_model':True})
    assert memories(s,for_model=True)['entries'][0]['body']=='Explicitly permitted note.'
    call(s,'memory.visibility',{'memory_id':saved['id'],'hidden':True})
    assert not call(s,'memory.list')['data']['entries']
    assert len(call(s,'memory.list',{'include_hidden':True})['data']['entries'])==1
    with pytest.raises(ValueError):call(s,'memory.correct',{'memory_id':saved['id'],'expected_revision':1,'body':'stale'})

def test_memory_marks_changed_evidence_and_does_not_feed_stale_summary_to_model(tmp_path):
    s=instance(tmp_path,'student','S');tid=activity(s);answer(s,tid)
    call(s,'memory.capture',{'task_ids':[tid]})
    assert learning_context(s)['bounded_learning_memory']['entries']
    answer(s,tid,'second')
    listed=call(s,'memory.list')['data']['entries']
    assert listed and not listed[0]['current']
    assert not learning_context(s)['bounded_learning_memory']['entries']

def test_teacher_memories_never_mix_students_or_reuse_revoked_receipts(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');u=instance(tmp_path/'u','student','U');pair(t,s);pair(t,u)
    tid=activity(t,peer=s.identity.id);drain(t,s);answer(s,tid);drain(s,t);drain(t,s)
    result=call(t,'memory.capture',{'task_ids':[tid]},s.identity.id,'capture')
    mid=result['data']['entry']['id']
    assert not call(t,'memory.list',peer=u.identity.id)['data']['entries']
    with pytest.raises(KeyError):call(t,'memory.correct',{'memory_id':mid,'expected_revision':1,'body':'wrong scope'},u.identity.id)
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError):call(t,'memory.capture',{'task_ids':[tid]},s.identity.id,'capture')

def test_review_self_report_and_schedule_adjustment_are_not_mastery(tmp_path):
    s=instance(tmp_path,'student','S');tid=activity(s);answer(s,tid)
    c=call(s,'review.create',{'task_id':tid,'intervals':[1,4,9]},key='schedule')['data']['card']
    assert call(s,'review.create',{'task_id':tid,'intervals':[1,4,9]},key='schedule')['data']['card']==c
    with pytest.raises(ValueError,match='已有'):call(s,'review.create',{'task_id':tid})
    event=call(s,'review.record',{'card_id':c['id'],'expected_revision':1,'response':'I recalled the limit before checking.','rating':'good','additional_help':'没有额外帮助'},key='recall')['data']['event']
    assert event['detail']['interval_days']==4 and event['policy_trace']['mastery_updated'] is False
    assert call(s,'review.record',{'card_id':c['id'],'expected_revision':1,'response':'I recalled the limit before checking.','rating':'good','additional_help':'没有额外帮助'},key='recall')['data']['event']==event
    assert call(s,'review.list')['data']['cards'][0]['recent_events'][0]['detail']['rating']=='good'
    adjusted=call(s,'review.adjust',{'card_id':c['id'],'expected_revision':2,'days_from_now':0,'paused':True})['data']['event']['card_after']
    assert adjusted['paused'] and not call(s,'review.list')['data']['cards']
    assert call(s,'review.list',{'include_paused':True})['data']['cards'][0]['due'] is False
    assert len(s.task(tid)['attempts'])==1
    with pytest.raises(ValueError):call(s,'review.record',{'card_id':c['id'],'expected_revision':3,'response':'x','rating':'again'})

def test_raw_image_http_and_mcp_content_block_share_version_and_authorization(tmp_path):
    s=instance(tmp_path,'student','S');im=save_page(s);app=create_app(s.folder,runtime=s,network=False)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.get('/api/local/pages/image',params={'page_id':im['id']}).status_code==401
        client.headers['Authorization']='Bearer '+s.service.base.owner_token
        response=client.get('/api/local/pages/image',params={'page_id':im['id']})
        assert response.status_code==200 and response.content==png()
        assert response.headers['content-type']=='image/png'
        assert client.get('/api/local/pages/image',params={'page_id':im['id'],'source_hash':'0'*64}).status_code==400
    result=asyncio.run(create_mcp(s).call_tool('read_original_page',{'page_id':im['id']}))
    image=next(x for x in result.content if x.type=='image')
    assert image.mimeType=='image/png' and base64.b64decode(image.data)==png()

def test_vision_model_gets_original_pixels_not_transcription(tmp_path):
    s=instance(tmp_path,'student','S');image=save_page(s)
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse,ToolCallPart,ModelRequest,UserPromptPart,BinaryContent
    observed=[]
    def model(messages,info):
        for message in messages:
            if isinstance(message,ModelRequest):
                for part in message.parts:
                    if isinstance(part,UserPromptPart) and isinstance(part.content,list):
                        observed.extend(x.data for x in part.content if isinstance(x,BinaryContent))
        if not any(getattr(p,'tool_name','')=='get_original_source' for m in messages for p in m.parts):
            return ModelResponse(parts=[ToolCallPart('get_original_source',{})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'message':'合成图像描述',
            'observations':[{'description':'可见色块','region':[0.1,0.1,0.8,0.8]}],'unknown':['教学意义未验证'],'next_steps':['核对原图']})])
    result=asyncio.run(run_agent(s,{'mode':'vision','source':{'page_id':image['id']}},FunctionModel(model)))
    assert png() in observed and result['original_bytes_sent'] and not result['automatic_teacher_judgement']
    assert result['output']['observations'][0]['source_ref']['source_hash']==image['source_hash']

def test_page_memory_and_schedule_survive_encrypted_backup_restore(tmp_path):
    s=instance(tmp_path/'s','student','S');im=save_page(s);tid=activity(s,im,image=True);answer(s,tid)
    call(s,'memory.capture',{'task_ids':[tid]});call(s,'review.create',{'task_id':tid})
    encrypted=export_backup(s,'Synthetic-backup-password-123')
    fresh=LocalRuntime(tmp_path/'restored',MemoryVault());restore_backup(fresh,encrypted,'Synthetic-backup-password-123')
    restored=LocalRuntime(fresh.folder,fresh.vault)
    assert base64.b64decode(call(restored,'page.read',{'page_id':im['id']})['data']['data_base64'])==png()
    assert call(restored,'memory.list')['data']['entries'] and call(restored,'review.list')['data']['cards']


def test_review_recovers_applied_event_without_receipt_and_limits_helped_interval(tmp_path):
    s=instance(tmp_path,'student','S');tid=activity(s);answer(s,tid)
    c=call(s,'review.create',{'task_id':tid,'intervals':[1,7,14]})['data']['card']
    payload={'card_id':c['id'],'expected_revision':1,'response':'Checked after asking for a hint.','rating':'good','additional_help':'received a hint'}
    first=call(s,'review.record',payload,key='recover')['data']['event']
    assert first['detail']['interval_days']==2
    with s.db() as db:db.execute("UPDATE companion_requests SET result=NULL WHERE id='recover'")
    replay=call(s,'review.record',payload,key='recover')['data']['event']
    assert replay==first
    with s.db() as db:assert db.execute('SELECT COUNT(*) FROM companion_review_events').fetchone()[0]==1
    assert call(s,'review.list')['data']['cards'][0]['revision']==2


def test_large_original_http_body_and_missing_original_do_not_create_continuity(tmp_path,monkeypatch):
    import random
    s=instance(tmp_path,'student','S');app=create_app(s.folder,runtime=s,network=False)
    stream=io.BytesIO();Image.frombytes('RGB',(600,400),random.Random(42).randbytes(720000)).save(stream,format='PNG')
    encoded=base64.b64encode(stream.getvalue()).decode();assert len(encoded)>524288
    with TestClient(app,base_url='http://127.0.0.1',headers={'Authorization':'Bearer '+s.service.base.owner_token}) as client:
        request={'contract_version':'companion.capability.v3','request_id':'large-image','operation':'page.save',
            'payload':{'title':'Large synthetic pixels','source':'Synthetic random fixture','data_base64':encoded}}
        response=client.post('/api/local/capabilities/invoke',json=request)
        assert response.status_code==200
    im=response.json()['data']['page'];tid=activity(s,im,image=True);answer(s,tid)
    # Corrupt only the adapter snapshot in this isolated fixture, not any real record.
    from base.app.companion.functional import continuity
    original_task=continuity.authorized_task
    def changed_task(runtime,task_id,peer_id=None):
        value=original_task(runtime,task_id,peer_id)
        if task_id==tid:value['pack']['source_page']['data_base64']=base64.b64encode(b'broken original').decode()
        return value
    monkeypatch.setattr(continuity,'authorized_task',changed_task)
    with pytest.raises(ValueError):call(s,'memory.capture',{'task_ids':[tid]})
    with pytest.raises(ValueError):call(s,'review.create',{'task_id':tid})

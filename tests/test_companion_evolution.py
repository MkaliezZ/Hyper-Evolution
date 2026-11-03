import asyncio,json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from test_local_runtime import instance,pair,drain,MemoryVault
from base.app.local_runtime import LocalRuntime
from base.app.local_backup import export_backup,restore_backup
from base.app.companion.assets.changes import apply_suggestions,validate_writing_history
from base.app.companion.assets.references import digest
from base.app.companion.functional import evolution_store as store
from growth_local.web import create_app
from growth_local.mcp import create_mcp

def request(op,payload=None,peer=None,key=None):
    return {'contract_version':'companion.capability.v5','request_id':key or uuid4().hex,'operation':op,'payload':payload or {},'peer_id':peer}

def call(r,op,payload=None,peer=None,key=None):return r.invoke_capability(request(op,payload,peer,key))['data']

def content(**kw):return {'title':'自主学习安排','goal':'用自己的证据解释观点','steps':[{'id':'s1','action':'阅读后写出一个观点','minutes':10}],
    'reason':'先完成短作品，再根据实际困难调整',**kw}

def writing(r,text='A garden help people.',**kw):
    return call(r,'writing.create',{'title':'原始作品','goal':'写清一个观点及其理由','text':text,**kw})['document']

def confirm(r,kind,p,peer=None,key=None):
    return call(r,kind+'.confirm',{'preview_id':p['id'],'preview_hash':p['content_hash'],'expected_revision':p['parent_revision']},peer,key)

def revised(r,d,text=None,suggestions=None,peer=None):
    p=call(r,'writing.preview',{'document_id':d['id'],'expected_revision':d['revision'],'contribution_note':'解释改动理由并明确帮助来源',
        **({'suggestion_ids':suggestions} if suggestions else {'text':text})},peer)['preview']
    return confirm(r,'writing',p,peer)['document']

def test_path_preview_history_cas_and_idempotent_confirmation(tmp_path):
    s=instance(tmp_path,'student','S');a=call(s,'path.create',content())['path']
    p=call(s,'path.preview',{'path_id':a['id'],'expected_revision':1,**content(steps=[{'id':'s2','action':'先解释给同伴听','minutes':8}])})['preview']
    assert p['changes'] and call(s,'path.read',{'path_id':a['id']})['path']['revision']==1
    b=confirm(s,'path',p,key='confirm')['path']
    assert confirm(s,'path',p,key='confirm')['path']==b
    assert b['parent_hash']==a['content_hash'] and b['revision']==2 and b['mastery']=='not_inferred'
    assert a['runtime_policy']['material_ref'] is None
    with pytest.raises(ValueError):confirm(s,'path',p)
    history=call(s,'path.read',{'path_id':a['id']})['versions']
    assert history[0]==a and len(history)==2
    with pytest.raises(PermissionError):call(s,'path.publish',{'path_id':a['id'],'expected_revision':2})

def test_teacher_publishes_exact_plan_only_and_student_keeps_own_arrangement(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');u=instance(tmp_path/'u','student','U');pair(t,s);pair(t,u)
    task=t.assign(s.identity.id,'writing','assignment');drain(t,s)
    path=call(t,'path.create',content(task_ids=[task['id']]),s.identity.id)['path']
    assert not call(s,'path.list')['paths']
    call(t,'path.publish',{'path_id':path['id'],'expected_revision':1},s.identity.id);drain(t,s)
    remote=call(s,'path.read',{'path_id':path['id']})['path']
    assert remote['signature_verified'] and remote['content_hash']==path['content_hash']
    with pytest.raises(PermissionError):call(s,'path.preview',{'path_id':path['id'],'expected_revision':1,**content(title='改老师的任务')})
    p=call(t,'path.preview',{'path_id':path['id'],'expected_revision':1,**content(title='未发布的私有新安排',task_ids=[task['id']])},s.identity.id)['preview']
    confirm(t,'path',p,s.identity.id);t.queue_task_update(s.identity.id,task['id']);drain(t,s)
    assert call(s,'path.read',{'path_id':path['id']})['path']['revision']==1
    call(t,'path.publish',{'path_id':path['id'],'expected_revision':2},s.identity.id);drain(t,s)
    assert call(s,'path.read',{'path_id':path['id']})['path']['revision']==2
    own=call(s,'path.create',content())['path'];assert own['owner_device']==s.identity.id
    with pytest.raises(PermissionError):call(t,'path.read',{'path_id':path['id']},u.identity.id)
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError):call(t,'path.read',{'path_id':path['id']},s.identity.id)

def test_writing_candidate_does_not_mutate_and_edits_keep_attribution(tmp_path):
    s=instance(tmp_path,'student','S');d=writing(s)
    suggestion=call(s,'writing.suggest',{'document_id':d['id'],'expected_revision':1,
        'edits':[{'start':9,'end':13,'original':'help','replacement':'helps','reason':'单数主语的动词形式'}]})['suggestion']
    assert call(s,'writing.read',{'document_id':d['id']})['document']==d
    new=revised(s,d,suggestions=[suggestion['id']])
    assert new['text']=='A garden helps people.' and new['contribution']=='external_assisted_revision'
    assert new['runtime_policy']['material_ref']['text_hash']==new['text_hash']
    assert new['suggestion_refs'][0]['id']==suggestion['id'] and new['changes']
    assert not call(s,'writing.suggestions',{'document_id':d['id']})['suggestions'][0]['current_text']
    with pytest.raises(ValueError):revised(s,new,suggestions=[suggestion['id']])
    own=revised(s,new,text='A garden helps people because it offers shade.')
    assert own['contribution']=='learner_revision_declared'
    assert call(s,'writing.read',{'document_id':d['id']})['versions'][0]['text']==d['text']

def test_unicode_stale_overlap_and_history_integrity_fail_honestly(tmp_path):
    assert apply_suggestions('好🙂abc',[{'start':2,'end':3,'original':'a','replacement':'A'}])=='好🙂Abc'
    for edits in [[{'start':2,'end':3,'original':'b','replacement':'B'}],
        [{'start':1,'end':3,'original':'🙂a','replacement':'a'},{'start':2,'end':3,'original':'a','replacement':'B'}]]:
        with pytest.raises(ValueError):apply_suggestions('好🙂abc',edits)
    s=instance(tmp_path,'student','S');d=writing(s);new=revised(s,d,text='A garden helps people.')
    from base.app.companion.functional.evolution import public_history
    history=public_history(s,new);history['versions'][-1]['changes']=[]
    with pytest.raises(ValueError):validate_writing_history(history,new['text'])

def test_signed_teacher_suggestions_and_explicit_submission_sidecar(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s)
    task=t.assign(s.identity.id,'writing','assignment');drain(t,s)
    d=writing(s,task_id=task['id']);call(s,'writing.submit',{'document_id':d['id'],'expected_revision':1,'additional_help':'使用词典'},key='submit-1')
    assert not t.task(task['id'])['attempts']
    drain(s,t);drain(t,s)
    attempt=t.task(task['id'])['attempts'][0];ref=attempt['answer']['writing_history_ref']
    assert len(json.dumps(attempt['answer']))<20000
    history=call(t,'writing.history',{'task_id':task['id'],'history_id':ref['id']},s.identity.id)
    assert history['history']['versions'][0]['text']==d['text'] and history['device_declaration_only']
    td=call(t,'writing.create',{'title':'基于提交的教师建议','goal':'主谓一致','task_id':task['id']},s.identity.id)['document']
    suggestion=call(t,'writing.suggest',{'document_id':td['id'],'expected_revision':1,'contributor':'teacher_suggestion',
        'edits':[{'start':9,'end':13,'original':'help','replacement':'helps','reason':'让动词与单数主语一致'}]},s.identity.id)['suggestion']
    call(t,'writing.share_suggestion',{'suggestion_id':suggestion['id']},s.identity.id);drain(t,s)
    assert call(s,'writing.suggestions',{'document_id':d['id']})['suggestions'][0]['contributor']=='teacher_suggestion'
    new=revised(s,d,suggestions=[suggestion['id']]);assert len(t.task(task['id'])['attempts'])==1
    call(s,'writing.submit',{'document_id':new['id'],'expected_revision':2},key='submit-2');drain(s,t);drain(t,s)
    actual=t.task(task['id'])['attempts'];assert len(actual)==2
    final=next(a for a in actual if a['answer']['text']==new['text']);ref2=final['answer']['writing_history_ref']
    assert len(call(t,'writing.history',{'task_id':task['id'],'history_id':ref2['id']},s.identity.id)['history']['versions'])==2
    assert (final.get('evaluation') or {}).get('judgement')!='meets_criteria'
    assert call(s,'writing.history',{'task_id':task['id'],'history_id':ref2['id']})['history']['versions'][-1]['contribution']=='external_assisted_revision'

def test_history_not_readable_for_other_task_or_revoked_pair(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s)
    task=t.assign(s.identity.id,'writing','a');other=t.assign(s.identity.id,'writing','b');drain(t,s)
    d=writing(s,task_id=task['id']);call(s,'writing.submit',{'document_id':d['id'],'expected_revision':1});drain(s,t)
    ref=t.task(task['id'])['attempts'][0]['answer']['writing_history_ref']
    with pytest.raises(PermissionError):call(t,'writing.history',{'task_id':other['id'],'history_id':ref['id']},s.identity.id)
    s.unpair(t.identity.id)
    with pytest.raises(PermissionError):call(s,'writing.read',{'document_id':d['id']})

def test_v5_same_web_mcp_and_backup(tmp_path):
    s=instance(tmp_path/'s','student','S');d=writing(s);revised(s,d,text='A garden helps people.')
    req=request('writing.read',{'document_id':d['id']},key='same-read');direct=s.invoke_capability(req)
    app=create_app(s.folder,runtime=s,network=False)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.post('/api/local/session',json={'bootstrap':app.state.bootstrap})
        assert c.post('/api/local/capabilities/invoke',json=req).json()==direct
    async def mcp_read():
        result=await create_mcp(s).call_tool('invoke_companion_capability',{'request':req})
        return result[1] if isinstance(result,tuple) else json.loads(result[0].text)
    result=asyncio.run(mcp_read())
    # FastMCP local call returns a (content, structuredContent) pair.
    if isinstance(result,tuple):result=result[1]
    assert result==direct
    archive=export_backup(s,'correct horse battery staple')
    fresh=LocalRuntime(tmp_path/'restored',MemoryVault());restore_backup(fresh,archive,'correct horse battery staple')
    loaded=LocalRuntime(fresh.folder,fresh.vault)
    assert len(call(loaded,'writing.read',{'document_id':d['id']})['versions'])==2

def test_writing_model_reads_pinned_text_and_saves_candidates_only(tmp_path):
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse,ToolCallPart
    from base.app.local_agent import run_agent
    s=instance(tmp_path,'student','S');d=writing(s)
    def model(messages,info):
        if not any(getattr(p,'tool_name','')=='get_writing_draft' for m in messages for p in m.parts):
            return ModelResponse(parts=[ToolCallPart('get_writing_draft',{})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'message':'合成模型候选建议。',
            'edits':[{'start':9,'end':13,'original':'help','replacement':'helps','reason':'主谓一致的局部练习'}],'next_steps':['自己解释后再决定是否采用。']})])
    result=asyncio.run(run_agent(s,{'mode':'writing','document_id':d['id']},FunctionModel(model)))
    assert result['tools_used']==['get_writing_draft'] and not result['automatic_teacher_judgement']
    assert call(s,'writing.read',{'document_id':d['id']})['document']==d
    assert len(call(s,'writing.suggestions',{'document_id':d['id']})['suggestions'])==1

def test_many_long_revisions_use_sidecar_without_expanding_core_answer(tmp_path):
    s=instance(tmp_path,'student','S');task=s.start_self('writing','writing')
    text='Original first draft. '+('abcde '*1700);d=writing(s,text=text,task_id=task['id'])
    for i in range(3):d=revised(s,d,text=text+' Revision '+str(i))
    call(s,'writing.submit',{'document_id':d['id'],'expected_revision':4},key='long-submit')
    a=s.task(task['id'])['attempts'][0]
    assert len(json.dumps(a['answer']))<20000 and 'writing_history' not in a['answer']
    history=call(s,'writing.history',{'task_id':task['id'],'history_id':a['answer']['writing_history_ref']['id']})['history']
    assert len(history['versions'])==4 and len(json.dumps(history))>20000

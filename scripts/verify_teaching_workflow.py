"""Real loopback HTTP, stdio/HTTP MCP and optional browser. Synthetic data only."""
import argparse,asyncio,json,logging,os,socket,sys
from pathlib import Path
from uuid import uuid4
import httpx,uvicorn
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from base.app.local_runtime import LocalRuntime
from base.app.local_identity import b64
from base.app.companion.functional.workspaces import host
from growth_local.web import create_app

ROOT=Path(__file__).resolve().parents[1]
logging.getLogger('httpx').setLevel(logging.WARNING)

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--browser',action='store_true');args=parser.parse_args()
    folder=ROOT/'data/verify'/('teaching-workflow-'+uuid4().hex)
    roots=[LocalRuntime(folder/name) for name in ['teacher','student']]
    tr,sr=roots;tr.setup('teacher','合成测试教师');sr.setup('student','合成测试学生')
    secret=b64(os.urandom(32));tr.accept_peer(sr.hello(),secret);sr.accept_peer(tr.hello(),secret)
    runtimes=[host(root) for root in roots];t,s=runtimes;peer=sr.identity.id
    servers=[];running=[];clients=[];launches=[]
    def raw(op,payload=None,version='v10',who=peer,key=None):return {'contract_version':'companion.capability.'+version,
        'request_id':key or uuid4().hex,'operation':op,'payload':payload or {},'peer_id':who}
    def drain(a,b):
        for envelope in a.pending(b.identity.id):b.receive(envelope);a.ack(b.identity.id,envelope['body']['id'])
    async def start(root):
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1]
        app=create_app(root.folder,runtime=root,network=False)
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False));servers.append(server)
        running.append(asyncio.create_task(server.serve(sockets=[sock])))
        client=httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',headers={'Authorization':'Bearer '+root.service.base.owner_token},trust_env=False,timeout=45);clients.append(client)
        launches.append(f'http://127.0.0.1:{port}/#start={app.state.bootstrap}')
        for _ in range(100):
            try:
                if (await client.get('/api/local/ready')).status_code==200:return client
            except httpx.RequestError:pass
            await asyncio.sleep(.1)
        raise TimeoutError('Local server did not start')
    async def cap(client,op,payload=None,version='v10',who=peer,key=None):
        response=await client.post('/api/local/capabilities/invoke',json=raw(op,payload,version,who,key))
        if not response.is_success:raise AssertionError(f'{op}: {response.status_code} {response.text}')
        return response.json()['data']
    async def mcp(request,web=None):
        async def invoke(session):
            await session.initialize();result=await session.call_tool('invoke_companion_capability',{'request':request})
            assert not result.isError
            return result.structuredContent or json.loads(result.content[0].text)
        if web:
            async with streamablehttp_client(str(web.base_url).rstrip('/')+'/mcp/',headers=web.headers) as (reader,writer,_):
                async with ClientSession(reader,writer) as session:return await invoke(session)
        env={**os.environ,'HYPER_GROWTH_DATA':str(tr.folder),'PYTHONPATH':str(ROOT/'src'),'PYTHONUTF8':'1'}
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','growth_local.mcp','--data',str(tr.folder)],env=env)) as (reader,writer):
            async with ClientSession(reader,writer) as session:return await invoke(session)
    try:
        for runtime in runtimes:
            runtime.invoke_capability(raw('workspace.initialize',version='v8',who=None))
            runtime.invoke_capability(raw('workspace.select',{'subject':'english','track':'k12'},version='v8',who=None))
        tw,sw=await start(tr),await start(sr)
        request=raw('roster.save',{'name':'合成预登记学生','aliases':['QA-Nov2'],'peer_id':peer},who=None,key='same-transports')
        result=(await tw.post('/api/local/capabilities/invoke',json=request)).json()
        assert await mcp(request)==result and await mcp(request,tw)==result
        rr=(await cap(tw,'route.save',{'title':'合成教学链验证','level':'junior','grade':7,'goal':'细节理解'},'v7'))['record']
        prepared=await cap(tw,'workflow.prepare',{'route_id':rr['id'],'focus':'细节理解','count':2})
        d=prepared['draft'];qs=d['body']['questions']
        reviews=[{'question_id':q['id'],'basis':q['evidence'],'ambiguity_check':'依据本题明确的开放与关闭日期逐项核对。',
            'choices':[{'option':chr(65+i),'defensible':chr(65+i) in q['key'],'reasoning':'回到原文核对opens对应的日期。',
                'why_not':'该项对应关闭日期，与问题条件不同。','next_step':'区分opens和closes，再换日期复核。'} for i in range(len(q['options']))]} for q in qs]
        await cap(tw,'draft.review_items',{'id':d['id'],'expected_revision':1,'questions':reviews,'human_review_confirmed':True})
        await cap(tw,'draft.finalize_review',{'id':d['id'],'expected_revision':1,'human_review_confirmed':True})
        await cap(tw,'blueprint.save',{'id':d['id'],'expected_revision':1,'sections':[{'title':'阅读细节','types':['reading_mcq'],
            'question_ids':[q['id'] for q in qs],'count':2,'points':2.0,'minutes':6}]})
        goal=(await cap(tw,'goal.save',{'title':'读准开放日期','outcomes':['区分开放与关闭日期']}))['record']
        await cap(tw,'goal.bind',{'id':d['id'],'expected_revision':1,'goal_id':goal['id'],'goal_revision':1,
            'outcomes':{'区分开放与关闭日期':[q['id'] for q in qs]},'coverage_note':'两条不同材料检查相同操作。','human_review_confirmed':True})
        publication=(await cap(tw,'k12.draft.publish',{'id':d['id'],'expected_revision':1,'mode':'target','human_review_confirmed':True},'v7'))['record']
        drain(t,s)
        response=await sw.post('/api/local/tasks/'+publication['task_id']+'/submit',json={
            'answers':{q['id']:q['key'][0] for q in qs},'text':'','files':[],
            'request_key':'synthetic-full-loop','learning_conditions':{'additional_help':'none'}})
        response.raise_for_status();drain(s,t);drain(t,s)
        attempt=t.task(publication['task_id'])['attempts'][-1]
        await cap(tw,'k12.explain.save',{'task_id':publication['task_id'],'submission_id':attempt['id'],'question_id':'q1',
            'student':'先定位opens，再与日期一一对应。','tutor':'合成教师私有备注，不对学生发送。','next_step':'换新情境再试一次。',
            'quote':qs[0]['evidence'],'human_confirmed':True},'v7')
        drain(t,s)
        task=(await sw.get('/api/local/tasks/'+publication['task_id'])).json()
        assert task['pack']['teaching_blueprint']['minutes']==6
        assert '合成教师私有备注' not in json.dumps(task,ensure_ascii=False)
        assert (await cap(tw,'goal.history',{'id':goal['id']}))['history'][0]['results'][0]['outcomes'][0]['state']=='meets_this_target'
        # A separate unseen, unsubmitted practice task demonstrates the student timer.
        fresh=(await cap(tw,'workflow.prepare',{'route_id':rr['id'],'focus':'细节理解','count':1}))['draft']
        fresh_q=fresh['body']['questions'][0]
        fresh_review={**reviews[0],'question_id':fresh_q['id'],'basis':fresh_q['evidence'],
            'choices':[{**c,'defensible':c['option'] in fresh_q['key']} for c in reviews[0]['choices']]}
        await cap(tw,'draft.review_items',{'id':fresh['id'],'expected_revision':1,'questions':[fresh_review],'human_review_confirmed':True})
        await cap(tw,'draft.finalize_review',{'id':fresh['id'],'expected_revision':1,'human_review_confirmed':True})
        await cap(tw,'blueprint.save',{'id':fresh['id'],'expected_revision':1,'sections':[{'title':'新情境练习','types':['reading_mcq'],
            'question_ids':['q1'],'count':1,'points':1.0,'minutes':6}]})
        fresh_pub=(await cap(tw,'k12.draft.publish',{'id':fresh['id'],'expected_revision':1,'mode':'practice','human_review_confirmed':True},'v7'))['record']
        drain(t,s)
        # Keep one unchanged review to exercise resume UI after partial modification.
        q={**qs[0],'prompt':'Read carefully: '+qs[0]['prompt']}
        patch=await cap(tw,'draft.patch',{'id':d['id'],'expected_revision':1,'questions':[q]})
        assert patch['review_state']['pending']==['q1']
        browser=None
        if args.browser:
            config=folder/'browser-input.json';config.write_text(json.dumps({'teacher_url':launches[0],'student_url':launches[1],
                'task_id':publication['task_id'],'timer_task_id':fresh_pub['task_id'],'draft_id':d['id'],'route_id':rr['id'],'artifacts':str(ROOT/'artifacts')}),encoding='utf8')
            runtime_path=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
            env={**os.environ,'NODE_PATH':str(runtime_path/'node_modules')}
            process=await asyncio.create_subprocess_exec(str(runtime_path/'bin/node.exe'),str(ROOT/'scripts/verify_teaching_workflow_browser.cjs'),str(config),
                env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            stdout,stderr=await process.communicate()
            if process.returncode:raise AssertionError('Browser acceptance failed: '+stderr.decode('utf8','replace')[-4000:])
            browser=json.loads(stdout.decode('utf8'))
        report={'ok':True,'synthetic_only':True,'real_data_modified':False,'model_api_called':False,
            'checks':['real HTTP teacher/student lifecycle','stdio and HTTP MCP replay equality','item review and retained-review patch',
                'signed blueprint delivery','stable goal result','private teacher note excluded'],'browser':browser}
        output=ROOT/'artifacts/teaching-workflow-verification.json';output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n');print(json.dumps({'ok':True,'report':str(output)}))
    finally:
        for client in clients:await client.aclose()
        for server in servers:server.should_exit=True
        await asyncio.gather(*running,return_exceptions=True)

if __name__=='__main__':asyncio.run(main())

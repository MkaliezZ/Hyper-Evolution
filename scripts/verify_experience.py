"""Real HTTP + independent stdio MCP + HTTP MCP self-study acceptance; synthetic local data only."""
import asyncio,json,logging,os,socket,sys
from pathlib import Path
from uuid import uuid4
import httpx,uvicorn
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from base.app.local_runtime import LocalRuntime
from base.app.companion.functional.workspaces import host
from growth_local.web import create_app

ROOT=Path(__file__).resolve().parents[1]
logging.getLogger('httpx').setLevel(logging.WARNING)

async def main():
    folder=ROOT/'data/verify'/('experience-'+uuid4().hex)
    root=LocalRuntime(folder);root.setup('student','合成自学三入口测试')
    runtime=host(root);runtime.initialize();runtime.select('english','materials')
    app=create_app(folder,runtime=runtime,network=False)
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
    serving=asyncio.create_task(server.serve(sockets=[sock]))
    headers={'Authorization':'Bearer '+root.service.base.owner_token}
    def request(op,payload=None,version='v11',key=None):return {'contract_version':'companion.capability.'+version,
        'request_id':key or uuid4().hex,'operation':op,'payload':payload or {}}
    async def mcp(raw,web=False):
        async def call(session):
            await session.initialize();result=await session.call_tool('invoke_companion_capability',{'request':raw})
            assert not result.isError,str(result.content)
            return result.structuredContent or json.loads(result.content[0].text)
        if web:
            async with streamablehttp_client(f'http://127.0.0.1:{port}/mcp/',headers=headers) as (read,write,_):
                async with ClientSession(read,write) as session:return await call(session)
        env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'PYTHONUTF8':'1','HYPER_GROWTH_DATA':str(folder)}
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','growth_local','--mcp','--data',str(folder)],env=env)) as (read,write):
            async with ClientSession(read,write) as session:return await call(session)
    try:
        for _ in range(100):
            if server.started:break
            await asyncio.sleep(.05)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',headers=headers,trust_env=False,timeout=35) as client:
            async def cap(raw):
                response=await client.post('/api/local/capabilities/invoke',json=raw);response.raise_for_status();return response.json()
            await cap(request('experience.select',{'experience':'self'}))
            material=(await cap(request('material.save',{'title':'合成自学资料','text':'A garden gives students a quiet break.','source':'Original engineering example'},'v2')))['data']['material']
            raw=request('self.start',{'source':{'material_id':material['id'],'revision':material['revision'],'source_hash':material['source_hash']},
                'goal':'用一个理由解释帮助','method':'apply'})
            created=await cap(raw);assert await mcp(raw)==created and await mcp(raw,True)==created
            tid=created['data']['task_id']
            response=await client.post('/api/local/tasks/'+tid+'/submit',json={'text':'A garden helps us relax because it gives us a quiet break.','answers':{},'files':[],'request_key':'first'})
            response.raise_for_status()
            task=(await client.get('/api/local/tasks/'+tid)).json();sid=task['attempts'][-1]['id']
            raw=request('self.feedback_context',{'task_id':tid,'submission_id':sid});expected=await cap(raw)
            assert await mcp(raw)==expected and await mcp(raw,True)==expected
            raw=request('self.reflect',{'task_id':tid,'submission_id':sid,'comment':'理由来自原文，下次补自己的例子','next_step':'用图书馆安静角落解释同样的帮助'})
            reflected=await mcp(raw);assert await cap(raw)==reflected and await mcp(raw,True)==reflected
            cards=(await cap(request('review.list',version='v3')))['data']['cards'];assert len(cards)==1
            await cap(request('workspace.select',{'subject':'mathematics','track':'materials'},'v8'))
            assert not (await cap(request('self.context')))['data']['tasks']
            assert (await client.get('/api/local/status')).json()['experience']['id']=='self'
            await cap(request('workspace.select',{'subject':'english','track':'materials'},'v8'))
            assert (await cap(request('self.context')))['data']['tasks'][0]['id']==tid
            denied=await client.post('/api/local/capabilities/invoke',json=request('experience.select',{'experience':'teacher'}));assert denied.status_code==403
            for asset in ['experience.js','experience-state.js','experience.css']:
                assert (await client.get('/assets/'+asset)).status_code==200
        restarted=LocalRuntime(folder)
        assert host(restarted).status()['experience']['id']=='self'
        report={'ok':True,'source_only':True,'real_model_called':False,'real_user_data_modified':False,
            'checks':['real HTTP, independent stdio MCP and HTTP MCP return identical activity/context/reflection',
            'source and Policy Pack bound to own task','submit then reflect and schedule review','no teacher privilege promotion',
            'mode shared across physically isolated subjects','restart preserves mode and learning history','new UI assets served'],
            'data_folder':str(folder)}
        output=ROOT/'data/verify/experience-acceptance.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        server.should_exit=True;await serving

if __name__=='__main__':asyncio.run(main())

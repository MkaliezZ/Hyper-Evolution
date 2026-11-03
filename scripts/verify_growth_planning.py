"""Synthetic real HTTP/stdio MCP/HTTP MCP and signed growth-planning exchange."""
import asyncio,json,os,socket,sys
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

async def main():
    folder=ROOT/'data/verify'/('growth-planning-'+uuid4().hex)
    tr,sr=LocalRuntime(folder/'teacher'),LocalRuntime(folder/'student')
    tr.setup('teacher','合成成长教师');sr.setup('student','合成成长学生')
    secret=b64(os.urandom(32));tr.accept_peer(sr.hello(),secret);sr.accept_peer(tr.hello(),secret)
    t,s=host(tr),host(sr);servers=[];running=[];clients=[]
    async def start(root):
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
        server=uvicorn.Server(uvicorn.Config(create_app(root.folder,runtime=root,network=False),log_level='error',access_log=False));servers.append(server)
        running.append(asyncio.create_task(server.serve(sockets=[sock])))
        web=httpx.AsyncClient(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}',headers={'Authorization':'Bearer '+root.service.base.owner_token},timeout=40,trust_env=False);clients.append(web)
        for _ in range(100):
            try:
                if (await web.get('/api/local/ready')).status_code==200:return web
            except httpx.RequestError:pass
            await asyncio.sleep(.1)
        raise TimeoutError('Local server not ready')
    def request(op,payload=None,version='v9',peer=None,key=None):return {'contract_version':'companion.capability.'+version,'operation':op,'payload':payload or {},'peer_id':peer,'request_id':key or uuid4().hex}
    async def cap(web,raw):
        response=await web.post('/api/local/capabilities/invoke',json=raw);response.raise_for_status();return response.json()
    async def mcp(raw,web=None):
        async def run(session):
            await session.initialize();result=await session.call_tool('invoke_companion_capability',{'request':raw});assert not result.isError,str(result.content)
            return result.structuredContent or json.loads(result.content[0].text)
        if web:
            async with streamablehttp_client(str(web.base_url).rstrip('/')+'/mcp/',headers=web.headers) as (read,write,_):
                async with ClientSession(read,write) as session:return await run(session)
        env={**os.environ,'HYPER_GROWTH_DATA':str(sr.folder),'PYTHONPATH':str(ROOT/'src'),'PYTHONUTF8':'1'}
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','growth_local.mcp','--data',str(sr.folder)],env=env)) as (read,write):
            async with ClientSession(read,write) as session:return await run(session)
    def drain(a,b):
        for envelope in a.pending(b.identity.id):b.receive(envelope);a.ack(b.identity.id,envelope['body']['id'])
    try:
        tw,sw=await start(tr),await start(sr)
        for web in [tw,sw]:
            await cap(web,request('workspace.initialize',version='v8'))
            await cap(web,request('workspace.select',{'subject':'mathematics'},'v8'))
        content={'current_situation':'合成工程测试：准备解释数学关系','stage':'preparing','goal':'用不同数量说明比例关系',
            'requirements':[{'requirement':'举例说明适用条件','current_evidence':'已有合成练习','gap':'还需新情境检查','next_action':'换一个数量解释','completion_standard':'说明单价保持不变'}]}
        p=(await cap(sw,request('planning.save',{'content':content})))['data']['plan']
        raw=request('planning.read',{'id':p['id']});expected=await cap(sw,raw)
        assert await mcp(raw)==expected and await mcp(raw,sw)==expected
        assert not s.pending(t.identity.id)
        shared={'id':p['id'],'expected_revision':1,'content_hash':p['content_hash'],'receiver_id':t.identity.id}
        await cap(sw,request('planning.share',shared));drain(s,t)
        remote=(await cap(tw,request('planning.read',{'id':p['id']},peer=s.identity.id)))['data']['plan']
        assert remote['signature_verified'] and remote['content_hash']==p['content_hash']
        proposal=(await cap(tw,request('planning.save',{'content':{**content,'goal':'老师建议先比较两种数量'}},peer=s.identity.id)))['data']['plan']
        await cap(tw,request('planning.share',{'id':proposal['id'],'expected_revision':1,'content_hash':proposal['content_hash']},peer=s.identity.id));drain(t,s)
        assert len((await cap(sw,request('planning.context')))['data']['plans'])==2
        await cap(sw,request('workspace.select',{'subject':'english'},'v8'))
        assert not (await cap(sw,request('planning.context')))['data']['plans']
        denied=await sw.post('/api/local/capabilities/invoke',json=request('planning.read',{'id':p['id']}));assert denied.status_code in [403,404]
        result={'ok':True,'synthetic_only':True,'actual_http_stdio_http_mcp':'PASS','signed_student_plan_and_teacher_proposal':'PASS',
            'save_does_not_share':'PASS','subject_isolation':'PASS','real_model_api_called':False,'public_relay_retested':False,'installer_updated':False}
        (ROOT/'artifacts/growth-planning-transport-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
    finally:
        for client in clients:await client.aclose()
        for server in servers:server.should_exit=True
        await asyncio.gather(*running,return_exceptions=True)

if __name__=='__main__':asyncio.run(main())

"""Source-only acceptance using real HTTP, stdio MCP and HTTP MCP; synthetic local records."""
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
    folder=ROOT/'data/verify'/('subject-workspaces-'+uuid4().hex)
    tr,sr=LocalRuntime(folder/'teacher'),LocalRuntime(folder/'student')
    tr.setup('teacher','合成学科工程教师');sr.setup('student','合成学科工程学生')
    secret=b64(os.urandom(32));tr.accept_peer(sr.hello(),secret);sr.accept_peer(tr.hello(),secret)
    t,s=host(tr),host(sr);servers=[];running=[];clients=[]
    async def start(root):
        sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(create_app(root.folder,runtime=root,network=False),log_level='error',access_log=False));servers.append(server)
        running.append(asyncio.create_task(server.serve(sockets=[sock])))
        web=httpx.AsyncClient(base_url='http://127.0.0.1:'+str(port),headers={'Authorization':'Bearer '+root.service.base.owner_token},timeout=40,trust_env=False);clients.append(web)
        for _ in range(150):
            try:
                if (await web.get('/api/local/ready')).status_code==200:return web
            except httpx.RequestError:pass
            await asyncio.sleep(.1)
        raise TimeoutError('Loopback server did not become ready')
    def request(op,payload=None,version='v8',peer=None,key=None):
        return {'contract_version':'companion.capability.'+version,'operation':op,'payload':payload or {},'peer_id':peer,'request_id':key or uuid4().hex}
    async def cap(web,op,payload=None,version='v8',peer=None,key=None):
        response=await web.post('/api/local/capabilities/invoke',json=request(op,payload,version,peer,key));response.raise_for_status();return response.json()['data']
    async def mcp(raw,web=None):
        async def call(session):
            await session.initialize();result=await session.call_tool('invoke_companion_capability',{'request':raw})
            assert not result.isError,str(result.content)
            return result.structuredContent or json.loads(result.content[0].text)
        if web:
            async with streamablehttp_client(str(web.base_url).rstrip('/')+'/mcp/',headers=web.headers) as (read,write,_):
                async with ClientSession(read,write) as session:return await call(session)
        env={**os.environ,'HYPER_GROWTH_DATA':str(tr.folder),'PYTHONPATH':str(ROOT/'src'),'PYTHONUTF8':'1'}
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','growth_local.mcp','--data',str(tr.folder)],env=env)) as (read,write):
            async with ClientSession(read,write) as session:return await call(session)
    def drain(a,b):
        for envelope in a.pending(b.identity.id):b.receive(envelope);a.ack(b.identity.id,envelope['body']['id'])
    async def source(web,title,key):return (await cap(web,'material.save',{'title':title,'source':'团队原创合成工程素材','text':'At a fixed unit price, total cost equals unit price times quantity.'},'v2',key=key))['material']
    async def activity(web,material):return (await cap(web,'activity.create',{'material_id':material['id'],'revision':1,'source_hash':material['source_hash'],'goal':'说明一个有依据的关系','method':'understand'},'v2',sr.identity.id))['task_id']
    try:
        tw,sw=await start(tr),await start(sr)
        await cap(tw,'workspace.initialize');await cap(sw,'workspace.initialize')
        await cap(tw,'workspace.select',{'subject':'english'});await cap(sw,'workspace.select',{'subject':'science'})
        em=await source(tw,'合成英语工作区素材','same-request-in-different-databases');et=await activity(tw,em);drain(t,s)
        assert (await sw.get('/api/local/dashboard')).json()['tasks']==[]
        await mcp(request('workspace.select',{'subject':'mathematics'}))
        assert (await tw.get('/api/local/status')).json()['workspace']['active']=='mathematics'
        denied=await tw.post('/api/local/capabilities/invoke',json=request('material.read',{'material_id':em['id']},'v2'));assert denied.status_code in [403,404]
        mm=await source(tw,'合成数学工作区素材','same-request-in-different-databases');mt=await activity(tw,mm)
        raw=request('academic.material.list',{'subject':'all'},'v7',key='three-transport-library')
        expected=(await tw.post('/api/local/capabilities/invoke',json=raw)).json()
        assert [m['id'] for m in expected['data']['materials']]==[mm['id']]
        assert await mcp(raw)==expected and await mcp(raw,tw)==expected
        drain(t,s);assert s.current()=='science' and (await sw.get('/api/local/dashboard')).json()['tasks']==[]
        await mcp(request('workspace.select',{'subject':'mathematics'}),sw)
        task=(await sw.get('/api/local/tasks/'+mt)).json();assert task['signature_verified']
        response=await sw.post('/api/local/tasks/'+mt+'/submit',json={'answers':{},'text':'The relationship depends on a fixed unit price.','files':[],'request_key':'actual-student-submission'});response.raise_for_status()
        drain(s,t);drain(t,s);submission=t.task(mt)['attempts'][0]['id']
        await cap(tw,'assessment.record',{'task_id':mt,'submission_id':submission,'source_type':'teacher_review','outcome':'needs_revision','comment':'补充数量与总价的具体例子。','next_step':'换一个数量说明。','human_review_confirmed':True},'v2',sr.identity.id)
        drain(t,s);assert s.task(mt)['attempts'][-1]['evaluation']['judgement']=='needs_revision'
        await cap(tw,'workspace.select',{'subject':'english'})
        assert [x['id'] for x in (await tw.get('/api/local/dashboard',params={'peer_id':sr.identity.id})).json()['tasks']]==[et]
        assert (await tw.get('/api/local/tasks/'+mt)).status_code in [403,404]
        custom=(await mcp(request('workspace.create',{'name':'合成物理测试'})))['data'];sid=custom['subject']['id']
        await cap(tw,'workspace.select',{'subject':sid})
        assert Path(custom['folder'],'base.sqlite3').is_file() and Path(custom['folder'],'workspace.json').is_file()
        assert not (await cap(tw,'material.list',version='v2'))['materials']
        assert (await tw.get('/api/local/resources')).status_code==403
        stale=await tw.get('/api/local/dashboard',params={'peer_id':sr.identity.id},headers={'X-Growth-Workspace':'english'});assert stale.status_code==409
        result={'ok':True,'synthetic_only':True,'packaged_executable':False,'model_api_called':False,
            'checks':['independent subject SQLite databases and original folders','same request key creates independent material in different databases',
                'HTTP, independent stdio MCP and HTTP MCP share the active workspace and return identical local sources',
                'cross-subject direct material and task IDs are denied','signed assignments arrive in their subject without changing student selection',
                'student submission, teacher feedback and signed return remain in math','English task remains visible only in English',
                'custom subject creates a new folder and manifest','English resource API hidden outside English','stale browser workspace request rejected'],
            'legacy_history':'preserved in separate read-only legacy workspace; no guessed task migration',
            'professional_subject_validation':'NOT_PERFORMED','human_pilot':'DEFERRED_BY_USER'}
        (ROOT/'artifacts/workspaces-transport-verification.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
        print(json.dumps(result,ensure_ascii=False))
    finally:
        for client in clients:await client.aclose()
        for server in servers:server.should_exit=True
        if running:await asyncio.gather(*running,return_exceptions=True)

if __name__=='__main__':asyncio.run(main())

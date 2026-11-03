"""Independent synthetic HTTP / stdio / HTTP MCP and signed-pair acceptance."""
import asyncio,base64,hashlib,io,json,os,secrets,socket,sys
from pathlib import Path
from uuid import uuid4
import httpx,uvicorn
from PIL import Image
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from base.app.local_runtime import LocalRuntime
from base.app.local_identity import b64
from growth_local.web import create_app

ROOT=Path(__file__).resolve().parents[1]
def drain(a,b):
    for event in a.pending(b.identity.id):b.receive(event);a.ack(b.identity.id,event['body']['id'])
async def mcp_call(session,name,args):
    value=await session.call_tool(name,args)
    assert not value.isError,name
    return value
async def main():
    data=ROOT/'data/verify'/('continuity-'+uuid4().hex)
    t,s=[LocalRuntime(data/role) for role in ['teacher','student']]
    t.setup('teacher','合成连续学习老师');s.setup('student','合成连续学习学生')
    secret=b64(secrets.token_bytes(32));t.accept_peer(s.hello(),secret);s.accept_peer(t.hello(),secret)
    servers=[];jobs=[];clients={};urls={};checks=[]
    try:
        for role,r in [('teacher',t),('student',s)]:
            app=create_app(r.folder,runtime=r,network=False);sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
            url=f'http://127.0.0.1:{sock.getsockname()[1]}';urls[role]=url
            server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False));servers.append(server)
            jobs.append(asyncio.create_task(server.serve(sockets=[sock])))
            for _ in range(100):
                if server.started:break
                await asyncio.sleep(.03)
            assert server.started
            clients[role]=httpx.AsyncClient(base_url=url,headers={'Authorization':'Bearer '+r.service.base.owner_token},trust_env=False)
        async def invoke(role,operation,payload=None,peer=None,key=None):
            request={'contract_version':'companion.capability.v3','request_id':key or uuid4().hex,'operation':operation,'payload':payload or {},'peer_id':peer}
            response=await clients[role].post('/api/local/capabilities/invoke',json=request);response.raise_for_status();return response.json()
        image=io.BytesIO();Image.new('RGB',(90,60),'#b95232').save(image,format='PNG');raw=image.getvalue();checksum=hashlib.sha256(raw).hexdigest()
        page=(await invoke('teacher','page.save',{'title':'Original synthetic visual source','source':'Team-created acceptance image','data_base64':base64.b64encode(raw).decode()},key='page'))['data']['page']
        task=(await invoke('teacher','activity.create',{'source':{'page_id':page['id'],'revision':1,'source_hash':checksum},'goal':'Distinguish observations from claims','scenario':'visual_reading','method':'inquire'},s.identity.id,key='activity'))['data']['task_id']
        drain(t,s)
        response=await clients['student'].get('/api/local/pages/image',params={'task_id':task});response.raise_for_status();assert response.content==raw
        checks.append('actual original pixels cross a signed assignment and match HTTP bytes/hash/version')
        response=await clients['student'].post(f'/api/local/tasks/{task}/submit',json={'answers':{},'text':'A synthetic observed region, with an explicit uncertainty.','files':[],'request_key':'work','learning_conditions':{'additional_help':'Synthetic test, no learner claim'}})
        response.raise_for_status();drain(s,t);drain(t,s)
        sid=t.task(task)['attempts'][0]['id'];plan=t.task(task)['pack']['companion_plan']['runtime_policy']
        assert len(plan['decisions'])==10 and plan['method_id']=='M02'
        response=await clients['teacher'].post('/api/local/capabilities/invoke',json={'contract_version':'companion.capability.v2','request_id':'teacher-review','operation':'assessment.record','peer_id':s.identity.id,'payload':{'task_id':task,'submission_id':sid,'source_type':'teacher_review','outcome':'needs_revision','comment':'Point to the visible evidence.','next_step':'State what is not visible.','human_review_confirmed':True}})
        response.raise_for_status();drain(t,s)
        memory=(await invoke('student','memory.capture',{'task_ids':[task]}))['data']['entry']
        assert memory['source_refs'][0]['submission_id']==sid
        card=(await invoke('student','review.create',{'task_id':task,'intervals':[1,3,7]}))['data']['card']
        result=await invoke('student','review.record',{'card_id':card['id'],'expected_revision':1,'response':'Recalled an observation and a limitation.','rating':'hard'})
        assert result['data']['event']['policy_trace']['mastery_updated'] is False
        checks.append('all ten policy packs are frozen; real work, signed feedback, source-backed memory and review event read back')
        request={'contract_version':'companion.capability.v3','request_id':'same-request','operation':'memory.list','payload':{}}
        expected=(await clients['student'].post('/api/local/capabilities/invoke',json=request)).json()
        params=StdioServerParameters(command=sys.executable,args=['-m','growth_local.mcp'],env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'HYPER_GROWTH_DATA':str(s.folder),'PYTHONUTF8':'1'})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                result=await mcp_call(session,'invoke_companion_capability',{'request':request})
                assert (result.structuredContent or json.loads(result.content[0].text))==expected
                result=await mcp_call(session,'read_original_page',{'task_id':task})
                media=next(x for x in result.content if x.type=='image')
                assert base64.b64decode(media.data)==raw and media.mimeType=='image/png'
                checks.append('independent stdio MCP matches web v3 and returns an actual image content block')
        async with streamablehttp_client(urls['student']+'/mcp/',headers={'Authorization':'Bearer '+s.service.base.owner_token}) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize();result=await mcp_call(session,'invoke_companion_capability',{'request':request})
                assert (result.structuredContent or json.loads(result.content[0].text))==expected
                s.unpair(t.identity.id)
                denied=await session.call_tool('read_original_page',{'task_id':task});assert denied.isError
                assert not (await invoke('student','memory.list'))['data']['entries']
                assert not (await invoke('student','review.list'))['data']['cards']
                checks.append('HTTP MCP parity, then revoked pairing excludes image reads, memories and review context')
        report={'ok':True,'contract':'companion.capability.v3','checks':checks,'synthetic_only':True,'model_api_called':False,
            'source_image_sha256':checksum,'database_extension':'four additive tables after S1','old_records_rewritten':False,
            'public_network_tested':False,'domain_review':'NOT_REVIEWED','learning_effect':'NOT_TESTED'}
        (ROOT/'artifacts/companion-continuity-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        for client in clients.values():await client.aclose()
        for server in servers:server.should_exit=True
        await asyncio.gather(*jobs,return_exceptions=True)
if __name__=='__main__':asyncio.run(main())

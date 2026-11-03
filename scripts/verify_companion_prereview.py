"""Actual teacher/student HTTP, independent MCP transports and optional own API/frozen build."""
import argparse,asyncio,hashlib,json,logging,os,socket,subprocess,sys
from pathlib import Path
from uuid import uuid4
import httpx,uvicorn
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from base.app.local_runtime import LocalRuntime
from base.app.local_identity import b64
from growth_local.web import create_app

ROOT=Path(__file__).resolve().parents[1]
logging.getLogger('httpx').setLevel(logging.WARNING)

async def main():
    p=argparse.ArgumentParser();p.add_argument('--executable');p.add_argument('--env-file');a=p.parse_args()
    folder=ROOT/'data/verify'/('prereview-'+uuid4().hex)
    t=LocalRuntime(folder/'teacher');s=LocalRuntime(folder/'student');t.setup('teacher','合成预审教师');s.setup('student','合成预审学生')
    secret=b64(os.urandom(32));t.accept_peer(s.hello(),secret);s.accept_peer(t.hello(),secret)
    def drain(x,y):
        for env in x.pending(y.identity.id):y.receive(env);x.ack(y.identity.id,env['body']['id'])
    task=t.assign(s.identity.id,'writing','synthetic-writing');drain(t,s)
    s.submit(task['id'],{},'A garden help people. It offers shade. For example, students can rest near the trees.',[],'synthetic-answer');drain(s,t);drain(t,s)
    target={'task_id':task['id'],'submission_id':t.task(task['id'])['attempts'][-1]['id']}
    processes=[];servers=[];running=[];clients=[]
    async def start(r):
        if a.executable:
            env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','PYTHONHOME']}
            proc=subprocess.Popen([a.executable,'--web','--no-browser','--data',str(r.folder)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0);processes.append(proc)
            for _ in range(200):
                if (r.folder/'running.json').exists():break
                if proc.poll() is not None:raise RuntimeError('Frozen web process exited')
                await asyncio.sleep(.1)
            port=json.loads((r.folder/'running.json').read_text())['port']
        else:
            sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1]
            server=uvicorn.Server(uvicorn.Config(create_app(r.folder,runtime=r,network=False),log_level='error',access_log=False));servers.append(server)
            running.append(asyncio.create_task(server.serve(sockets=[sock])))
        web=httpx.AsyncClient(base_url='http://127.0.0.1:'+str(port),headers={'Authorization':'Bearer '+r.service.base.owner_token},trust_env=False,timeout=35);clients.append(web)
        for _ in range(200):
            try:
                if (await web.get('/api/local/ready')).status_code==200:return web
            except httpx.RequestError:pass
            await asyncio.sleep(.1)
        raise TimeoutError('Web not ready')
    def request(op,payload=None,peer=None,key=None):return {'contract_version':'companion.capability.v6','request_id':key or uuid4().hex,'operation':op,'payload':payload or {},'peer_id':peer}
    async def cap(web,op,payload=None,peer=None,key=None):
        response=await web.post('/api/local/capabilities/invoke',json=request(op,payload,peer,key));response.raise_for_status();return response.json()['data']
    async def mcp(body,web=None):
        async def call(session):
            await session.initialize();value=await session.call_tool('invoke_companion_capability',{'request':body});assert not value.isError
            return value.structuredContent or json.loads(value.content[0].text)
        if web:
            async with streamablehttp_client(str(web.base_url).rstrip('/')+'/mcp/',headers=web.headers) as (read,write,_):
                async with ClientSession(read,write) as session:return await call(session)
        env={**os.environ,'HYPER_GROWTH_DATA':str(t.folder),'PYTHONPATH':str(ROOT/'src'),'PYTHONUTF8':'1'}
        args=['-m','growth_local.mcp','--data',str(t.folder)]
        if a.executable:
            env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','PYTHONHOME']};args=['--mcp','--data',str(t.folder)]
        async with stdio_client(StdioServerParameters(command=a.executable or sys.executable,args=args,env=env)) as (read,write):
            async with ClientSession(read,write) as session:return await call(session)
    try:
        tw=await start(t);sw=await start(s)
        c=await cap(tw,'review.context',target,s.identity.id)
        body=request('review.context',target,s.identity.id,key='same-context')
        response=await tw.post('/api/local/capabilities/invoke',json=body);response.raise_for_status();expected=response.json()
        assert await mcp(body)==expected and await mcp(body,tw)==expected
        forbidden=await sw.post('/api/local/capabilities/invoke',json=body);assert forbidden.status_code in [400,403]
        assert (await tw.get('/assets/review.js')).status_code==200 and (await tw.get('/assets/review.css')).status_code==200
        model_report={'called':False}
        if a.env_file:
            values=dict(line.split('=',1) for line in Path(a.env_file).read_text(encoding='utf-8-sig').splitlines() if line.strip() and not line.lstrip().startswith('#') and '=' in line)
            key=values['GROWTH_MODEL_KEY'].strip().strip('\"\'');base=values['GROWTH_MODEL_URL'].strip().rstrip('/').removesuffix('/chat/completions')
            cfg={'provider':'deepseek' if base=='https://api.deepseek.com' else 'openai','base_url':base,'model':values['GROWTH_MODEL_NAME'].strip(),'key':key,'remember':False}
            saved=await tw.put('/api/local/model',json=cfg);saved.raise_for_status()
            job=(await cap(tw,'review.start',target,s.identity.id))['job']
            for _ in range(800):
                state=(await cap(tw,'review.job',{'job_id':job['id']},s.identity.id))['job']
                if state['status'] in ['completed','failed']:break
                await asyncio.sleep(.5)
            assert state['status']=='completed','Own API pre-review failed: '+str(state.get('error') or state['status'])
            candidate=next(x for x in (await cap(tw,'review.list',{'task_id':task['id']},s.identity.id))['prereviews'] if x['id']==state['result']['prereview_id'])
            model_report={'called':True,'requests':state['result']['requests'],'context_tool_used':'get_review_context' in state['result']['tools_used'],
                'model':state['result']['model'],'dimensions':len(candidate['report']['dimensions'])}
            assert key not in (await tw.get('/api/local/status')).text and key.encode() not in (t.folder/'base.sqlite3').read_bytes()
            await tw.delete('/api/local/model/key')
        else:
            report={'summary':'合成外部候选','comment':'先观察实际观点与理由。','next_step':'核对主语与动词。','uncertainties':['合成工程候选，未专业审定。'],
                'dimensions':[{'criterion':x,'observation':'可定位的当前作品句子。','evidence':'A garden help people.','status':'partial'} for x in c['source']['criteria']]}
            candidate=(await cap(tw,'review.capture',{**target,'context_hash':c['context_hash'],'report':report,'model_name':'Synthetic external Agent'},s.identity.id))['prereview']
        assert not t.task(task['id'])['attempts'][-1]['review_history'] and not t.pending(s.identity.id)
        fields={k:candidate['report'][k] for k in ['comment','next_step','dimensions']}|{'comment':'教师人工修改：先保留原意，再解释主谓一致。','outcome':'ungraded'}
        draft=(await cap(tw,'review.draft.save',{**target,'context_hash':c['context_hash'],'prereview_id':candidate['id'],'fields':fields},s.identity.id))['draft']
        assert draft['teacher_modified'] and not t.pending(s.identity.id)
        body=request('review.publish',{'draft_id':draft['id'],'expected_revision':1,'draft_hash':draft['content_hash'],'human_review_confirmed':True},s.identity.id,'publish-through-mcp')
        publication=await mcp(body);response=await tw.post('/api/local/capabilities/invoke',json=body);response.raise_for_status()
        assert publication==response.json() and await mcp(body,tw)==publication
        drain(t,s);received=s.task(task['id']);assert received['attempts'][-1]['evaluation']['comment']==fields['comment']
        assert received['companion_review_assistance'][0]['teacher_modified'] and len(received['attempts'][-1]['review_history'])==1
        report={'ok':True,'synthetic_only':True,'packaged_executable':bool(a.executable),'model':model_report,
            'version':(await tw.get('/api/local/ready')).json()['version'],'public_network_retested':False,'professional_review':'NOT_REVIEWED','human_pilot':'DEFERRED_BY_USER',
            'checks':['same scoped context over actual HTTP and independent stdio/HTTP MCP','student denied teacher pre-review',
                'model capture does not publish','teacher edit and local draft do not send','explicit MCP publication and HTTP replay are idempotent',
                'signed student feedback contains teacher edits and compact AI provenance','review web assets served'],
            'binary_sha256':hashlib.sha256(Path(a.executable).read_bytes()).hexdigest() if a.executable else None}
        (ROOT/'artifacts'/('companion-prereview-packaged.json' if a.executable else 'companion-prereview-verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        for web in clients:
            try:
                await web.delete('/api/local/model/key')
                if a.executable:await web.post('/api/local/exit',json={})
            except httpx.RequestError:pass
            await web.aclose()
        for server in servers:server.should_exit=True
        if running:await asyncio.gather(*running)
        for process in processes:
            try:process.wait(20)
            except subprocess.TimeoutExpired:process.terminate();process.wait(10)

if __name__=='__main__':asyncio.run(main())

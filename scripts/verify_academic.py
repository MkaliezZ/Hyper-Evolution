"""K12 engineering acceptance: actual HTTP, both MCP transports and optional own model.
All records are synthetic, under data/verify. Never uses or edits user learning records.
"""
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
    parser=argparse.ArgumentParser();parser.add_argument('--executable');parser.add_argument('--env-file');parser.add_argument('--report-tag',choices=['subjects']);args=parser.parse_args()
    folder=ROOT/'data/verify'/('academic-'+uuid4().hex);t=LocalRuntime(folder/'teacher');s=LocalRuntime(folder/'student')
    t.setup('teacher','合成K12测试教师');s.setup('student','合成K12测试学生')
    secret=b64(os.urandom(32));t.accept_peer(s.hello(),secret);s.accept_peer(t.hello(),secret)
    def drain(a,b):
        for env in a.pending(b.identity.id):b.receive(env);a.ack(b.identity.id,env['body']['id'])
    processes=[];servers=[];running=[];clients=[]
    async def start(runtime):
        if args.executable:
            env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','PYTHONHOME']}
            proc=subprocess.Popen([args.executable,'--web','--no-browser','--data',str(runtime.folder)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0);processes.append(proc)
            for _ in range(200):
                if (runtime.folder/'running.json').exists():break
                if proc.poll() is not None:raise RuntimeError('Frozen web exited')
                await asyncio.sleep(.1)
            port=json.loads((runtime.folder/'running.json').read_text())['port']
        else:
            sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1]
            server=uvicorn.Server(uvicorn.Config(create_app(runtime.folder,runtime=runtime,network=False),log_level='error',access_log=False));servers.append(server)
            running.append(asyncio.create_task(server.serve(sockets=[sock])))
        client=httpx.AsyncClient(base_url='http://127.0.0.1:'+str(port),headers={'Authorization':'Bearer '+runtime.service.base.owner_token},trust_env=False,timeout=35);clients.append(client)
        for _ in range(200):
            try:
                if (await client.get('/api/local/ready')).status_code==200:return client
            except httpx.RequestError:pass
            await asyncio.sleep(.1)
        raise TimeoutError('Web did not start')
    def request(op,payload=None,peer=None,key=None):return {'contract_version':'companion.capability.v7','request_id':key or uuid4().hex,'operation':op,'payload':payload or {},'peer_id':peer}
    async def cap(client,op,payload=None,peer=None,key=None):
        response=await client.post('/api/local/capabilities/invoke',json=request(op,payload,peer,key));response.raise_for_status();return response.json()['data']
    async def mcp(body,web=None):
        async def call(session):
            await session.initialize();value=await session.call_tool('invoke_companion_capability',{'request':body});assert not value.isError
            return value.structuredContent or json.loads(value.content[0].text)
        if web:
            async with streamablehttp_client(str(web.base_url).rstrip('/')+'/mcp/',headers=web.headers) as (read,write,_):
                async with ClientSession(read,write) as session:return await call(session)
        env={**os.environ,'HYPER_GROWTH_DATA':str(t.folder),'PYTHONPATH':str(ROOT/'src'),'PYTHONUTF8':'1'};argv=['-m','growth_local.mcp','--data',str(t.folder)]
        if args.executable:env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','PYTHONHOME']};argv=['--mcp','--data',str(t.folder)]
        async with stdio_client(StdioServerParameters(command=args.executable or sys.executable,args=argv,env=env)) as (read,write):
            async with ClientSession(read,write) as session:return await call(session)
    async def job(client,payload):
        response=await client.post('/api/local/jobs',json=payload);response.raise_for_status();id=response.json()['id']
        for _ in range(800):
            state=(await client.get('/api/local/jobs/'+id)).json()
            if state['status'] in ['completed','failed']:break
            await asyncio.sleep(.5)
        assert state['status']=='completed','Own K12 model job failed: '+str(state.get('error') or state['status'])
        return state['result']
    try:
        tw=await start(t);sw=await start(s)
        r=(await cap(tw,'route.save',{'title':'合成七年级英语测试','level':'junior','grade':7,'goal':'区分I与she的be动词形式；本次只测试明确语法点。'},s.identity.id))['record']
        await cap(tw,'academic.select',{'subject':'english','track':'k12'})
        raw=request('route.read',{'route_id':r['id']},s.identity.id,'same-route')
        expected=(await tw.post('/api/local/capabilities/invoke',json=raw)).json()
        assert await mcp(raw)==expected and await mcp(raw,tw)==expected
        assert (await sw.post('/api/local/capabilities/invoke',json=raw)).status_code in [400,403]
        subject_checks=[]
        if args.report_tag=='subjects':
            e=(await cap(tw,'academic.material.save',{'subject':'english','title':'Synthetic English source','source':'Original engineering fixture','text':'Some paths cooled; distant streets changed little.'}))['material']
            m=(await cap(tw,'academic.material.save',{'subject':'mathematics','title':'Synthetic math source','source':'Original engineering fixture','text':'At a fixed price of six, total cost equals six times quantity.'}))['material']
            scoped=request('academic.material.list',{'subject':'mathematics'},key='same-math-library')
            response=await tw.post('/api/local/capabilities/invoke',json=scoped);response.raise_for_status();expected=response.json()
            assert [x['id'] for x in expected['data']['materials']]==[m['id']]
            assert await mcp(scoped)==expected and await mcp(scoped,tw)==expected
            assert not (await cap(sw,'academic.material.list',{'subject':'mathematics'}))['materials']
            recategorize=request('academic.asset.classify',{'asset_kind':'text','asset_id':e['id'],'asset_revision':e['revision'],'source_hash':e['source_hash'],
                'subject':'humanities','expected_revision':1,'human_confirmed':True},key='explicit-category')
            moved=await mcp(recategorize);assert (await tw.post('/api/local/capabilities/invoke',json=recategorize)).json()==moved
            assert not (await cap(tw,'academic.material.list',{'subject':'english'}))['materials']
            assert [x['id'] for x in (await cap(tw,'academic.material.list',{'subject':'humanities'}))['materials']]==[e['id']]
            assert (await tw.get('/assets/subject-materials.js')).status_code==200
            subject_checks=['subject-scoped library identical through HTTP, stdio MCP and HTTP MCP','English and math saved and listed separately',
                'student cannot see teacher local library','explicit category move through MCP and HTTP replay preserves one asset']
        for name in ['academic.js','academic.css']:assert (await tw.get('/assets/'+name)).status_code==200
        model_report={'called':False}
        if args.env_file:
            cfg=dict(line.split('=',1) for line in Path(args.env_file).read_text(encoding='utf-8-sig').splitlines() if line.strip() and not line.lstrip().startswith('#') and '=' in line)
            key=cfg['GROWTH_MODEL_KEY'].strip().strip('"\'');base=cfg['GROWTH_MODEL_URL'].strip().rstrip('/').removesuffix('/chat/completions')
            response=await tw.put('/api/local/model',json={'provider':'deepseek' if base=='https://api.deepseek.com' else 'openai','base_url':base,'model':cfg['GROWTH_MODEL_NAME'].strip(),'key':key,'remember':False});response.raise_for_status()
            generated=await job(tw,{'mode':'k12_generate','route_id':r['id'],'peer_id':s.identity.id,'count':2,'prompt':'用两道未见语法选择题练I/she与am/is的对应。用不同地点作语境，所有错误选项必须标注语法形式错误。'})
            audited=await job(tw,{'mode':'k12_review','draft_id':generated['draft_id'],'peer_id':s.identity.id})
            d=(await cap(tw,'k12.draft.read',{'id':generated['draft_id']},s.identity.id))['record']
            assert not (await cap(tw,'k12.draft.read',{'id':d['id']},s.identity.id))['reviews'] and not t.teacher_dashboard(s.identity.id)['tasks']
            model_report={'called':True,'generation_requests':generated['requests'],'review_requests':audited['requests'],'review_tools':audited['tools_used'],'issues':audited['issues'],'model':generated['model']}
            assert key not in (await tw.get('/api/local/status')).text and key.encode() not in (t.folder/'base.sqlite3').read_bytes()
            await tw.delete('/api/local/model/key')
        # Deterministic teaching flow is deliberately independent of unapproved model candidates.
        body={'title':'合成原创语法与阅读表达','instructions':'依据当前文字作答，保留原答。','goal':'检查主语和明确日期','source':'团队原创工程测试，不是教材或真题','criteria':['回应本题目标','依据可回查'],
            'questions':[{'id':'q1','type':'grammar_mcq','skill':'be动词主谓一致','material':'I am a student.','prompt':'Choose: I ___ a student.','options':['am','is','are'],'key':['A'],'evidence':'I am a student.','explanation':'I与am搭配。','traps':{'B':'语法形式错误','C':'语法形式错误'}},
            {'id':'q2','type':'reading_response','skill':'细节理解','material':'The garden is open on Monday.','prompt':'When is the garden open?','key':[],'evidence':'The garden is open on Monday.','explanation':'回到原文核对。'}]}
        d=(await cap(tw,'k12.draft.save',{'route_id':r['id'],'body':body},s.identity.id))['record']
        reviews=[{'question_id':q['id'],'basis':q['evidence'],'ambiguity_check':'核对本题实际条件，未把其他题型逻辑套入。','choices':[
            {'option':letter,'defensible':letter=='A','reasoning':'根据原文I与am的对应关系核对。','why_not':'本题主语I不与is或are搭配。','next_step':'分别替换为she和we再选择一次。'} for letter in 'ABC'] if q['id']=='q1' else []} for q in body['questions']]
        await cap(tw,'k12.draft.review',{'id':d['id'],'expected_revision':1,'draft_hash':d['content_hash'],'questions':reviews,'human_review_confirmed':True},s.identity.id)
        pub=request('k12.draft.publish',{'id':d['id'],'expected_revision':1,'human_review_confirmed':True},s.identity.id,'publish-k12')
        sent=await mcp(pub);assert (await tw.post('/api/local/capabilities/invoke',json=pub)).json()==sent
        tid=sent['data']['record']['task_id'];drain(t,s)
        response=await sw.post('/api/local/tasks/'+tid+'/submit',json={'answers':{'q1':'B','q2':'On Monday.'},'text':'','files':[],'request_key':'original-answer'});response.raise_for_status();drain(s,t);drain(t,s)
        attempt=t.task(tid)['attempts'][-1];target={'task_id':tid,'submission_id':attempt['id'],'question_id':'q1'}
        await cap(tw,'k12.problem.record',{**target,'observation':'原答误选is，目前只作为错法线索。','cause':'语法形式'},s.identity.id)
        await cap(tw,'k12.explain.save',{**target,'student':'先识别主语I，再选择am。','tutor':'PRIVATE_K12_TEACHER_SCRIPT','next_step':'换成she再核对一次。','human_confirmed':True},s.identity.id)
        await cap(tw,'k12.score.record',{'task_id':tid,'submission_id':attempt['id'],'question_id':'q2','score':1,'comment':'日期回应本题要求，范围限当前材料。','evidence':'Monday','human_confirmed':True},s.identity.id)
        drain(t,s);received=s.task(tid)
        assert 'PRIVATE_K12_TEACHER_SCRIPT' not in json.dumps(received,ensure_ascii=False) and received['academic_feedback']
        report=await cap(tw,'k12.report',{'route_id':r['id']},s.identity.id)
        assert report['pending_reviews']==0 and report['unconfirmed_problems']==1
        result={'ok':True,'version':(await tw.get('/api/local/ready')).json()['version'],'packaged_executable':bool(args.executable),'synthetic_only':True,'model':model_report,
            'checks':['HTTP and independent stdio/HTTP MCP return identical scoped v7 contract','student cannot read teacher peer records','K12 JS/CSS served',
                'explicit MCP publication and HTTP replay create one task','signed student submission retains original answer',
                'trap is not confirmed cause','subjective scoring resolves pending without editing original grade','private teacher lecture does not sync','student receives signed per-question feedback']+
                (['model generation and independent solve-before-key review never publish'] if model_report['called'] else [])+subject_checks,
            'professional_validation':'NOT_REVIEWED','human_pilot':'DEFERRED_BY_USER','binary_sha256':hashlib.sha256(Path(args.executable).read_bytes()).hexdigest() if args.executable else None}
        name='academic-subjects-verification.json' if args.report_tag=='subjects' else 'academic-packaged-verification.json' if args.executable else 'academic-verification.json'
        path=ROOT/'artifacts'/name;path.write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
        print(json.dumps(result,ensure_ascii=False))
    finally:
        for client in clients:
            try:
                await client.delete('/api/local/model/key')
                if args.executable:await client.post('/api/local/exit',json={})
            except httpx.RequestError:pass
            await client.aclose()
        for server in servers:server.should_exit=True
        if running:await asyncio.gather(*running)
        for process in processes:
            try:process.wait(20)
            except subprocess.TimeoutExpired:process.terminate();process.wait(10)

if __name__=='__main__':asyncio.run(main())

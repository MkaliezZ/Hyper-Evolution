"""Real HTTP and independent stdio/HTTP MCP; optional frozen Windows executables."""
import argparse,asyncio,base64,io,json,os,socket,subprocess,sys,logging
from pathlib import Path
from uuid import uuid4
import httpx,uvicorn
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from base.app.local_runtime import LocalRuntime
from base.app.local_identity import b64
from growth_local.web import create_app

logging.getLogger('httpx').setLevel(logging.WARNING)
ROOT=Path(__file__).resolve().parents[1]
async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--executable');args=parser.parse_args()
    folder=ROOT/'data/verify'/('evolution-'+uuid4().hex)
    t=LocalRuntime(folder/'teacher');s=LocalRuntime(folder/'student');t.setup('teacher','合成工程教师');s.setup('student','合成工程学生')
    secret=b64(os.urandom(32));t.accept_peer(s.hello(),secret);s.accept_peer(t.hello(),secret)
    def drain(a,b):
        for env in a.pending(b.identity.id):b.receive(env);a.ack(b.identity.id,env['body']['id'])
    task=t.assign(s.identity.id,'writing','writing-assignment');drain(t,s)
    servers=[];jobs=[];processes=[];clients=[]
    async def start(r):
        if args.executable:
            clean_env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','PYTHONHOME']}
            process=subprocess.Popen([args.executable,'--web','--no-browser','--data',str(r.folder)],env=clean_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(process)
            for _ in range(200):
                if (r.folder/'running.json').exists():break
                if process.poll() is not None:raise RuntimeError('Frozen web process exited')
                await asyncio.sleep(.1)
            port=json.loads((r.folder/'running.json').read_text())['port']
        else:
            app=create_app(r.folder,runtime=r,network=False);sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.listen(128)
            server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False));servers.append(server);jobs.append(asyncio.create_task(server.serve(sockets=[sock])))
            for _ in range(100):
                if server.started:break
                await asyncio.sleep(.05)
        web=httpx.AsyncClient(base_url='http://127.0.0.1:'+str(port),headers={'Authorization':'Bearer '+r.service.base.owner_token},trust_env=False,timeout=30);clients.append(web)
        for _ in range(100):
            try:
                if (await web.get('/api/local/ready')).status_code==200:break
            except httpx.RequestError:pass
            await asyncio.sleep(.1)
        return web
    async def webcall(web,op,payload=None,peer=None,key=None,version='companion.capability.v5'):
        body={'contract_version':version,'request_id':key or uuid4().hex,'operation':op,'payload':payload or {},'peer_id':peer}
        response=await web.post('/api/local/capabilities/invoke',json=body);response.raise_for_status();return response.json()
    async def mcp(r,body,http=False,web=None):
        async def call(session):
            await session.initialize();v=await session.call_tool('invoke_companion_capability',{'request':body});assert not v.isError
            return v.structuredContent or json.loads(v.content[0].text)
        if http:
            async with streamablehttp_client(str(web.base_url).rstrip('/')+'/mcp/',headers=web.headers) as (read,write,_):
                async with ClientSession(read,write) as session:return await call(session)
        params=StdioServerParameters(command=args.executable or sys.executable,args=['--data',str(r.folder)] if args.executable else ['-m','growth_local.mcp'],
            env={**os.environ,'HYPER_GROWTH_DATA':str(r.folder),'PYTHONPATH':str(ROOT/'src'),'PYTHONUTF8':'1'})
        # Console executable requires --mcp when its name is not HyperGrowthMCP.exe.
        if args.executable:
            params.args=['--mcp','--data',str(r.folder)]
            params.env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','PYTHONHOME']}
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:return await call(session)
    try:
        tw=await start(t);sw=await start(s)
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(80,60),(210,180,130)).save(stream,format='PNG')
        png=base64.b64encode(stream.getvalue()).decode()
        page=(await webcall(sw,'page.save',{'title':'Synthetic original pixels','source':'Engineering original fixture','data_base64':png},version='companion.capability.v3'))['data']['page']
        assert (await webcall(sw,'page.read',{'page_id':page['id']},version='companion.capability.v3'))['data']['data_base64']==png
        policy=(await webcall(sw,'policy.check',version='companion.capability.v4'))['data']['check'];assert len(policy['cases'])==20 and policy['engineering_passed']
        material=(await webcall(sw,'material.save',{'title':'Synthetic retrieval source','source':'Team original','text':'A garden cooled local paths. Distant streets changed little.'},version='companion.capability.v2'))['data']['material']
        index=(await webcall(sw,'index.build',version='companion.capability.v4'))['data']['index']
        hits=(await webcall(sw,'index.search',{'index_id':index['id'],'query':'Distant streets'},version='companion.capability.v4'))['data']['hits']
        assert any(h['source_ref'].get('material_id')==material['id'] for h in hits)
        method=(await webcall(tw,'method.candidate',{'title':'合成方法候选，不作专业发布','problem':'学习者对观点的理由缺少具体解释',
            'intended_scope':'仅验证合成记录流程，不推广为所有学科统一题型','use_basis':'团队原创合成工程资料，不含真实个人记录',
            'provenance_statement':'开发者原创合成测试，未使用真实师生作品','deidentification_note':'不包含姓名、联系方式和学校等个人信息',
            'procedure':['先观察一份实际作品再定位困难'],'acceptance':['只核对工程字段与记录，不确认教学效果'],
            'good_case':'用实际作品的困难选择形式，先验证问题而不是直接生成长篇成稿',
            'bad_case':'忽略具体困难，把各种学习任务都套成同一种题型',
            'evidence_limits':'只有合成案例，专业审阅和真实学习效果未验证'}))['data']['method']
        assert (await webcall(tw,'method.read',{'candidate_id':method['id']}))['data']['candidate']['content_hash']==method['content_hash']
        path=(await webcall(tw,'path.create',{'title':'合成学习安排','goal':'解释观点与理由','steps':[{'id':'one','action':'先写原始观点'}],
            'reason':'工程闭环演示，不代表实际教学方案','task_ids':[task['id']]},s.identity.id))['data']['path']
        await webcall(tw,'path.publish',{'path_id':path['id'],'expected_revision':1},s.identity.id);drain(t,s)
        assert (await webcall(sw,'path.read',{'path_id':path['id']}))['data']['path']['content_hash']==path['content_hash']
        d=(await webcall(sw,'writing.create',{'title':'原始表达','goal':'让主语和动词对应','text':'A garden help people.','task_id':task['id']}))['data']['document']
        suggestion=(await webcall(sw,'writing.suggest',{'document_id':d['id'],'expected_revision':1,
            'edits':[{'start':9,'end':13,'original':'help','replacement':'helps','reason':'用局部改动解释主谓一致'}]}))['data']['suggestion']
        p=(await webcall(sw,'writing.preview',{'document_id':d['id'],'expected_revision':1,'suggestion_ids':[suggestion['id']],
            'contribution_note':'合成演示：理解理由后选择采用','additional_help':'外部候选建议'}))['data']['preview']
        await webcall(sw,'writing.confirm',{'preview_id':p['id'],'preview_hash':p['content_hash'],'expected_revision':1})
        body={'contract_version':'companion.capability.v5','request_id':'exact-parity','operation':'writing.read','payload':{'document_id':d['id']}}
        value=(await sw.post('/api/local/capabilities/invoke',json=body)).json()
        assert await mcp(s,body)==value and await mcp(s,body,True,sw)==value
        assert value['data']['versions'][0]['text']=='A garden help people.' and value['data']['document']['text']=='A garden helps people.'
        await webcall(sw,'writing.submit',{'document_id':d['id'],'expected_revision':2,'additional_help':'合成外部建议，未验证独立完成'},key='submit')
        drain(s,t);drain(t,s);ref=t.task(task['id'])['attempts'][-1]['answer']['writing_history_ref']
        actual=(await webcall(tw,'writing.history',{'task_id':task['id'],'history_id':ref['id']},s.identity.id))['data']['history']
        assert len(actual['versions'])==2 and actual['versions'][-1]['contribution']=='external_assisted_revision'
        forbidden=await sw.post('/api/local/capabilities/invoke',json={'contract_version':'companion.capability.v5','request_id':'deny',
            'operation':'path.preview','payload':{'path_id':path['id'],'expected_revision':1,'title':'forbidden','goal':'forbidden','reason':'forbidden','steps':[{'id':'x','action':'x'}]}})
        assert forbidden.status_code in [400,403]
        assert (await sw.get('/assets/evolution.js')).status_code==200 and (await tw.get('/assets/method-assets.js')).status_code==200
        report={'ok':True,'packaged_executable':bool(args.executable),'synthetic_only':True,'public_network_retested':False,
            'checks':['signed teacher plan published; student read-only','candidate edits preserve first draft','preview-confirm creates attributable revision',
                'same result over real HTTP, independent stdio MCP and HTTP MCP','explicit submit transfers validated history sidecar',
                'student cannot overwrite teacher plan','v2 source and v4 actual retrieval','P01-P10 twenty cases loaded and executed',
                'Pillow stores and returns exact PNG bytes','method candidate stored separately from private records','new web assets packaged'],
            'binary_sha256':__import__('hashlib').sha256(Path(args.executable).read_bytes()).hexdigest() if args.executable else None,
            'domain_review':'NOT_REVIEWED','learning_effect':'NOT_TESTED'}
        (ROOT/'artifacts'/('companion-evolution-packaged.json' if args.executable else 'companion-evolution-verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        for web in clients:
            if args.executable:
                try:await web.post('/api/local/exit',json={})
                except httpx.RequestError:pass
            await web.aclose()
        for server in servers:server.should_exit=True
        if jobs:await asyncio.gather(*jobs)
        for process in processes:
            try:process.wait(15)
            except subprocess.TimeoutExpired:process.terminate();process.wait(10)

if __name__=='__main__':asyncio.run(main())

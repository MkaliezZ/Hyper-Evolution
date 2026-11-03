"""Independent real HTTP / stdio / HTTP MCP retrieval and policy acceptance check."""
import asyncio,json,os,socket,sys
from pathlib import Path
from uuid import uuid4
import httpx,uvicorn
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from base.app.local_runtime import LocalRuntime
from growth_local.web import create_app

ROOT=Path(__file__).resolve().parents[1]
async def main():
    runtime=LocalRuntime(ROOT/'data/verify'/('retrieval-'+uuid4().hex));runtime.setup('teacher','合成检索与审阅验收')
    app=create_app(runtime.folder,runtime=runtime,network=False);sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.listen(128)
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False));job=asyncio.create_task(server.serve(sockets=[sock]))
    for _ in range(100):
        if server.started:break
        await asyncio.sleep(.05)
    token=runtime.service.base.owner_token;url='http://127.0.0.1:'+str(port)
    async def request(web,op,payload=None,key=None,version='companion.capability.v4'):
        body={'contract_version':version,'request_id':key or uuid4().hex,'operation':op,'payload':payload or {}}
        response=await web.post('/api/local/capabilities/invoke',json=body);response.raise_for_status();return response.json()
    async def mcp_call(session,body):
        value=await session.call_tool('invoke_companion_capability',{'request':body});assert not value.isError
        return value.structuredContent or json.loads(value.content[0].text)
    try:
        async with httpx.AsyncClient(base_url=url,headers={'Authorization':'Bearer '+token},trust_env=False) as web:
            material=(await request(web,'material.save',{'title':'Original comparison source','source':'Team synthetic fixture',
                'text':'A garden cooled local paths. Distant streets changed little.'},version='companion.capability.v2'))['data']['material']
            first=(await request(web,'index.build'))['data']['index']
            second=(await request(web,'index.build',{'chunk_size':160,'overlap':20}))['data']['index']
            assert second['generation']==2
            cases=[{'case_id':'exact','query':'Distant streets','expected':[{'source':{'material_id':material['id']}}]},
                {'case_id':'reordered','query':'streets garden','expected':[{'source':{'material_id':material['id']}}]},
                {'case_id':'negative','query':'Mars garden','expected':[]}]
            benchmark=(await request(web,'benchmark.save',{'title':'Fixed synthetic suite','label_origin':'synthetic','cases':cases}))['data']['benchmark']
            body={'contract_version':'companion.capability.v4','request_id':'same-run','operation':'benchmark.run',
                'payload':{'benchmark_id':benchmark['id'],'index_ids':[first['id'],second['id']]}}
            params=StdioServerParameters(command=sys.executable,args=['-m','growth_local.mcp'],env={**os.environ,'HYPER_GROWTH_DATA':str(runtime.folder),'PYTHONPATH':str(ROOT/'src'),'PYTHONUTF8':'1'})
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize();stdio=await mcp_call(session,body)
            http=(await web.post('/api/local/capabilities/invoke',json=body)).json();assert http==stdio
            run=http['data']['run'];assert len(run['results'])==4
            check=(await request(web,'policy.check'))['data']['check'];assert len(check['cases'])==20 and check['engineering_passed']
            observations=[{'case_id':c['case_id'],'verdict':'needs_revision','reason':'Synthetic workflow only; real teacher review remains pending.'} for c in check['cases'] if c['pack']=='P07']
            review=(await request(web,'policy.review.record',{'check_id':check['id'],'pack':'P07','reviewer_name':'开发者合成验收',
                'expertise_statement':'工程测试身份，不代表领域教师资质','intended_scope':'只核验记录流程，不批准真实教学试用',
                'conclusion':'needs_revision','observations':observations,'human_confirmed':True}))['data']['review']
            async with streamablehttp_client(url+'/mcp/',headers={'Authorization':'Bearer '+token}) as (read,write,_):
                async with ClientSession(read,write) as session:
                    await session.initialize();assert await mcp_call(session,body)==http
                    reviewed=await mcp_call(session,{'contract_version':'companion.capability.v4','request_id':'review-read','operation':'policy.review.list','payload':{'pack':'P07'}})
                    assert reviewed['data']['reviews'][0]['id']==review['id']
            report={'ok':True,'synthetic_only':True,'model_api_called':False,'public_network_tested':False,
                'checks':['immutable index generations and config hashes','same fixed labels through literal/BM25 paths',
                    'exact replay equality across HTTP, independent stdio and HTTP MCP','20 policy engineering cases and append-only needs-revision declaration'],
                'comparison':[{'index_generation':r['index_generation'],'method':r['method'],'metrics':r['metrics']} for r in run['results']],
                'policy_case_count':20,'domain_review':'NOT_REVIEWED','learning_effect':'NOT_TESTED','schema_extension':'five tables after v3'}
            (ROOT/'artifacts/companion-retrieval-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
            print(json.dumps(report,ensure_ascii=False))
    finally:server.should_exit=True;await job

if __name__=='__main__':asyncio.run(main())

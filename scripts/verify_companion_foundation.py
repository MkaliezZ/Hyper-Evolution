"""Synthetic HTTP + real stdio/HTTP MCP acceptance. Only creates isolated QA data."""
import asyncio
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import sys
from uuid import uuid4
import httpx
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from base.app.local_runtime import LocalRuntime
from base.app.local_identity import b64
from growth_local.web import create_app

ROOT = Path(__file__).resolve().parents[1]


async def call(client, name, args=None):
    result = await client.call_tool(name, args or {})
    assert not result.isError, name
    return result.structuredContent or json.loads(result.content[0].text)


def drain(a,b):
    for envelope in a.pending(b.identity.id):
        b.receive(envelope)
        a.ack(b.identity.id,envelope['body']['id'])


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-node',help='Optional Node executable with playwright available via NODE_PATH')
    parser.add_argument('--study',action='store_true',help='Also verify source learning, assessment ledger and bank preview')
    args=parser.parse_args()
    data=ROOT/'data/verify'/('companion-'+uuid4().hex)
    runtimes={role:LocalRuntime(data/role) for role in ['teacher','student']}
    teacher,student=runtimes['teacher'],runtimes['student']
    teacher.setup('teacher','合成验收教师');student.setup('student','合成验收学生')
    secret=b64(secrets.token_bytes(32))
    teacher.accept_peer(student.hello(),secret);student.accept_peer(teacher.hello(),secret)
    servers=[];jobs=[];clients={};urls={};checks=[]
    try:
        for role,runtime in runtimes.items():
            app=create_app(runtime.folder,runtime=runtime,network=False)
            sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
            urls[role]=f'http://127.0.0.1:{sock.getsockname()[1]}'
            server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
            servers.append(server);jobs.append(asyncio.create_task(server.serve(sockets=[sock])))
            for _ in range(100):
                if server.started:break
                await asyncio.sleep(.05)
            assert server.started
            clients[role]=httpx.AsyncClient(base_url=urls[role],headers={'Authorization':'Bearer '+runtime.service.base.owner_token},trust_env=False)
            (data/role/'qa-launch-url.txt').write_text(urls[role]+'/#start='+app.state.bootstrap,encoding='utf8')
        web=clients['student'];tw=clients['teacher']
        own=await web.post('/api/local/tasks',json={'purpose':'writing','request_key':'own'});own.raise_for_status()
        remote=await tw.post('/api/local/tasks',json={'peer_id':student.identity.id,'purpose':'writing','request_key':'assigned'});remote.raise_for_status()
        tid=remote.json()['id'];drain(teacher,student)
        submitted=await web.post(f'/api/local/tasks/{tid}/submit',json={'answers':{},'text':'Synthetic first draft, with an explicit request.','files':[],'request_key':'first'})
        submitted.raise_for_status();drain(student,teacher);drain(teacher,student)
        sid=teacher.task(tid)['attempts'][0]['id']
        feedback=await tw.post(f'/api/local/feedback/{sid}',json={'comment':'合成反馈：补充论据。','next_step':'修改后在新情境再试。','judgement':'needs_revision','request_key':'review'})
        feedback.raise_for_status();drain(teacher,student)
        assert (await web.get(f'/api/local/tasks/{tid}')).json()['attempts'][0]['evaluation']['judgement']=='needs_revision'
        checks.append('real HTML HTTP assignment/submission/teacher feedback/readback, independent databases and signed messages')
        async with httpx.AsyncClient(base_url=urls['student'],trust_env=False) as anonymous:
            assert (await anonymous.get('/api/local/evidence')).status_code==401
        assert (await web.get('/api/local/evidence',params={'peer_id':teacher.identity.id})).status_code==403
        checks.append('HTTP evidence authentication and role isolation')
        if args.study:
            async def study(client,operation,payload=None,peer=None,key=None):
                response=await client.post('/api/local/capabilities/invoke',json={'contract_version':'companion.capability.v2','request_id':key or uuid4().hex,'operation':operation,'payload':payload or {},'peer_id':peer})
                response.raise_for_status();return response.json()
            material=(await study(tw,'material.save',{'title':'Original source learning','text':'The garden cooled nearby paths. Distant streets changed little. Conditions matter.','source':'Original synthetic example'}))['data']['material']
            created=await study(tw,'activity.create',{'material_id':material['id'],'revision':1,'source_hash':material['source_hash'],'goal':'Explain the limits of the claim','method':'apply'},student.identity.id)
            reading_tid=created['data']['task_id'];drain(teacher,student)
            submit=await web.post(f'/api/local/tasks/{reading_tid}/submit',json={'answers':{},'text':'The effect depends on distance, because distant streets changed little.','files':[],'request_key':'reading-work','learning_conditions':{'normal_participation':'Read the passage','additional_help':'No additional help reported'}})
            submit.raise_for_status();drain(student,teacher);drain(teacher,student)
            reading_sid=teacher.task(reading_tid)['attempts'][0]['id']
            record={'task_id':reading_tid,'submission_id':reading_sid,'source_type':'teacher_review','outcome':'needs_revision','comment':'Name the conditions precisely.','next_step':'Give a concrete application.','human_review_confirmed':True}
            await study(tw,'assessment.record',record,student.identity.id,'reading-review');drain(teacher,student)
            assert len((await study(web,'assessment.list',{'task_id':reading_tid}))['data']['entries'])==1
            assert (await study(web,'material.read',{'task_id':reading_tid}))['data']['selection'].startswith('The garden')
            revised=await web.post(f'/api/local/tasks/{reading_tid}/submit',json={'answers':{},'text':'Revised: a nearby shaded path can cool, while a distant street may not.','files':[],'request_key':'reading-revision'})
            revised.raise_for_status();drain(student,teacher);drain(teacher,student)
            assert len(student.task(reading_tid)['attempts'])==2
            assert len((await study(web,'assessment.list',{'task_id':reading_tid}))['data']['entries'])==1
            from base.app.content import make_drill
            bank=(await study(tw,'bank.preview',{'format':'json','content':json.dumps([make_drill('toefl','predeparture',seed='synthetic-study-bank')])}))['data']
            imported=await study(tw,'bank.commit',{'preview_id':bank['id'],'preview_hash':bank['preview_hash']},key='study-bank-confirm')
            assert len(imported['data']['imported'])==1 and imported['data']['status']=='pending_review'
            checks.append('source learning: frozen method/source, declared help, signed append-only review and pending bank import')
        request={'request_id':'real-dual-entry','operation':'evidence.read'}
        http_result=await web.post('/api/local/capabilities/invoke',json=request);http_result.raise_for_status()
        assert {x['origin'] for x in http_result.json()['data']['tasks']}=={'self','teacher'}
        params=StdioServerParameters(command=sys.executable,args=['-m','growth_local.mcp'],env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'HYPER_GROWTH_DATA':str(student.folder),'PYTHONUTF8':'1'})
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                names={t.name for t in (await session.list_tools()).tools}
                assert 'submit_work' in names and 'record_teacher_feedback' not in names
                assert await call(session,'invoke_companion_capability',{'request':request})==http_result.json()
                evidence=await call(session,'get_authorized_evidence')
                ref=next(t for t in evidence['data']['tasks'] if t['id']==tid)['source_ref']
                resolved=await call(session,'invoke_companion_capability',{'request':{'request_id':'resolve','operation':'asset.resolve','input_refs':[ref]}})
                assert resolved['status']=='completed'
                checks.append('real stdio initialization, scoped tools, exact HTTP/MCP evidence parity and versioned source resolution')
                if args.study:
                    study_request={'contract_version':'companion.capability.v2','request_id':'real-study-parity','operation':'assessment.list','payload':{'task_id':reading_tid}}
                    assert await call(session,'invoke_companion_capability',{'request':study_request})==(await web.post('/api/local/capabilities/invoke',json=study_request)).json()
                    checks.append('v2 study contract exact parity across real stdio MCP and web')
                student.unpair(teacher.identity.id)
                denied=await session.call_tool('invoke_companion_capability',{'request':{'request_id':'revoked','operation':'asset.resolve','input_refs':[ref]}})
                assert denied.isError
                checks.append('independent MCP process observes current pairing revocation')
        async with streamablehttp_client(urls['student']+'/mcp/',headers={'Authorization':'Bearer '+student.service.base.owner_token}) as (read,write,_):
            async with ClientSession(read,write) as session:
                await session.initialize()
                after=await call(session,'invoke_companion_capability',{'request':request})
                now=(await web.post('/api/local/capabilities/invoke',json=request)).json()
                assert after==now and after['data']['coverage']['excluded_revoked_tasks']==(2 if args.study else 1)
                checks.append('real authenticated HTTP MCP matches HTML after revocation')
        # Browser smoke input stays in ignored synthetic data; no credential is printed.
        config={'student':{'url':urls['student'],'launch_file':str(data/'student/qa-launch-url.txt')},
                'teacher':{'url':urls['teacher'],'launch_file':str(data/'teacher/qa-launch-url.txt')}}
        (data/'browser-input.json').write_text(json.dumps(config),encoding='utf8')
        browser_verified=False
        if args.browser_node:
            student.accept_peer(teacher.hello(),secret)
            process=await asyncio.create_subprocess_exec(args.browser_node,str(ROOT/'scripts'/('verify_companion_study.cjs' if args.study else 'verify_companion_browser.cjs')),str(data/'browser-input.json'),cwd=ROOT)
            assert await process.wait()==0,'Browser smoke failed'
            browser_verified=True
            checks.append('real Chromium student/teacher HTML, student creates and submits an activity, same evidence API')
        report={'ok':True,'checks':checks,'three_layer_contract':'three-layer.v1','runtime_schema':'companion.capability.v1',
                'synthetic_only':True,'database_migration':False,'model_api_called':False,'real_webrtc':'separate verify_local_peer.py',
                'browser_verified':browser_verified,
                'study_contract':'companion.capability.v2' if args.study else None,
                'schema_extension':'four additive tables; existing records not rewritten' if args.study else None,
                'domain_review':'NOT_REVIEWED','learning_effect':'NOT_TESTED'}
        (ROOT/'artifacts'/('companion-study-verification.json' if args.study else 'companion-foundation-verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        for client in clients.values():await client.aclose()
        for server in servers:server.should_exit=True
        await asyncio.gather(*jobs,return_exceptions=True)


if __name__=='__main__':asyncio.run(main())

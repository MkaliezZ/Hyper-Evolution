"""Exercise extracted online installer sources, three CLI editions, actual web/MCP and WebRTC."""
import argparse,asyncio,hashlib,json,os,socket,subprocess,sys,time,zipfile
from pathlib import Path
from uuid import uuid4
import httpx,uvicorn
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from growth_local.signal import create_app
from package_public import TAG

ROOT=Path(__file__).resolve().parents[1]


async def until(predicate,seconds=50):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=await predicate()
        if value:return value
        await asyncio.sleep(.2)
    raise AssertionError('Timed out waiting for release verification')


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--packages',default='releases');args=parser.parse_args()
    work=ROOT/'data/verify'/('public-release-'+uuid4().hex);work.mkdir(parents=True)
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1]
    signal=uvicorn.Server(uvicorn.Config(create_app(),log_level='error',access_log=False))
    signaling=asyncio.create_task(signal.serve(sockets=[sock]));processes=[];clients={};checks=[];logs=[]
    editions={'teacher':'Enlighter','student':'Evolver','self':'Self-Evolver'}
    async def signal_ready():return signal.started
    await until(signal_ready)
    try:
        for edition,brand in editions.items():
            archives=list(Path(args.packages).glob(f'Hyper-Evolution-{brand}-Windows-x64-{TAG}.zip'));assert len(archives)==1
            extracted=work/'extracted'/edition
            with zipfile.ZipFile(archives[0]) as z:
                assert z.testzip() is None
                for n in z.namelist():assert not Path(n).is_absolute() and '..' not in Path(n).parts
                z.extractall(extracted)
            source=next(extracted.iterdir());manifest=json.loads((source/'PACKAGE-MANIFEST.json').read_text(encoding='utf8'))
            assert manifest['edition']==edition and manifest['release']==TAG and not manifest['runtime_binaries_included']
            for n,digest in manifest['files'].items():assert hashlib.sha256((source/n).read_bytes()).hexdigest()==digest
            folder=work/'devices'/edition
            log=open(work/(edition+'.log'),'w',encoding='utf8');logs.append(log)
            env={**os.environ,'PYTHONPATH':str(source/'src'),'PYTHONUTF8':'1'}
            process=subprocess.Popen([sys.executable,'-m','growth_local','--edition',edition,'--no-browser','--data',str(folder),
              '--coordinator',f'ws://127.0.0.1:{port}/ws'],cwd=source,env=env,stdout=log,stderr=log)
            processes.append(process)
            async def ready():
                assert process.poll() is None,'Release launcher exited before ready'
                return (folder/'qa-launch-url.txt').exists()
            await until(ready)
            launch=(folder/'qa-launch-url.txt').read_text();base=launch.split('/#')[0]
            client=httpx.AsyncClient(base_url=base,trust_env=False,timeout=40);clients[edition]=client
            response=await client.post('/api/local/session',json={'bootstrap':launch.split('#start=')[1]});response.raise_for_status()
            status=(await client.get('/api/local/status')).json();assert status['launch_edition']==edition and not status['profile'].get('role')
            (await client.post('/api/local/setup',json={'role':edition,'name':'Original release '+brand,'exam':'toefl',
             'academic_subject':'english','academic_track':'study_abroad' if edition!='self' else 'materials'})).raise_for_status()
            for operation,payload in [('workspace.initialize',{}),('workspace.select',{'subject':'english','track':'study_abroad' if edition!='self' else 'materials'})]:
                (await client.post('/api/local/capabilities/invoke',json={'contract_version':'companion.capability.v8',
                 'request_id':uuid4().hex,'operation':operation,'payload':payload})).raise_for_status()
            status=(await client.get('/api/local/status')).json()
            assert status['profile']['role']==('teacher' if edition=='teacher' else 'student')
            assert status['experience']['id']==edition
            page=await client.get('/');assert page.status_code==200 and '超维伴学' in page.text and '超维成长' not in page.text
            assert 'launch_edition' in (await client.get('/assets/experience.js')).text
            configuration=(await client.get('/api/local/mcp-config')).json()['mcpServers']['hyper-growth-local']
            assert configuration['command']==sys.executable and configuration['env']['HYPER_GROWTH_DATA']==str(folder)
            params=StdioServerParameters(command=configuration['command'],args=configuration['args'],env={**os.environ,**configuration['env']})
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize();tools={t.name for t in (await session.list_tools()).tools}
                    result=await session.call_tool('get_local_status',{});assert not result.isError
                    data=result.structuredContent or json.loads(result.content[0].text)
                    assert data['device_id']==status['device_id']
                    assert ('assign_activity' in tools)==(edition=='teacher')
            checks.append(brand+': manifest hashes, independent CLI/identity, web assets and real stdio MCP')
        teacher,student=clients['teacher'],clients['student']
        invitation=(await teacher.post('/api/local/pair/invite')).json()
        (await student.post('/api/local/pair/join',json={'code':invitation['code']})).raise_for_status()
        async def paired():
            a=(await teacher.get('/api/local/status')).json();b=(await student.get('/api/local/status')).json()
            return a if a['peers'] and b['peers'] and 'connected' in a['network']['states'].values() else None
        paired_status=await until(paired)
        task=(await teacher.post('/api/local/tasks',json={'peer_id':paired_status['peers'][0]['id'],'purpose':'writing','request_key':'release-task'})).json()
        task_id=task['id']
        async def task_received():return (await student.get('/api/local/tasks/'+task_id)).status_code==200
        await until(task_received)
        (await student.post('/api/local/tasks/'+task_id+'/submit',json={'text':'Could you help me find a study room? I am available on Monday.','answers':{},'files':[],'request_key':'release-submit'})).raise_for_status()
        async def submitted():
            row=(await teacher.get('/api/local/tasks/'+task_id)).json()
            return row['attempts'][0] if row['attempts'] else None
        attempt=await until(submitted)
        (await teacher.post('/api/local/feedback/'+attempt['id'],json={'comment':'The request is clear; add a specific time.','next_step':'Revise with a time.','judgement':'needs_revision','request_key':'release-feedback'})).raise_for_status()
        async def feedback_received():
            row=(await student.get('/api/local/tasks/'+task_id)).json()
            return row['attempts'] and row['attempts'][0]['evaluation'].get('judgement')=='needs_revision'
        await until(feedback_received)
        (await student.post('/api/local/tasks/'+task_id+'/submit',json={'text':'Could you help me find a study room on Monday at 10 a.m.?','answers':{},'files':[],'request_key':'release-revise'})).raise_for_status()
        async def revised():return len((await teacher.get('/api/local/tasks/'+task_id)).json()['attempts'])==2
        await until(revised)
        checks.append('Independent teacher/student source packages: real WebRTC pairing, assignment, submission, signed feedback and revision')
        denied=await student.post('/api/local/capabilities/invoke',json={'contract_version':'companion.capability.v11','request_id':'release-denied','operation':'experience.select','payload':{'experience':'teacher'}})
        assert denied.status_code==403
        checks.append('Student-to-teacher privilege escalation rejected by Runtime')
        report={'ok':True,'delivery':'online-source-installer','edition_count':3,'synthetic_data_only':True,
          'actual_provider_called':False,'checks':checks,'cross_network':False,'fresh_runtime':str(sys.executable).find('.runtime')>=0}
        (ROOT/'artifacts/public-release-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        for client in clients.values():
            try:await client.post('/api/local/exit')
            except Exception:pass
            await client.aclose()
        await asyncio.sleep(1)
        for process in processes:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
        for log in logs:log.close()
        signal.should_exit=True;await signaling


if __name__=='__main__':asyncio.run(main())

"""Run the actual Windows double-click CMD installer from an extracted source package."""
import argparse,hashlib,json,os,shutil,subprocess,time,zipfile
from pathlib import Path
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--packages',default='releases');parser.add_argument('--uv-archive');options=parser.parse_args()
    work=ROOT/'data/verify'/('windows launcher '+uuid4().hex);work.mkdir(parents=True)
    package=next(Path(options.packages).glob('Hyper-Evolution-Self-Evolver-Windows-x64-*.zip'))
    with zipfile.ZipFile(package) as z:z.extractall(work/'extract')
    source=next((work/'extract').iterdir());folder=work/'my data'
    environment=dict(os.environ)
    if options.uv_archive:
        archive=Path(options.uv_archive)
        assert hashlib.sha256(archive.read_bytes()).hexdigest()=='0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021'
        (source/'.tools').mkdir();shutil.copyfile(archive,source/'.tools/uv.zip')
        environment['PATH']=os.pathsep.join(p for p in environment.get('PATH','').split(os.pathsep) if not (Path(p)/'uv.exe').is_file())
    log=open(work/'launcher.log','w',encoding='utf8')
    args=['cmd.exe','/d','/c','call',str(source/'启动-Self-Evolver.cmd'),'--no-browser','--data',str(folder)]
    process=subprocess.Popen(args,cwd=source,env=environment,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+300
        while not (folder/'qa-launch-url.txt').exists():
            assert process.poll() is None,'Launcher exited; inspect private verification log'
            assert time.monotonic()<deadline,'Installer did not become ready within 300s'
            time.sleep(.5)
        assert (source/'.runtime/Scripts/python.exe').is_file()
        actual=(source/'.runtime/hyper-evolution-lock.txt').read_text().strip().lower()
        assert actual==hashlib.sha256((source/'requirements-runtime.lock').read_bytes()).hexdigest()
        launch=(folder/'qa-launch-url.txt').read_text();base=launch.split('/#')[0]
        with httpx.Client(base_url=base,trust_env=False,timeout=40) as client:
            client.post('/api/local/session',json={'bootstrap':launch.split('#start=')[1]}).raise_for_status()
            state=client.get('/api/local/status').json();assert state['launch_edition']=='self'
            client.post('/api/local/setup',json={'role':'self','name':'Original launcher verification'}).raise_for_status()
            assert client.get('/api/local/status').json()['experience']['id']=='self'
            reopening=subprocess.Popen(args,cwd=source,env=environment,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            assert reopening.wait(timeout=45)==0
            assert process.poll() is None
            client.post('/api/local/exit').raise_for_status()
        assert process.wait(timeout=30)==0
        report={'ok':True,'platform':'Windows x64','actual_cmd_launcher':True,'fresh_venv':True,'dependency_sync':True,
          'path_with_spaces':True,'edition_hint':'self','identity':'student','repeat_open_preserves_service':True,
          'uv_bootstrap': 'verified official cached archive, checksum and extraction' if options.uv_archive else 'existing installed uv',
          'synthetic_data_only':True}
        (ROOT/'artifacts/windows-launcher-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        if (folder/'running.json').exists() and (folder/'owner-token.txt').exists():
            try:
                port=json.loads((folder/'running.json').read_text())['port']
                with httpx.Client(trust_env=False,timeout=10) as cleanup:
                    cleanup.post(f'http://127.0.0.1:{port}/api/local/exit',headers={'Authorization':'Bearer '+(folder/'owner-token.txt').read_text().strip()})
                time.sleep(.5)
            except Exception:pass
        if process.poll() is None:process.terminate()
        log.close()


if __name__=='__main__':main()

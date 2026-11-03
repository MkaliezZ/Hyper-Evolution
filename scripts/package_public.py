"""Three source-based online installer editions from one reviewed public tree."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TAG='v0.6.0-rc.1'
EDITIONS={'teacher':'Enlighter','student':'Evolver','self':'Self-Evolver'}
ALLOWED_ROOT={'README.md','LICENSE','THIRD_PARTY_NOTICES.md','CONTRIBUTING.md','SECURITY.md','ROADMAP.md','AGENTS.md',
 'pyproject.toml','requirements-local.in','requirements-local.lock','requirements-runtime.lock','requirements-mcp.lock','requirements.lock'}


def collect():
    # Tracked files only: local runtimes, data, audit logs and private Git history never enter the package.
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    for name in filter(None,paths):
        p=Path(name)
        if name in ALLOWED_ROOT or name.startswith(('src/','docs/','examples/','third_party/','scripts/','packaging/','tests/')):
            if p.name.startswith('.') or p.suffix.lower() in {'.sqlite','.sqlite3','.db','.hgb','.log','.zip','.exe','.dll','.pdf','.mp3','.wav'}:
                raise ValueError('Unexpected release file: '+name)
            yield name


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='releases');args=parser.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    files=sorted(collect());sums=[]
    for edition,brand in EDITIONS.items():
        folder=f'Hyper-Evolution-{brand}-{TAG}'
        target=out/f'Hyper-Evolution-{brand}-Windows-x64-{TAG}.zip'
        manifest={'release':TAG,'edition':edition,'brand':brand,'source_commit':commit,'platform':'Windows x64',
          'delivery':'online-source-installer','first_run_network':True,'runtime_binaries_included':False,
          'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}}
        launch=f'启动-{brand}.cmd'
        manifest['files'][launch]=hashlib.sha256((ROOT/launch).read_bytes()).hexdigest()
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
            for name in files:z.write(ROOT/name,f'{folder}/{name}')
            z.write(ROOT/launch,f'{folder}/{launch}')
            z.writestr(f'{folder}/EDITION.json',json.dumps({'edition':edition,'name':brand,'version':TAG},ensure_ascii=False,indent=2))
            z.writestr(f'{folder}/PACKAGE-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            z.writestr(f'{folder}/先读我.txt',f'Hyper Evolution / {brand} {TAG} 工程测试版\n\n完整解压，双击 {launch}。首次启动联网自动准备运行环境，随后打开本机浏览器。\n按向导配置自己的 API；学生输入老师的配对码，自学者可直接导入资料。\n\n教程：docs/getting-started.md；角色教程：docs/{dict(teacher="enlighter",student="evolver",self="self-evolver")[edition]}.md\n记录保存在用户数据目录；退出和备份从网页设置操作。\n')
        with zipfile.ZipFile(target) as z:assert z.testzip() is None
        digest=hashlib.sha256(target.read_bytes()).hexdigest();sums.append(f'{digest}  {target.name}')
        print(json.dumps({'file':target.name,'bytes':target.stat().st_size,'sha256':digest,'edition':edition}))
    (out/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='ascii')


if __name__=='__main__':main()

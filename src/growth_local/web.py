"""Loopback-only UI/API. Browser cookies and MCP bearer tokens share scoped local services."""
import asyncio
import hashlib
import hmac
import io
import json
import secrets
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from base.app.local_runtime import LocalRuntime
from base.app.local_agent import test_connection, execute_job
from growth_local.mcp import create_mcp
from growth_local.peer import PeerManager

STATIC = Path(__file__).parent / 'static'
BASE_STATIC = Path(__file__).parents[1] / 'growth' / 'static'


def create_app(data, runtime=None, network=True):
    runtime = runtime or LocalRuntime(data)
    from base.app.companion.functional.workspaces import host
    runtime=host(runtime)
    manager = PeerManager(runtime) if network else None
    mcp = create_mcp(runtime)
    background = set()
    bootstrap = secrets.token_urlsafe(32)
    sessions = set()
    cookie_name = 'hyper-growth-' + runtime.identity.id[:16]
    boot_expiry = time.time() + 600

    @asynccontextmanager
    async def lifespan(app):
        # A terminated request is not silently reported as successful after a restart.
        with runtime.db() as db:
            db.execute("UPDATE local_jobs SET status='failed',error='程序上次退出时任务未完成，请重新发起。' WHERE status='running' OR (status='queued' AND id NOT LIKE 'review-job-%')")
        async with mcp.session_manager.run():
            if manager:
                await manager.start()
            from base.app.companion.functional.workspaces import review_workers
            worker=asyncio.create_task(review_workers(runtime,background));background.add(worker)
            yield
            if manager:
                await manager.stop()
            stopping=list(background)
            for task in stopping:
                task.cancel()
            if stopping:await asyncio.gather(*stopping,return_exceptions=True)

    app = FastAPI(title='超维成长本地版', docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.runtime = runtime
    app.state.bootstrap = bootstrap

    def authorized(req):
        cookie = req.cookies.get(cookie_name)
        token = req.headers.get('authorization', '').removeprefix('Bearer ')
        return bool(cookie and cookie in sessions) or bool(token and hmac.compare_digest(token, runtime.root.service.base.owner_token))

    @app.middleware('http')
    async def guard(req, call_next):
        if req.url.hostname not in ['127.0.0.1', 'localhost', '::1']:
            return JSONResponse({'error': '本机服务拒绝此Host'}, 421)
        if req.method not in ['GET', 'HEAD', 'OPTIONS']:
            origin = req.headers.get('origin')
            if origin and origin != str(req.base_url).rstrip('/'):
                return JSONResponse({'error': '本机请求来源不匹配'}, 403)
            try:
                if int(req.headers.get('content-length', '0')) > 85 * 1024 * 1024:
                    return JSONResponse({'error': '文件过大'}, 413)
            except ValueError:
                return JSONResponse({'error': '请求长度无效'}, 400)
        if (req.url.path.startswith('/api/') and req.url.path not in ['/api/local/session', '/api/local/ready']) or req.url.path.startswith('/mcp'):
            if not authorized(req):
                return JSONResponse({'error': '请从本机快捷方式打开超维成长，或使用本机MCP凭据。'}, 401)
        if runtime.enabled() and runtime.current()=='legacy' and req.method not in ['GET','HEAD','OPTIONS']:
            permitted=['/api/local/session','/api/local/reopen','/api/local/capabilities/invoke','/api/local/model','/api/local/model/key','/api/local/model/test','/api/local/pair/','/api/local/backup/','/api/local/exit','/mcp']
            if not any(req.url.path==p or p.endswith('/') and req.url.path.startswith(p) for p in permitted):
                return JSONResponse({'error':'历史工作区只读，请先切换到目标学科。'},403)
        if runtime.enabled() and runtime.current() not in ['english','legacy'] and req.url.path.startswith(('/api/local/resources','/api/local/academic/')):
            return JSONResponse({'error':'英语题库与K12录音仅在英语工作区可见，请先切换学科。'},403)
        with runtime.bind():
            requested=req.headers.get('x-growth-workspace');actual=getattr(runtime.active(),'workspace_subject','legacy')
            if requested and runtime.enabled() and requested!=actual and req.url.path.startswith('/api/local/') and req.url.path not in ['/api/local/status','/api/local/session','/api/local/ready','/api/local/reopen','/api/local/capabilities/invoke']:
                return JSONResponse({'error':'学科工作区已切换，请刷新页面后继续，未执行旧页面的操作。'},409)
            response = await call_next(req)
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response

    for exc, code in [(ValueError, 400), (KeyError, 404), (PermissionError, 403)]:
        async def handler(req, error, status=code):
            return JSONResponse({'error': str(error).strip("'")}, status)
        app.add_exception_handler(exc, handler)

    async def body(req,max_bytes=512*1024):
        raw = await req.body()
        if len(raw) > max_bytes:
            raise ValueError('请求内容过大')
        try:
            value = json.loads(raw)
        except ValueError:
            raise ValueError('请求不是有效JSON') from None
        if not isinstance(value, dict):
            raise ValueError('请求必须是对象')
        return value

    @app.get('/api/local/ready')
    def ready():
        return {'ok': True, 'version': '0.6.0-rc.1-engineering'}

    @app.post('/api/local/session')
    async def session(req: Request):
        nonlocal bootstrap
        provided = (await body(req)).get('bootstrap')
        if time.time() > boot_expiry or not isinstance(provided, str) or not bootstrap or not hmac.compare_digest(provided, bootstrap):
            raise PermissionError('启动入口已失效，请重新使用本机快捷方式')
        bootstrap = None
        token = secrets.token_urlsafe(32)
        sessions.add(token)
        response = JSONResponse({'ok': True})
        response.set_cookie(cookie_name, token, httponly=True, samesite='strict', path='/')
        return response

    @app.post('/api/local/reopen')
    def reopen(req: Request):
        nonlocal bootstrap, boot_expiry
        # Guard requires the local bearer credential; used by the owned desktop launcher.
        bootstrap = secrets.token_urlsafe(32)
        boot_expiry = time.time() + 600
        return {'url': str(req.base_url) + '#start=' + bootstrap}

    @app.get('/api/local/status')
    def status():
        return {**runtime.status(), 'launch_edition': getattr(app.state, 'launch_edition', None)}

    @app.post('/api/local/setup')
    async def setup(req: Request):
        d = await body(req)
        subject=d.get('academic_subject');track=d.get('academic_track')
        role=d.get('role');experience=d.get('experience') or ('teacher' if role=='teacher' else 'student')
        if role=='self':role='student';experience='self'
        if experience not in (['teacher'] if role=='teacher' else ['student','self']) or role not in ['teacher','student']:
            raise ValueError('请选择教师、跟随老师学习或自主学习')
        if subject:
            from base.app.companion.aesthetic.academic import SUBJECTS
            if subject not in SUBJECTS or track not in SUBJECTS[subject]['tracks']:raise ValueError('请选择有效的学科和学习路线')
        runtime.setup(role, d.get('name'), d.get('exam', 'ielts'), d.get('stage', 'application'))
        runtime.invoke_capability({'contract_version':'companion.capability.v11','request_id':'initial-experience',
            'operation':'experience.select','payload':{'experience':experience}})
        if subject:runtime.save_config('academic-selection',{'subject':subject,'track':track})
        return runtime.status()

    @app.put('/api/local/model')
    async def model(req: Request):
        d = await body(req)
        if not d.get('key') and d.get('base_url', '').rstrip('/') != runtime.config('model', {}).get('base_url'):
            raise ValueError('更换接口地址时，请重新输入你要用于该地址的API Key')
        return runtime.save_model(d, d.get('key') or None, d.get('remember') is True)

    @app.delete('/api/local/model/key')
    def delete_key():
        return runtime.delete_model_key()

    @app.post('/api/local/model/test')
    async def model_test(req: Request):
        d = await body(req)
        existing = runtime.config('model', {})
        key = d.get('key') or (runtime.model_key() if d.get('base_url', '').rstrip('/') == existing.get('base_url') else None)
        # Validate with a throwaway configuration holder; never persist the test key.
        from urllib.parse import urlsplit
        url = d.get('base_url', '').rstrip('/')
        parts = urlsplit(url)
        if parts.scheme != 'https' and not (parts.scheme == 'http' and parts.hostname in ['127.0.0.1', 'localhost', '::1']):
            raise ValueError('请填写HTTPS模型接口地址，或本机localhost模型地址')
        if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:
            raise ValueError('接口地址格式不正确')
        return await test_connection(d, key)

    @app.post('/api/local/jobs')
    async def agent_job(req: Request):
        d = await body(req)
        if runtime.enabled() and runtime.current()!='english' and d.get('mode') in ['draft','k12_generate','k12_review','k12_workflow']:
            raise ValueError('当前学科未配置英语出题规则，请从本学科资料开始')
        if d.get('mode')=='prereview':
            return runtime.invoke_capability({'contract_version':'companion.capability.v6','request_id':d.get('request_key') or secrets.token_hex(16),
                'operation':'review.start','peer_id':d.get('peer_id'),'payload':{k:d.get(k) for k in ['task_id','submission_id']}})['data']['job']
        if not runtime.model_status()['configured']:
            raise ValueError('请先在设置中配置你自己的模型API')
        from base.app.local_agent import learning_context
        if d.get('mode')=='self_review':
            runtime.invoke_capability({'contract_version':'companion.capability.v11','request_id':'self-review-check',
                'operation':'self.feedback_context','peer_id':d.get('peer_id'),'payload':{k:d.get(k) for k in ['task_id','submission_id']}})
        elif d.get('mode')=='vision':
            runtime.invoke_capability({'contract_version':'companion.capability.v3','request_id':'vision-job-check',
                'operation':'page.read','peer_id':d.get('peer_id'),'payload':{**d.get('source',{}),'include_image':False}})
        elif d.get('mode')=='reading':
            runtime.invoke_capability({'contract_version':'companion.capability.v2','request_id':'reading-job-check',
                'operation':'material.read','peer_id':d.get('peer_id'),'payload':d.get('source',{})})
        elif d.get('mode')=='writing':
            runtime.invoke_capability({'contract_version':'companion.capability.v5','request_id':'writing-job-check',
                'operation':'writing.read','peer_id':d.get('peer_id'),'payload':{'document_id':d.get('document_id')}})
        elif d.get('mode')=='k12_review':
            runtime.invoke_capability({'contract_version':'companion.capability.v7','request_id':secrets.token_hex(16),'operation':'k12.draft.read',
                'peer_id':d.get('peer_id'),'payload':{'id':d.get('draft_id')}})
        elif d.get('mode') in ['k12_generate','k12_workflow']:
            runtime.invoke_capability({'contract_version':'companion.capability.v7','request_id':secrets.token_hex(16),'operation':'route.read',
                'peer_id':d.get('peer_id'),'payload':{'route_id':d.get('route_id')}})
        else:learning_context(runtime, d.get('peer_id'))
        with runtime.db() as db:
            count = db.execute("SELECT COUNT(*) FROM local_jobs WHERE status='running' OR (status='queued' AND id NOT LIKE 'review-job-%')").fetchone()[0]
        if count >= 2:
            raise ValueError('已有模型任务运行中，请先等待完成')
        job_id = runtime.create_job(d)
        task = asyncio.create_task(execute_job(runtime, job_id))
        background.add(task)
        task.add_done_callback(background.discard)
        return {'id': job_id, 'status': 'queued'}

    @app.get('/api/local/jobs/{id}')
    def job(id: str):
        return runtime.job(id)

    @app.get('/api/local/jobs')
    def jobs():
        with runtime.db() as db:
            rows=db.execute('SELECT id,status,created,error,body FROM local_jobs ORDER BY created DESC LIMIT 20').fetchall()
        return {'jobs':[{**{k:row[k] for k in ['id','status','created','error']},'mode':json.loads(row['body']).get('mode')} for row in rows]}

    @app.get('/api/local/dashboard')
    def dashboard(peer_id: str | None = None):
        if runtime.role == 'student':
            return runtime.student_dashboard()
        runtime.require_role('teacher')
        return runtime.teacher_dashboard(peer_id) if peer_id else {'peers': runtime.peers(), 'resources': runtime.service.resources()}

    @app.get('/api/local/pages/image')
    def original_page_image(page_id: str | None=None,task_id: str | None=None,revision: int | None=None,peer_id: str | None=None,source_hash: str | None=None):
        import base64
        payload={k:v for k,v in {'page_id':page_id,'task_id':task_id,'revision':revision,'source_hash':source_hash}.items() if v is not None}
        value=runtime.invoke_capability({'contract_version':'companion.capability.v3','request_id':'web-original-page',
            'operation':'page.read','peer_id':peer_id,'payload':payload})['data']
        return Response(base64.b64decode(value['data_base64']),media_type=value['mime'])

    @app.get('/api/local/evidence')
    def evidence(peer_id: str | None = None, task_id: str | None = None):
        return runtime.invoke_capability({'request_id': 'web-evidence', 'operation': 'evidence.read',
                                          'peer_id': peer_id, 'task_id': task_id})

    @app.get('/api/local/capabilities')
    def capabilities():
        return runtime.invoke_capability({'request_id': 'web-architecture', 'operation': 'architecture.describe'})

    @app.post('/api/local/capabilities/invoke')
    async def invoke_capability(req: Request):
        raw=await body(req,3*1024*1024);requested=req.headers.get('x-growth-workspace');actual=getattr(runtime.active(),'workspace_subject','legacy')
        if requested and runtime.enabled() and requested!=actual and not raw.get('operation','').startswith('workspace.'):
            raise ValueError('学科工作区已切换，请刷新页面后继续，未读取或修改其他学科。')
        return runtime.invoke_capability(raw)

    @app.post('/api/local/pair/invite')
    async def invite():
        if not manager:
            raise ValueError('网络服务未启动')
        return await manager.invite()

    @app.put('/api/local/teacher-notes/{peer_id}')
    async def teacher_notes(peer_id: str, req: Request):
        return runtime.save_teacher_notes(peer_id, (await body(req)).get('notes'))

    @app.post('/api/local/pair/join')
    async def join(req: Request):
        if not manager:
            raise ValueError('网络服务未启动')
        return await manager.join((await body(req)).get('code'))

    @app.post('/api/local/pair/{peer_id}/revoke')
    def revoke(peer_id: str):
        return runtime.unpair(peer_id)

    @app.post('/api/local/tasks')
    async def start(req: Request):
        d = await body(req)
        if runtime.role == 'student':
            if d.get('resource_id'):
                return runtime.start_model_practice(d['resource_id'], d['request_key'])
            return runtime.start_self(d['purpose'], d['request_key'])
        return runtime.assign(d['peer_id'], d['purpose'], d['request_key'], d.get('resource_id'))

    @app.get('/api/local/tasks/{id}')
    def get_task(id: str):
        return {**runtime.task(id), 'local_submissions': runtime.pending_submissions(id)}

    @app.get('/api/local/drafts/{id}')
    def get_draft(id: str):
        runtime.require_role('student')
        runtime.task(id)
        return runtime.config('draft:' + id, {})

    @app.put('/api/local/drafts/{id}')
    async def save_draft(id: str, req: Request):
        runtime.require_role('student')
        runtime.task(id)
        runtime.save_config('draft:' + id, await body(req))
        return {'saved_on_this_device': True}

    @app.post('/api/local/tasks/{id}/submit')
    async def submit(id: str, req: Request):
        d = await body(req)
        return runtime.submit(id, d.get('answers', {}), d.get('text', ''), d.get('files', []), d['request_key'],d.get('learning_conditions'))

    @app.post('/api/local/feedback/{id}')
    async def feedback(id: str, req: Request):
        d = await body(req)
        return runtime.feedback(id, d.get('comment'), d.get('next_step'), d.get('judgement') or None, d.get('scores'), d['request_key'])

    @app.post('/api/local/tasks/{id}/state')
    async def task_state(id: str, req: Request):
        return runtime.set_task_state(id, (await body(req)).get('state'))

    @app.post('/api/local/goals')
    async def goal(req: Request):
        runtime.require_role('student')
        d = await body(req)
        return runtime.service.save_goal(runtime.profile['learner_id'], d.get('target'), d.get('url', ''))

    @app.post('/api/local/uploads')
    async def upload(file: UploadFile = File(...)):
        runtime.require_role('student')
        return runtime.service.save_file(runtime.profile['learner_id'], file.filename, file.content_type, await file.read(12*1024*1024+1))

    @app.get('/api/local/files/{id}')
    def file(id: str):
        f = runtime.service.file(id)
        if runtime.role == 'student' and f['learner_id'] != runtime.profile['learner_id']:
            raise PermissionError('附件不属于本机学生')
        if runtime.role == 'teacher' and not any(p['learner_id'] == f['learner_id'] for p in runtime.peers()):
            raise PermissionError('附件不属于本机收到的作业')
        return FileResponse(f['path'], media_type=f['mime'], filename=f['name'])

    @app.get('/api/local/audio/{task_id}')
    def audio(task_id: str):
        task = runtime.task(task_id)
        digest = task['pack'].get('audio')
        if not digest or not isinstance(digest, str) or len(digest) != 64:
            raise KeyError('任务没有音频')
        path = runtime.folder/'peer-media'/digest
        if not path.is_file():
            resource = next((p for p in runtime.service.resources() if p.get('audio') == digest), None)
            path = Path(resource['media_path']) if resource else path
        if not path.is_file() or not path.resolve().is_relative_to(runtime.folder) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('录音尚未同步完成，或文件校验失败')
        header=path.read_bytes()[:12]
        return FileResponse(path, media_type='audio/ogg' if header[:4]==b'OggS' else 'audio/wav' if header[:4]==b'RIFF' and header[8:12]==b'WAVE' else 'audio/mpeg')

    @app.post('/api/local/academic/media')
    async def academic_media(file: UploadFile=File(...),source: str=Form(...),speech_origin: str=Form('unverified')):
        import base64
        data=await file.read(12*1024*1024+1)
        return runtime.invoke_capability({'contract_version':'companion.capability.v7','request_id':secrets.token_hex(16),'operation':'k12.media.save',
            'payload':{'name':file.filename,'source':source,'speech_origin':speech_origin,'mime':'audio/wav' if file.content_type in ['audio/x-wav','audio/wave'] else file.content_type,'data_base64':base64.b64encode(data).decode()}})['data']

    @app.get('/api/local/academic/audio/{id}')
    def academic_audio(id: str):
        a=runtime.invoke_capability({'contract_version':'companion.capability.v7','request_id':secrets.token_hex(16),'operation':'k12.media.read','payload':{'id':id}})['data']['record']
        return FileResponse(runtime.folder/'peer-media'/a['sha256'],media_type=a['mime'])

    @app.get('/api/local/resources')
    def resources():
        if runtime.role == 'teacher':
            return {'packs': runtime.service.resources()}
        runtime.require_role('student')
        return {'packs': [{'id': p['id'], 'title': p['title'], 'status': p['status']} for p in runtime.service.resources() if p.get('source', {}).get('kind') == 'model_original_draft']}

    @app.get('/api/local/resources/{id}/audio')
    def preview_audio(id: str):
        runtime.require_role('teacher')
        pack = next((p for p in runtime.service.resources() if p['id'] == id), None)
        if not pack or not pack.get('media_path'):
            raise KeyError('录音不存在')
        path = Path(pack['media_path'])
        if not path.resolve().is_relative_to(runtime.folder/'media') or hashlib.sha256(path.read_bytes()).hexdigest() != pack['audio_sha256']:
            raise ValueError('录音校验失败，请重新导入')
        return FileResponse(path, media_type='audio/ogg' if path.suffix == '.ogg' else 'audio/mpeg')

    @app.post('/api/local/resources/{id}/review')
    async def review(id: str, req: Request):
        runtime.require_role('teacher')
        d = await body(req)
        return runtime.service.review_pack(id, runtime.profile['name'], d.get('note'), d.get('audio_listened') is True, d.get('content_checked') is True)

    @app.post('/api/local/resources/import')
    async def import_resources(file: UploadFile = File(...)):
        runtime.require_role('teacher')
        raw = await file.read(80*1024*1024+1)
        if len(raw) > 80*1024*1024:
            raise ValueError('资源包最多80MB')
        try:
            bundle = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            raise ValueError('请选择本地版资源ZIP包') from None
        with bundle:
            names = bundle.namelist()
            if len(names) > 1000 or sum(x.file_size for x in bundle.infolist()) > 100*1024*1024 or any('..' in Path(n).parts or n.startswith(('/', '\\')) or ':' in n for n in names):
                raise ValueError('资源包路径或解压大小无效')
            packs = json.loads(bundle.read('resources.json'))
            if not isinstance(packs, list) or len(packs) > 300:
                raise ValueError('资源清单无效')
            media = runtime.folder/'media'
            media.mkdir(exist_ok=True)
            for pack in packs:
                if pack.get('audio'):
                    name = Path(pack['media_path'].replace('\\', '/')).name
                    data = bundle.read('media/'+name)
                    if len(data) > 12*1024*1024 or hashlib.sha256(data).hexdigest() != pack['audio_sha256']:
                        raise ValueError('音频哈希或大小无效')
                    path = media/name
                    path.write_bytes(data)
                    pack['media_path'] = str(path.resolve())
                runtime.service.validate_pack(pack)
            for pack in packs:
                runtime.service.import_pack(pack)
        return {'imported': len(packs), 'status': 'pending_review'}

    @app.get('/api/local/mcp-config')
    def mcp_config():
        import sys
        if getattr(sys, 'frozen', False):
            command = str(Path(sys.executable).with_name('HyperGrowthMCP.exe'))
            args = ['--data', str(runtime.root.folder)]
        else:
            command, args = sys.executable, ['-m', 'growth_local.mcp']
        return {'mcpServers': {'hyper-growth-local': {'command': command, 'args': args, 'env': {'HYPER_GROWTH_DATA': str(runtime.root.folder), 'PYTHONPATH': str(Path(__file__).parents[1]), 'PYTHONUTF8': '1'}}}}

    @app.post('/api/local/exit')
    async def exit_app():
        callback = getattr(app.state, 'shutdown', None)
        if not callback:
            raise ValueError('请在运行服务的终端中停止本机程序')
        async def later():
            await asyncio.sleep(.3)
            callback()
        asyncio.create_task(later())
        return {'stopping': True, 'pending_messages_preserved': True}

    @app.post('/api/local/backup/export')
    async def backup_export(req: Request):
        from base.app.local_backup import export_backup
        from starlette.concurrency import run_in_threadpool
        raw = await run_in_threadpool(export_backup, runtime, (await body(req)).get('password'))
        return Response(raw,media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="hyper-growth-recovery.hgb"'})

    @app.post('/api/local/backup/restore')
    async def backup_restore(file: UploadFile=File(...),password: str=Form(...)):
        from base.app.local_backup import restore_backup
        from starlette.concurrency import run_in_threadpool
        result=await run_in_threadpool(restore_backup,runtime,await file.read(85*1024*1024+1),password)
        callback=getattr(app.state,'shutdown',None)
        if callback:
            async def later():
                await asyncio.sleep(1)
                callback()
            asyncio.create_task(later())
        return result

    app.mount('/mcp', mcp.streamable_http_app())
    app.mount('/assets', StaticFiles(directory=STATIC), name='local-assets')
    app.mount('/base-assets', StaticFiles(directory=BASE_STATIC), name='base-assets')

    @app.get('/')
    def home():
        return FileResponse(STATIC/'index.html')
    return app

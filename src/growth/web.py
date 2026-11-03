import hashlib, hmac, json, os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from base.app.growth import GrowthService
from growth.mcp_server import create_mcp
from base.app.provider import model_status, generate_draft

STATIC = Path(__file__).parent / "static"


def create_app(data=None):
    service = GrowthService(data or os.environ.get("BASE_DATA", "data/growth"))
    mcp = create_mcp(service)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="超维伴学", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.service = service

    def teacher(req, learner_id=None):
        service.base.authorize(
            req.headers.get("x-owner-token")
            or req.headers.get("authorization", "").removeprefix("Bearer ")
        )
        if learner_id: service.require_paired(learner_id)

    def learner(req, id=None):
        return service.authorize(
            req.headers.get("authorization", "").removeprefix("Bearer "), id
        )

    async def body(req):
        raw = await req.body()
        if len(raw) > 512 * 1024:
            raise ValueError("请求内容过大")
        try:
            data = json.loads(raw)
        except ValueError:
            raise ValueError("请求不是有效JSON") from None
        if not isinstance(data, dict):
            raise ValueError("请求必须是对象")
        return data

    @app.middleware("http")
    async def protect(req, call_next):
        if req.method not in ["GET", "HEAD", "OPTIONS"]:
            origin = req.headers.get("origin")
            if origin and origin != str(req.base_url).rstrip("/"):
                return JSONResponse({"error": "请求来源不匹配"}, 403)
            try:
                length = int(req.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"error": "无效请求长度"}, 400)
            if length > 13 * 1024 * 1024:
                return JSONResponse({"error": "文件过大，最多12MB"}, 413)
        if req.url.path == "/mcp" or req.url.path.startswith("/mcp/"):
            auth = req.headers.get("authorization", "").removeprefix("Bearer ")
            if not auth or not hmac.compare_digest(auth, service.base.owner_token):
                return JSONResponse({"error": "MCP需要教师访问凭据"}, 401)
        response = await call_next(req)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    for exc, code in [(ValueError, 400), (KeyError, 404), (PermissionError, 403)]:

        async def handler(req, error, status=code):
            return JSONResponse({"error": str(error).strip("'")}, status)

        app.add_exception_handler(exc, handler)

    @app.get("/api/health")
    def health():
        return {
            "ok": True,
            "version": "0.2.0",
            "product": "超维伴学",
            "transports": ["web", "mcp-stdio", "mcp-streamable-http"],
        }

    @app.get("/api/catalog")
    def catalog():
        return service.catalog()

    @app.post("/api/enroll")
    async def enroll(req: Request):
        d = await body(req)
        return service.create_learner(
            d.get("name"),
            d.get("exam", "ielts"),
            d.get("stage", "application"),
            d.get("goal", ""),
            demo=d.get("demo") is True,
            request_key=d.get("request_key"),
            paired=False,
        )

    @app.post('/api/pairing/redeem')
    async def redeem_pairing(req: Request):
        d=await body(req)
        token=req.headers.get('authorization','').removeprefix('Bearer ')
        subject=service.authorize(token) if token else None
        client=req.client.host if req.client else 'unknown'
        service.pair_rate_limit(client)
        try:
            return service.redeem_pair_code(d.get('code'),subject)
        except ValueError:
            service.pair_rate_limit(client,failure=True)
            raise

    @app.post('/api/pairing/leave')
    def leave_pairing(req: Request):
        return service.unpair(learner(req))

    @app.post('/api/teacher/profile')
    async def teacher_profile(req: Request):
        teacher(req)
        return service.teacher_profile((await body(req)).get('name'))

    @app.post('/api/teacher/pair-codes')
    async def create_pair_code(req: Request):
        teacher(req)
        return service.create_pair_code((await body(req)).get('learner_id'))

    @app.post('/api/teacher/pair-codes/{id}/revoke')
    def revoke_pair_code(id: str, req: Request):
        teacher(req)
        return service.revoke_pair_code(id)

    @app.post('/api/teacher/students/{id}/unpair')
    def unpair_student(id: str, req: Request):
        teacher(req,id)
        return service.unpair(id)

    @app.get("/api/me")
    def me(req: Request):
        return service.dashboard(learner(req))

    @app.post("/api/activities")
    async def start(req: Request):
        id = learner(req)
        d = await body(req)
        return service.start(
            id, d.get("purpose"), d.get("request_key"), d.get("resource_id")
        )

    @app.get("/api/activities/{id}")
    def activity(id: str, req: Request):
        s = service.session(id)
        learner(req, s["learner_id"])
        return s

    @app.post("/api/activities/{id}/submit")
    async def submit(id: str, req: Request):
        s = service.session(id)
        learner(req, s["learner_id"])
        d = await body(req)
        return service.submit(
            id,
            d.get("answers"),
            d.get("text", ""),
            d.get("files"),
            d.get("request_key", ""),
            d.get("independent") is True,
        )

    @app.post("/api/goals")
    async def goal(req: Request):
        id = learner(req)
        d = await body(req)
        return service.save_goal(id, d.get("target"), d.get("url", ""), d.get("gaps"))

    @app.post("/api/uploads")
    async def upload(req: Request, file: UploadFile = File(...)):
        id = learner(req)
        data = await file.read(12 * 1024 * 1024 + 1)
        return service.save_file(id, file.filename, file.content_type, data)

    @app.get("/api/files/{id}")
    def attachment(id: str, req: Request):
        f = service.file(id)
        if req.headers.get("x-owner-token"):
            teacher(req, f['learner_id'])
        else:
            learner(req, f["learner_id"])
        return FileResponse(
            f["path"],
            media_type=f["mime"],
            filename=f["name"],
            content_disposition_type="attachment",
        )

    @app.get("/api/audio/{id}")
    def audio(id: str, req: Request):
        owner = bool(req.headers.get("x-owner-token"))
        if owner:
            teacher(req)
        else:
            subject = learner(req)
        packs = [p for p in service.resources() if p.get("audio") == id]
        if not packs:
            raise KeyError("录音不存在")
        # A student may play a pending source only within an explicitly marked demonstration profile.
        if (
            not owner
            and not any(p["status"] == "ready" for p in packs)
            and not service.person(subject)["demo"]
        ):
            raise PermissionError("录音还在教师试听审核中")
        paths = {p.get("media_path") for p in packs}
        path = next((Path(p) for p in paths if p and Path(p).is_file()), None)
        if path is None:
            raise KeyError("本机还没有导入这个录音文件，请教师查看资源导入说明")
        if not path.resolve().is_relative_to((service.folder / "media").resolve()):
            raise PermissionError("录音路径不在本实例资源目录")
        if hashlib.sha256(path.read_bytes()).hexdigest() != packs[0].get(
            "audio_sha256"
        ):
            raise ValueError("录音内容已改变，请教师重新导入并审核")
        return FileResponse(
            path,
            media_type={
                ".ogg": "audio/ogg",
                ".m4a": "audio/mp4",
                ".wav": "audio/wav",
            }.get(path.suffix.lower(), "audio/mpeg"),
        )

    @app.get("/api/teacher")
    def overview(req: Request):
        teacher(req)
        return service.teacher_overview()

    @app.post("/api/teacher/students")
    async def new_student(req: Request):
        teacher(req)
        d = await body(req)
        return service.create_learner(
            d.get("name"),
            d.get("exam"),
            d.get("stage"),
            d.get("goal", ""),
            request_key=d.get("request_key"),
        )

    @app.post("/api/teacher/students/{id}")
    async def update_student(id: str, req: Request):
        teacher(req,id)
        d = await body(req)
        return service.update_person(
            id,
            d.get("name"),
            d.get("goal", ""),
            d.get("exam"),
            d.get("stage"),
            d.get("notes", ""),
        )

    @app.post("/api/teacher/students/{id}/link")
    def student_link(id: str, req: Request):
        teacher(req,id)
        return service.issue_link(id)

    @app.post("/api/teacher/assign")
    async def assign(req: Request):
        teacher(req)
        d = await body(req)
        service.require_paired(d.get('learner_id'))
        return service.start(
            d.get("learner_id"),
            d.get("purpose"),
            d.get("request_key"),
            d.get("resource_id"),
        )

    @app.post("/api/teacher/feedback/{id}")
    async def feedback(id: str, req: Request):
        teacher(req)
        d = await body(req)
        return service.feedback(
            id,
            d.get("comment"),
            d.get("next_step"),
            d.get("judgement"),
            d.get("scores"),
            d.get("request_key"),
        )

    @app.post("/api/teacher/state/{id}")
    async def state(id: str, req: Request):
        teacher(req)
        service.require_task_pair(id)
        d = await body(req)
        return service.base.set_state(id, d.get("state"))

    @app.post("/api/teacher/transfer/{id}")
    async def transfer(id: str, req: Request):
        teacher(req)
        service.require_submission_pair(id)
        d = await body(req)
        return service.base.verify_transfer(id, d.get("context"), d.get("independent"))

    @app.post("/api/teacher/packs")
    async def draft_pack(req: Request):
        teacher(req)
        return service.import_pack(await body(req))

    @app.get("/api/teacher/model")
    def model_info(req: Request):
        teacher(req)
        return model_status()

    @app.post("/api/teacher/generate")
    async def generate(req: Request):
        teacher(req)
        d = await body(req)
        service.require_paired(d.get('learner_id'))
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(generate_draft, service, d.get("learner_id"))

    @app.post("/api/teacher/packs/{id}/review")
    async def review(id: str, req: Request):
        teacher(req)
        d = await body(req)
        return service.review_pack(
            id,
            d.get("reviewer"),
            d.get("note"),
            d.get("audio_listened") is True,
            d.get("content_checked") is True,
        )

    app.mount("/mcp", mcp_app)
    app.mount("/assets", StaticFiles(directory=STATIC), name="assets")

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html")

    return app

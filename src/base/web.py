"""Single local web service; both browser roles use the shared Store."""
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from base.core import Store


def create_app(data=None):
    store = Store(data or os.environ.get('BASE_DATA', 'data/base'))
    secret_file = store.folder / 'owner-token.txt'
    secret_file.write_text(store.owner_token, encoding='utf-8')
    secret_file.chmod(0o600)
    app = FastAPI(docs_url=None, redoc_url=None)
    app.state.store = store

    @app.middleware('http')
    async def protect(request, call_next):
        if request.method not in ('GET', 'HEAD'):
            origin = request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'error': '请求来源不匹配'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.exception_handler(ValueError)
    async def bad_value(request, error):
        return JSONResponse({'error': str(error)}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing(request, error):
        return JSONResponse({'error': str(error)}, status_code=404)

    @app.exception_handler(PermissionError)
    async def denied(request, error):
        return JSONResponse({'error': str(error)}, status_code=403)

    def owner(request):
        store.authorize(request.cookies.get('base_owner'))

    async def payload(request):
        try:
            body = await request.json()
        except ValueError:
            raise ValueError('请求内容须为有效JSON对象') from None
        if not isinstance(body, dict):
            raise ValueError('请求内容必须是一个对象')
        return body

    @app.get('/healthz')
    def health():
        return {'ok': True, 'version': '0.3.2'}

    @app.get('/', response_class=HTMLResponse)
    @app.get('/learn/{token}', response_class=HTMLResponse)
    def page():
        return Path(__file__).with_name('page.html').read_text(encoding='utf-8')

    @app.post('/api/login')
    async def login(request: Request):
        body = await payload(request)
        store.authorize(body.get('token'))
        response = JSONResponse({'ok': True})
        response.set_cookie('base_owner', store.owner_token, httponly=True, samesite='strict')
        return response

    @app.post('/api/logout')
    def logout():
        response = JSONResponse({'ok': True})
        response.delete_cookie('base_owner')
        return response

    @app.get('/api/manage')
    def manage(request: Request):
        owner(request)
        from base.app.activities import prepare_activity
        from base.app.profile import LearningProfile
        from base.teaching import teaching_rules, check_activity
        preview = prepare_activity()
        return {'preview': preview, 'profile_schema': LearningProfile.model_json_schema(), 'teaching': teaching_rules(), 'check': check_activity(preview), 'instance_id': store.instance_id, 'learners': store.learners(), 'tasks': store.tasks(), 'submissions': store.submissions()}

    @app.post('/api/tasks')
    async def create(request: Request):
        owner(request)
        body = await payload(request)
        return store.create(body.get('learner'), body.get('draft'), body.get('request_key'), body.get('learner_id'))

    @app.post('/api/learners')
    async def save_learner(request: Request):
        owner(request)
        body = await payload(request)
        return store.save_learner(body.get('name'), body.get('profile'), body.get('learner_id'), body.get('request_key'))

    @app.get('/api/growth/{learner_id}')
    def growth(learner_id: str, request: Request):
        owner(request)
        return {'growth': store.growth(learner_id), 'plan': store.next_plan(learner_id)}

    @app.post('/api/tasks/{task_id}/state')
    async def state(task_id: str, request: Request):
        owner(request)
        body = await payload(request)
        return store.set_state(task_id, body.get('state'))

    @app.post('/api/transfer/{submission_id}')
    async def transfer(submission_id: str, request: Request):
        owner(request)
        body = await payload(request)
        return store.verify_transfer(submission_id, body.get('context'), body.get('independent'))

    @app.get('/api/learn/{token}')
    def learn(token: str):
        return store.public_task(token)

    @app.post('/api/learn/{token}')
    async def submit(token: str, request: Request):
        body = await payload(request)
        return store.submit(token, body.get('answer'), body.get('request_key'))

    @app.post('/api/feedback/{submission_id}')
    async def feedback(submission_id: str, request: Request):
        owner(request)
        body = await payload(request)
        return store.feedback(submission_id, body.get('comment'), body.get('next_step'), body.get('scores'), body.get('judgement'), body.get('request_key'))

    return app

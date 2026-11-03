"""Local product boundary: one device identity, scoped tools, signed peer events and durable queues."""
import hashlib
import json
import secrets
import time
from pathlib import Path
from uuid import uuid4
from base.core import now
from base.app.growth import GrowthService
from base.app.local_identity import Identity, canonical, b64, unb64


class LocalRuntime:
    def __init__(self, folder, vault=None):
        self.folder = Path(folder).resolve()
        self.identity = Identity(self.folder, vault)
        self.vault = self.identity.vault
        self.service = GrowthService(self.folder)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS local_config(key TEXT PRIMARY KEY,body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_peers(id TEXT PRIMARY KEY,public_key TEXT NOT NULL,role TEXT NOT NULL,name TEXT NOT NULL,learner_id TEXT,state TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_outbox(id TEXT PRIMARY KEY,peer_id TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_inbox(id TEXT PRIMARY KEY,peer_id TEXT NOT NULL,digest TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_task_links(task_id TEXT PRIMARY KEY,peer_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_remote_tasks(id TEXT PRIMARY KEY,peer_id TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_remote_submissions(id TEXT PRIMARY KEY,task_id TEXT NOT NULL,body TEXT NOT NULL,created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_blob_links(peer_id TEXT NOT NULL,client_id TEXT NOT NULL,local_id TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(peer_id,client_id));
                CREATE TABLE IF NOT EXISTS local_jobs(id TEXT PRIMARY KEY,status TEXT NOT NULL,body TEXT NOT NULL,result TEXT,error TEXT,created TEXT NOT NULL);
            ''')
        self.network = None
        self.session_key = None
        self.open_model_keys = {}

    def db(self):
        return self.service.base.db()

    def workspace_child(self,folder,subject):
        child=LocalRuntime(folder,self.vault)
        child.workspace_root=self;child.workspace_subject=subject;child.open_model_keys=self.open_model_keys
        if not child.profile:
            p=self.profile;child.setup(p['role'],p['name'],p.get('exam','ielts'),p.get('stage','application'))
        return child

    def invoke_capability(self, request):
        if not getattr(self,'workspace_subject',None) and (self.config('subject-workspaces-v1') or isinstance(request,dict) and request.get('contract_version')=='companion.capability.v8'):
            from base.app.companion.functional.workspaces import host
            return host(self).invoke_capability(request)
        if getattr(self,'workspace_subject',None):
            from base.app.companion.functional.workspaces import materialize
            from base.app.companion.functional.workspace_lock import lock
            with lock(self.workspace_root.folder):
                materialize(self);result=self._invoke_capability(request);materialize(self);return result
        return self._invoke_capability(request)

    def _invoke_capability(self, request):
        if isinstance(request,dict) and request.get('contract_version')=='companion.capability.v11':
            from base.app.companion.functional.experience import invoke
            return invoke(self,request)
        if isinstance(request,dict) and request.get('contract_version')=='companion.capability.v10':
            from base.app.companion.functional.teaching_workflow import invoke
            return invoke(self,request)
        if isinstance(request,dict) and request.get('contract_version')=='companion.capability.v9':
            from base.app.companion.functional.planning import invoke
            return invoke(self,request)
        if isinstance(request,dict) and request.get('contract_version')=='companion.capability.v7':
            from base.app.companion.functional.academic import invoke
            return invoke(self,request)
        if isinstance(request,dict) and request.get('contract_version')=='companion.capability.v6':
            from base.app.companion.functional.review_service import invoke
            return invoke(self,request)
        """The shared three-layer facade; transports cannot supply a trusted actor scope."""
        if isinstance(request,dict) and request.get('contract_version')=='companion.capability.v5':
            from base.app.companion.functional.evolution import invoke
        elif isinstance(request,dict) and request.get('contract_version')=='companion.capability.v4':
            from base.app.companion.functional.retrieval_service import invoke
        elif isinstance(request,dict) and request.get('contract_version')=='companion.capability.v3':
            from base.app.companion.functional.continuity import invoke
        elif isinstance(request,dict) and request.get('contract_version')=='companion.capability.v2':
            from base.app.companion.functional.study import invoke
        else:
            from base.app.companion.functional.service import invoke
        return invoke(self, request)

    def config(self, key, default=None):
        if getattr(self,'workspace_root',None) and (key in ['model','network','learning-experience-v1'] or key.startswith('peer-planning:')):return self.workspace_root.config(key,default)
        with self.db() as db:
            row = db.execute('SELECT body FROM local_config WHERE key=?', (key,)).fetchone()
        return json.loads(row['body']) if row else default

    def save_config(self, key, value):
        if getattr(self,'workspace_root',None) and key in ['model','network','learning-experience-v1']:return self.workspace_root.save_config(key,value)
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO local_config VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))

    @property
    def profile(self):
        return self.config('profile', {})

    @property
    def role(self):
        return self.profile.get('role')

    def require_role(self, role):
        if self.role != role:
            raise PermissionError('此操作只对' + ('教师' if role == 'teacher' else '学生') + '本机身份开放')

    def setup(self, role, name, exam='ielts', stage='application'):
        if self.profile:
            raise ValueError('本机身份已设置。升级不会重置身份；教师和学生使用各自的安装与数据目录。')
        if role not in ['teacher', 'student'] or not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('请选择身份并填写1—80字称呼')
        profile = {'role': role, 'name': name.strip(), 'exam': exam, 'stage': stage}
        if role == 'student':
            profile['learner_id'] = self.service.create_learner(name.strip(), exam, stage, request_key='local-device-profile', paired=True)['person']['id']
        else:
            self.service.teacher_profile(name.strip())
        self.save_config('profile', profile)
        return self.status()

    def hello(self):
        result = {'id': self.identity.id, 'public_key': self.identity.public_key, 'role': self.role, 'name': self.profile.get('name')}
        result['workspace_protocol']='subject-workspaces.v1'
        result['planning_protocol']='growth-planning.v1'
        if self.role == 'student':
            p = self.service.public_person(self.profile['learner_id'])
            result['student'] = {k: p[k] for k in ['name', 'exam', 'stage']}
        return result

    def _local_peers(self):
        with self.db() as db:
            rows = db.execute('SELECT * FROM local_peers ORDER BY created,id').fetchall()
        return [dict(row) for row in rows]

    def peers(self):
        rows=self._local_peers()
        if getattr(self,'workspace_root',None):
            state={p['id']:p['state'] for p in self.workspace_root.peers()}
            rows=[{**p,'state':state.get(p['id'],'revoked')} for p in rows]
        return rows

    def peer(self, peer_id, active=True):
        peer = next((p for p in self.peers() if p['id'] == peer_id), None)
        if not peer or (active and peer['state'] != 'active'):
            raise PermissionError('设备未配对或配对已解除')
        return peer

    def accept_peer(self, hello, secret):
        public_key = hello.get('public_key', '')
        try:
            assert hashlib.sha256(unb64(public_key)).hexdigest() == hello['id']
            assert hello['role'] in ['teacher', 'student'] and hello['role'] != self.role
            assert isinstance(hello['name'], str) and 0 < len(hello['name']) <= 80
        except Exception:
            raise PermissionError('配对设备身份无效') from None
        existing = next((p for p in self.peers() if p['id'] == hello['id']), None)
        if existing and existing['public_key'] != public_key:
            raise PermissionError('配对公钥发生变化，拒绝替换身份')
        learner_id = existing['learner_id'] if existing else None
        if self.role == 'teacher' and learner_id is None:
            p = hello.get('student', {})
            learner_id = self.service.create_learner(p.get('name'), p.get('exam'), p.get('stage'), request_key='peer:' + hello['id'])['person']['id']
        self.vault.set('peer:' + hello['id'], secret)
        self.save_config('peer-workspace:'+hello['id'],hello.get('workspace_protocol'))
        self.save_config('peer-planning:'+hello['id'],hello.get('planning_protocol'))
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO local_peers VALUES (?,?,?,?,?,?,?)', (hello['id'], public_key, hello['role'], hello['name'], learner_id, 'active', existing['created'] if existing else now()))
        return self.peer(hello['id'])

    def status(self):
        from base.app.companion.functional.experience import describe
        with self.db() as db:
            pending = db.execute("SELECT COUNT(*) FROM local_outbox WHERE status!='acknowledged'").fetchone()[0]
            # Includes writes made by an independent stdio MCP process, not only this UI process.
            counts = [db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ['tasks','submissions','reviews','events','hd_audits','local_inbox','local_jobs','local_remote_submissions']]
            jobs = db.execute('SELECT id,status FROM local_jobs ORDER BY id').fetchall()
        revision = hashlib.sha256(canonical({'counts': counts, 'jobs': [list(r) for r in jobs]})).hexdigest()[:16]
        return {'version': '0.3.0-local', 'revision': revision, 'device_id': self.identity.id, 'profile': self.profile, 'experience':describe(self), 'data_folder': str(self.folder), 'model': self.model_status(), 'peers': self.peers(), 'pending_messages': pending, 'network': self.network.status() if self.network else {'running': False}, 'storage': 'this_device', 'cloud_model_fallback': False}

    def model_status(self):
        settings = self.config('model', {})
        return {**settings, 'key_present': bool(self.model_key()), 'configured': bool(settings and self.model_key())}

    def model_key(self):
        return self.open_model_keys.get('api') or self.vault.get('api')

    def save_model(self, settings, key=None, remember=True):
        provider = settings.get('provider', 'deepseek')
        url = settings.get('base_url', '').rstrip('/')
        model = settings.get('model', '').strip()
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if provider not in ['deepseek', 'compatible'] or not model or len(model) > 160 or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('模型配置无效；地址中不要包含密钥或账号密码')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ['127.0.0.1', 'localhost', '::1']):
            raise ValueError('远程模型接口须使用HTTPS；本机模型可使用localhost HTTP')
        if not parsed.hostname or len(url) > 500 or (key is not None and (not isinstance(key, str) or not 1 <= len(key.strip()) <= 1000)):
            raise ValueError('请填写有效接口地址和API Key')
        vision=settings.get('vision_model','')
        if not isinstance(vision,str) or len(vision)>160:raise ValueError('视觉模型名称无效')
        if key is not None:
            if remember:
                self.vault.set('api', key.strip())
                self.open_model_keys.pop('api', None)
            else:
                self.vault.delete('api')
                self.open_model_keys['api'] = key.strip()
        elif not remember and self.vault.get('api'):
            self.open_model_keys['api'] = self.vault.get('api')
            self.vault.delete('api')
        elif remember and self.open_model_keys.get('api'):
            self.vault.set('api', self.open_model_keys.pop('api'))
        self.save_config('model', {'provider': provider, 'base_url': url, 'model': model, 'remember': bool(remember),'vision_model':vision.strip()})
        return self.model_status()

    def delete_model_key(self):
        self.vault.delete('api')
        self.open_model_keys.clear()
        return self.model_status()

    def queue(self, peer_id, kind, payload, event_id=None):
        self.peer(peer_id)
        if getattr(self,'workspace_subject',None):
            if self.workspace_root.config('peer-workspace:'+peer_id)!='subject-workspaces.v1':
                raise ValueError('对方尚未确认支持独立学科工作区；请双方升级并重新连接，任务未发往旧版设备')
            state=self.workspace_root.config('subject-workspaces-v1')
            payload={**payload,'subject_workspace':{'id':self.workspace_subject,'name':state['subjects'][self.workspace_subject]['name']}}
        event_id = event_id or uuid4().hex
        envelope = self.identity.envelope(peer_id, kind, payload, event_id)
        raw = canonical(envelope).decode()
        if len(raw.encode()) > 20 * 1024 * 1024:
            raise ValueError('本次同步内容过大，请将附件分次提交')
        with self.db() as db:
            prior = db.execute('SELECT body FROM local_outbox WHERE id=?', (event_id,)).fetchone()
            if prior and prior['body'] != raw:
                raise ValueError('同步操作标识已用于其他内容')
            db.execute('INSERT OR IGNORE INTO local_outbox VALUES (?,?,?,?,?)', (event_id, peer_id, raw, 'queued', now()))
        return event_id

    def pending(self, peer_id):
        self.peer(peer_id)
        with self.db() as db:
            rows = db.execute("SELECT body FROM local_outbox WHERE peer_id=? AND status!='acknowledged' ORDER BY created LIMIT 10", (peer_id,)).fetchall()
        return [json.loads(r['body']) for r in rows]

    def ack(self, peer_id, event_id):
        with self.db() as db:
            db.execute("UPDATE local_outbox SET status='acknowledged' WHERE id=? AND peer_id=?", (event_id, peer_id))

    def unpair(self, peer_id):
        self.peer(peer_id)
        # Existing received copies remain on the recipient's device. Only future exchange is revoked.
        with self.db() as db:
            db.execute("UPDATE local_peers SET state='revoked' WHERE id=?", (peer_id,))
        return {'revoked': True, 'existing_copies_preserved': True}

    def assign(self, peer_id, purpose, request_key, resource_id=None):
        self.require_role('teacher')
        peer = self.peer(peer_id)
        result = self.service.start(peer['learner_id'], purpose, request_key, resource_id)
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO local_task_links VALUES (?,?)', (result['id'], peer_id))
            if db.execute('SELECT 1 FROM local_outbox WHERE id=?', ('assign-' + result['id'],)).fetchone():
                return result
        payload = {'task': result}
        if result['pack'].get('audio'):
            resource = next(p for p in self.service.resources() if p.get('audio') == result['pack']['audio'])
            path = Path(resource['media_path'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != resource['audio_sha256']:
                raise ValueError('录音已改变，请重新审核后分配')
            payload['audio'] = {'data': b64(path.read_bytes()), 'sha256': resource['audio_sha256'], 'suffix': path.suffix}
        self.queue(peer_id, 'task.assigned', payload, event_id='assign-' + result['id'])
        return result

    def teacher_dashboard(self, peer_id):
        self.require_role('teacher')
        peer = self.peer(peer_id)
        return self.service.dashboard(peer['learner_id'], teacher=True)

    def save_teacher_notes(self, peer_id, notes):
        self.require_role('teacher')
        peer = self.peer(peer_id)
        if not isinstance(notes, str) or len(notes) > 3000:
            raise ValueError('教师备注限3000字')
        with self.db() as db:
            db.execute('UPDATE hd_people SET notes=? WHERE id=?', (notes, peer['learner_id']))
        return {'saved': True, 'scope': 'teacher_device_only'}

    def student_dashboard(self):
        self.require_role('student')
        d = self.service.dashboard(self.profile['learner_id'])
        with self.db() as db:
            rows = db.execute('SELECT body FROM local_remote_tasks ORDER BY created,id').fetchall()
        remote = [json.loads(r['body']) for r in rows]
        d['tasks'] = [{**t, 'origin': 'self'} for t in d['tasks']] + remote
        d['teachers'] = [p for p in self.peers() if p['role'] == 'teacher']
        return d

    def task(self, task_id):
        if self.role == 'student':
            with self.db() as db:
                row = db.execute('SELECT body FROM local_remote_tasks WHERE id=?', (task_id,)).fetchone()
            if row:
                return json.loads(row['body'])
            task = self.service.session(task_id)
            if task['learner_id'] != self.profile['learner_id']:
                raise PermissionError('不能读取其他档案的任务')
            return {**task, 'origin': 'self'}
        self.require_role('teacher')
        task = self.service.session(task_id)
        if not any(p['learner_id'] == task['learner_id'] and p['state'] == 'active' for p in self.peers()):
            raise PermissionError('任务不属于已配对的学生')
        if task['pack'].get('academic'):
            from base.app.companion.functional.academic import task_feedback
            peer=next(p for p in self.peers() if p['learner_id']==task['learner_id'] and p['state']=='active')
            task['academic_feedback']=task_feedback(self,peer['id'],task_id)
        return task

    def start_self(self, purpose, request_key):
        self.require_role('student')
        return self.service.start(self.profile['learner_id'], purpose, request_key)

    def start_model_practice(self, pack_id, request_key):
        self.require_role('student')
        id = self.profile['learner_id']
        dashboard = self.service.dashboard(id)
        if not any(t['purpose'] == 'diagnostic' and t['attempts'] for t in dashboard['tasks']):
            raise ValueError('先完成诊断，再使用针对性的AI自主练习')
        pack = next((p for p in self.service.resources() if p['id'] == pack_id), None)
        if not pack or pack.get('source', {}).get('kind') != 'model_original_draft' or pack['exam'] != dashboard['person']['exam']:
            raise ValueError('未找到本机对应考试的模型草稿')
        pack = {**pack, 'purpose': 'practice', 'review_state': 'AI自主练习，未经教师审校'}
        draft = {'name': '超维成长', 'activity_title': pack['title'], 'instructions': pack['instructions'], 'material': pack['stimulus'], 'goal': '根据诊断错因自主练习', 'deliverable': '逐题作答并对照依据，不作为教师核验结论', 'criteria': 'AI草稿可能有误；自动核对不是教师确认达标', 'next_step': '与老师核对依据后，再用未见材料复测', 'mode': 'text', 'assessment_version': 'local-draft-0.3', 'growth': pack}
        task = self.service.base.create(dashboard['person']['name'], draft, 'local-draft:' + request_key, learner_id=id)
        return self.service.session(task['id'])

    def file_payload(self, file_id):
        self.require_role('student')
        f = self.service.file(file_id)
        if f['learner_id'] != self.profile['learner_id']:
            raise PermissionError('不能同步其他人的附件')
        return {'client_id': file_id, 'name': f['name'], 'mime': f['mime'], 'data': b64(Path(f['path']).read_bytes()), 'sha256': f['sha256']}

    def submit(self, task_id, answers, text, files, request_key, learning_conditions=None,writing_history=None):
        self.require_role('student')
        if learning_conditions is not None:
            from base.app.companion.functional.study_contracts import LearningConditions
            try:learning_conditions=LearningConditions.model_validate(learning_conditions).model_dump()
            except ValueError:raise ValueError('学习条件说明格式无效') from None
        task = self.task(task_id)
        writing_ref=None
        if writing_history is not None:
            from base.app.companion.functional.evolution_sync import capture_history
            writing_ref=capture_history(self,task_id,writing_history,text,self.identity.id,'self')
        if task.get('origin') == 'self':
            return self.service.submit(task_id, answers, text, files, request_key, learning_conditions=learning_conditions,writing_history_ref=writing_ref)
        self.peer(task['peer_id'])
        if task['pack'].get('academic',{}).get('mode')=='target':
            event_id=hashlib.sha256((task_id+':'+request_key).encode()).hexdigest()
            with self.db() as db:
                submitted=db.execute('SELECT id FROM local_remote_submissions WHERE task_id=?',(task_id,)).fetchall()
            if (submitted or task['attempts']) and not any(x['id']==event_id for x in submitted):raise ValueError('目标测验已交卷或等待送达，请保留原答，另用新材料再测')
        if task['state'] != 'active':
            raise ValueError('任务已暂停或归档')
        if not isinstance(text, str) or len(text) > 12000 or not isinstance(answers, dict) or not isinstance(files, list) or len(files) > 5:
            raise ValueError('作答内容无效或附件过多')
        if task['pack']['items'] and any(not str(answers.get(i['id'], '')).strip() for i in task['pack']['items']):
            raise ValueError('请完成全部题目再提交')
        if not task['pack']['items'] and not text.strip() and not files:
            raise ValueError('请提交文字或作品附件')
        payload = {'task_id': task_id, 'answers': answers, 'text': text, 'files': [self.file_payload(f) for f in files], 'request_key': request_key}
        if learning_conditions is not None:payload['learning_conditions']=learning_conditions
        if writing_history is not None:payload['writing_history']=writing_history
        event_id = hashlib.sha256((task_id + ':' + request_key).encode()).hexdigest()
        self.queue(task['peer_id'], 'submission', payload, event_id=event_id)
        with self.db() as db:
            old = db.execute('SELECT body FROM local_remote_submissions WHERE id=?', (event_id,)).fetchone()
            content = json.dumps({'answers': answers, 'text': text, 'files': files, 'delivery': 'queued', 'request_key': request_key}, ensure_ascii=False)
            if learning_conditions is not None:content=json.dumps({**json.loads(content),'learning_conditions':learning_conditions},ensure_ascii=False)
            if writing_ref is not None:content=json.dumps({**json.loads(content),'writing_history_ref':writing_ref},ensure_ascii=False)
            if old and old['body'] != content:
                raise ValueError('提交标识已用于另一份作品')
            db.execute('INSERT OR IGNORE INTO local_remote_submissions VALUES (?,?,?,?)', (event_id, task_id, content, now()))
        return self.task(task_id)

    def pending_submissions(self, task_id):
        with self.db() as db:
            rows = db.execute('SELECT s.*,o.status AS delivery FROM local_remote_submissions s LEFT JOIN local_outbox o ON s.id=o.id WHERE s.task_id=? ORDER BY s.created', (task_id,)).fetchall()
        return [{**dict(r), 'body': json.loads(r['body'])} for r in rows]

    def feedback(self, submission_id, comment, next_step, judgement, scores, request_key):
        self.require_role('teacher')
        learner_id = self.service.require_submission_pair(submission_id)
        peer = next((p for p in self.peers() if p['learner_id'] == learner_id and p['state'] == 'active'), None)
        if not peer:
            raise PermissionError('提交不属于已配对学生')
        if judgement=='meets_criteria':
            with self.db() as db:row=db.execute('SELECT task_id FROM submissions WHERE id=?',(submission_id,)).fetchone()
            task=self.task(row['task_id'])
            if task['pack'].get('companion_plan',{}).get('runtime_policy'):
                raise ValueError('此任务已绑定 Policy Pack，请通过逐项评价能力记录依据后确认达标')
        result = self.service.feedback(submission_id, comment, next_step, judgement, scores, request_key)
        with self.db() as db:
            task_id = db.execute('SELECT task_id FROM submissions WHERE id=?', (submission_id,)).fetchone()['task_id']
        self.queue_task_update(peer['id'], task_id)
        return result

    def set_task_state(self, task_id, state):
        self.require_role('teacher')
        self.task(task_id)
        result = self.service.base.set_state(task_id, state)
        with self.db() as db:
            peer_id = db.execute('SELECT peer_id FROM local_task_links WHERE task_id=?', (task_id,)).fetchone()['peer_id']
        self.queue_task_update(peer_id, task_id)
        return result

    def queue_task_update(self, peer_id, task_id,event_id=None):
        task = self.service.session(task_id)
        from base.app.companion.functional.study_store import ledger
        task['companion_assessments']=[x for x in ledger(self,task_id) if x['source_type']=='teacher_review']
        from base.app.companion.functional.evolution_sync import task_extensions
        task.update(task_extensions(self,peer_id,task_id))
        from base.app.companion.functional.review_service import assistance
        task['companion_review_assistance']=assistance(self,peer_id,task_id)
        if task['pack'].get('academic'):
            from base.app.companion.functional.academic import task_feedback
            task['academic_feedback']=task_feedback(self,peer_id,task_id)
        # Local file IDs are translated back to the student's own attachment IDs.
        with self.db() as db:
            mapping = {r['local_id']: r['client_id'] for r in db.execute('SELECT * FROM local_blob_links WHERE peer_id=?', (peer_id,))}
        for attempt in task['attempts']:
            attempt['answer']['files'] = [mapping.get(f, f) for f in attempt['answer'].get('files', [])]
        self.queue(peer_id, 'task.updated', {'task': task},event_id=event_id)

    def receive(self, envelope):
        if not isinstance(envelope, dict) or len(canonical(envelope)) > 20 * 1024 * 1024:
            raise ValueError('同步消息无效或过大')
        body = envelope['body']
        peer = self.peer(body['sender'])
        if body.get('recipient') != self.identity.id:
            raise PermissionError('消息并非发送给本机')
        Identity.verify(peer['public_key'], body, envelope['signature'])
        event_id = body['id']
        if not isinstance(event_id, str) or len(event_id) > 128:
            raise ValueError('同步消息标识无效')
        digest = hashlib.sha256(canonical(envelope)).hexdigest()
        with self.db() as db:
            previous = db.execute('SELECT digest FROM local_inbox WHERE id=?', (event_id,)).fetchone()
        if previous:
            if previous['digest'] != digest:
                raise PermissionError('同步消息标识冲突')
            return {'received': event_id, 'duplicate': True}
        kind, payload = body['kind'], body['payload']
        if kind == 'ack':
            self.ack(peer['id'], payload['id'])
        elif kind == 'growth.plan':
            from base.app.companion.functional.planning import receive
            receive(self,peer,payload)
        elif kind in ['task.assigned', 'task.updated']:
            self.require_role('student')
            if peer['role'] != 'teacher':
                raise PermissionError('只有已配对老师可以发布任务或评阅')
            task = payload['task']
            if not isinstance(task.get('pack'), dict) or not isinstance(task.get('attempts'), list) or task.get('state') not in ['active', 'paused', 'archived']:
                raise ValueError('任务数据无效')
            with self.db() as db:
                old = db.execute('SELECT peer_id FROM local_remote_tasks WHERE id=?', (task['id'],)).fetchone()
                own = db.execute('SELECT 1 FROM tasks WHERE id=?', (task['id'],)).fetchone()
            if own:
                raise PermissionError('远程任务不能替换本机自主任务')
            if old and old['peer_id'] != peer['id']:
                raise PermissionError('不能替换另一位老师的任务')
            if task['pack'].get('source_page'):
                from base.app.companion.assets.pages import decode_original
                source_page=task['pack']['source_page']
                _,metadata=decode_original(source_page.get('data_base64',''))
                if metadata['source_hash']!=source_page.get('source_hash') or metadata['mime']!=source_page.get('mime'):
                    raise ValueError('配对任务的原图校验失败')
            task = {**task, 'origin': 'teacher', 'peer_id': peer['id'], 'teacher_name': peer['name'], 'signature_verified': True}
            from base.app.companion.functional.evolution_sync import accept_extensions
            accept_extensions(self,peer['id'],task,event_id)
            from base.app.companion.assets.review import validate_assistance
            validate_assistance(task)
            from base.app.companion.assets.academic import verify_task
            verify_task(task)
            from base.app.companion.assets.teaching_workflow import verify_blueprint
            verify_blueprint(task['pack'])
            if payload.get('audio'):
                audio = payload['audio']
                data = unb64(audio['data'])
                if len(data) > 12 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != audio['sha256']:
                    raise ValueError('录音哈希不匹配')
                folder = self.folder / 'peer-media'
                folder.mkdir(exist_ok=True)
                (folder / audio['sha256']).write_bytes(data)
            with self.db() as db:
                db.execute('INSERT OR REPLACE INTO local_remote_tasks VALUES (?,?,?,?)', (task['id'], peer['id'], json.dumps(task, ensure_ascii=False), task['created']))
        elif kind == 'submission':
            self.require_role('teacher')
            with self.db() as db:
                link = db.execute('SELECT peer_id FROM local_task_links WHERE task_id=?', (payload['task_id'],)).fetchone()
            if peer['role'] != 'student' or not link or link['peer_id'] != peer['id']:
                raise PermissionError('学生不能提交其他人的任务')
            files = []
            for blob in payload.get('files', []):
                data = unb64(blob['data'])
                if hashlib.sha256(data).hexdigest() != blob['sha256']:
                    raise ValueError('附件哈希不匹配')
                with self.db() as db:
                    old = db.execute('SELECT * FROM local_blob_links WHERE peer_id=? AND client_id=?', (peer['id'], blob['client_id'])).fetchone()
                if old:
                    if old['sha256'] != blob['sha256']:
                        raise ValueError('附件标识被重复用于不同内容')
                    files.append(old['local_id'])
                else:
                    saved = self.service.save_file(peer['learner_id'], blob['name'], blob['mime'], data)
                    files.append(saved['id'])
                    with self.db() as db:
                        db.execute('INSERT INTO local_blob_links VALUES (?,?,?,?)', (peer['id'], blob['client_id'], saved['id'], blob['sha256']))
            writing_ref=None
            if payload.get('writing_history') is not None:
                from base.app.companion.functional.evolution_sync import capture_history
                writing_ref=capture_history(self,payload['task_id'],payload['writing_history'],payload.get('text',''),peer['id'],'peer:'+peer['id'])
            received=self.service.submit(payload['task_id'], payload.get('answers'), payload.get('text', ''), files, 'peer:' + payload['request_key'],learning_conditions=payload.get('learning_conditions'),writing_history_ref=writing_ref)
            self.queue_task_update(peer['id'], payload['task_id'])
            from base.app.companion.functional.review_service import on_received
            on_received(self,received,peer['id'])
        else:
            raise PermissionError('不接受此类跨设备操作；模型配置和教师备注不能同步')
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO local_inbox VALUES (?,?,?,?,?)', (event_id, peer['id'], digest, json.dumps(envelope, ensure_ascii=False), now()))
        return {'received': event_id, 'duplicate': False}

    def create_job(self, payload):
        job_id = uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO local_jobs VALUES (?,?,?,?,?,?)', (job_id, 'queued', json.dumps(payload, ensure_ascii=False), None, None, now()))
        return job_id

    def job(self, job_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM local_jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise KeyError('任务不存在')
        return {**dict(row), 'body': json.loads(row['body']), 'result': json.loads(row['result']) if row['result'] else None}

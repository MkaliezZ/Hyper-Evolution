"""Shared device/transport, independent subject databases and original files.

The legacy database remains intact. Only explicitly classified sources are copied;
unassigned teaching history stays in its visibly separate legacy workspace.
"""
import copy,json,hashlib
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from base.app.local_identity import Identity,canonical
from base.app.companion.assets.references import digest
from base.app.companion.assets.workspaces import subject_path,text_path,check_text
from base.app.companion.functional import study_store,academic_store
from base.app.companion.functional.workspace_contracts import WorkspaceRequest,WorkspaceResult,PAYLOADS
from base.app.companion.functional.workspace_lock import serialized,lock

KEY='subject-workspaces-v1'
BOUND=ContextVar('growth_subject_workspace',default=None)

def host(runtime):
    if isinstance(runtime,WorkspaceHost):return runtime
    root=getattr(runtime,'workspace_root',runtime)
    if not hasattr(root,'_workspace_host'):root._workspace_host=WorkspaceHost(root)
    return root._workspace_host

def materialize(runtime):
    """Write one immutable TXT and metadata file for every local text version."""
    if not getattr(runtime,'workspace_subject',None):return
    with lock(runtime.workspace_root.folder):return _materialize(runtime)

def _materialize(runtime):
    study_store.initialize(runtime)
    with runtime.db() as db:rows=db.execute('SELECT body FROM companion_materials').fetchall()
    for row in rows:
        value=json.loads(row['body']);path=text_path(runtime.folder,value);path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():check_text(value,path.read_bytes())
        else:
            with path.open('xb') as file:file.write(value['text'].encode('utf-8'))
        meta=path.with_suffix('.json')
        body={k:v for k,v in value.items() if k!='text'}
        if not meta.exists():
            with meta.open('xb') as file:file.write(canonical(body))

class WorkspaceHost:
    def __init__(self,root):
        object.__setattr__(self,'root',root);object.__setattr__(self,'children',{})

    def __getattr__(self,name):
        if name in ['identity','vault','network','session_key','open_model_keys','hello','setup','accept_peer','unpair','model_status','model_key','save_model','delete_model_key']:
            return getattr(self.root,name)
        if self.enabled() and self.active() is self.root and name in ['assign','submit','feedback','set_task_state','start_self','start_model_practice','create_job','save_teacher_notes']:
            raise PermissionError('历史工作区只读，请切换到学科工作区后继续')
        if self.enabled() and getattr(self.active(),'workspace_subject',None)!='english' and name in ['assign','start_self','start_model_practice']:
            raise PermissionError('这些是英语题包入口；当前学科请从自己的资料设计学习任务')
        return getattr(self.active(),name)

    def __setattr__(self,name,value):
        if name in ['network','session_key']:setattr(self.root,name,value)
        else:object.__setattr__(self,name,value)

    def state(self):return self.root.config(KEY)
    def enabled(self):return bool(self.state())

    def current(self):
        state=self.state()
        return (state or {}).get('active','legacy')

    def active(self):
        bound=BOUND.get()
        if bound and bound[0] is self.root:return bound[1]
        return self.runtime(self.current()) if self.enabled() else self.root

    @contextmanager
    def bind(self):
        token=BOUND.set((self.root,self.active()))
        try:yield
        finally:BOUND.reset(token)

    @serialized
    def runtime(self,subject):
        if subject=='legacy':return self.root
        state=self.state()
        if not state or subject not in state['subjects']:raise ValueError('请先建立该学科工作区')
        if subject not in self.children:
            self.children[subject]=self.root.workspace_child(subject_path(self.root.folder,subject),subject)
        child=self.children[subject];child.network=self.root.network
        descriptor=child.folder/'workspace.json'
        expected={'version':1,'subject':subject,'name':state['subjects'][subject]['name'],'device':self.root.identity.id}
        if descriptor.exists():
            if json.loads(descriptor.read_text(encoding='utf8'))!=expected:raise ValueError('学科目录说明与登记不一致，未混用资料')
        else:
            with descriptor.open('xb') as file:file.write(canonical(expected))
        self.sync_peers(child)
        return child

    def sync_peers(self,child):
        known={p['id']:p for p in child._local_peers()}
        for p in self.root.peers():
            if p['state']=='active' and (p['id'] not in known or known[p['id']]['state']!='active'):
                hello={'id':p['id'],'public_key':p['public_key'],'role':p['role'],'name':p['name']}
                if p['role']=='student':
                    person=self.root.service.public_person(p['learner_id']);hello['student']={k:person[k] for k in ['name','exam','stage']}
                child.accept_peer(hello,self.root.vault.get('peer:'+p['id']))
            elif p['state']!='active':
                with child.db() as db:db.execute("UPDATE local_peers SET state='revoked' WHERE id=?",(p['id'],))

    def runtimes(self):
        return [self.root]+[self.runtime(s) for s in (self.state() or {}).get('subjects',{})]

    def summary(self):
        state=self.state()
        if not state:return {'enabled':False,'active':'legacy','subjects':[]}
        return {'enabled':True,'active':state['active'],'subjects':[{'id':id,**value,'folder':str(subject_path(self.root.folder,id))} for id,value in state['subjects'].items()],
            'legacy':{'id':'legacy','name':'历史工作区（待归属）','folder':str(self.root.folder),'read_only':True},
            'migration':state.get('migration',{}),'shared':['device_identity','pairing','model_configuration'],
            'isolated':['database','materials','tasks','submissions','feedback','memory','reviews','indexes','jobs']}

    @serialized
    def initialize(self):
        prior=self.state()
        if prior and prior.get('migration',{}).get('completed'):
            if 'english_resources_migration' not in prior['migration']:
                prior['migration']['english_resources_migration']=self.copy_english_resources();self.root.save_config(KEY,prior)
            return self.summary()
        if not self.root.role:raise PermissionError('请先完成本机身份设置')
        with self.root.db() as db:
            running=db.execute("SELECT COUNT(*) FROM local_jobs WHERE status='running'").fetchone()[0]
        if running:raise ValueError('旧工作区仍有模型任务运行，请等待完成后刷新，再启用独立学科工作区')
        from base.app.companion.aesthetic.academic import SUBJECTS
        study_store.initialize(self.root);academic_store.initialize(self.root)
        selection=self.root.config('academic-selection',{'subject':'english','track':'study_abroad'})
        subjects={id:{'name':value['name'],'track':selection['track'] if id==selection['subject'] else 'materials'} for id,value in SUBJECTS.items()}
        state=prior or {'version':1,'active':'legacy','intended_active':selection['subject'],'subjects':subjects,'migration':{'legacy_preserved':True,'classified_sources_copied':0,'historical_tasks':'legacy_pending_assignment'}}
        state['migration']['classified_sources_copied']=0
        # All existing records remain in the original database. Enabling only adds directories.
        self.root.save_config(KEY,state)
        try:
            for id in subjects:self.runtime(id)
            from base.app.companion.functional.subject_materials import listing
            for subject in subjects:
                data=listing(self.root,subject)
                for kind,values in [('text',data['materials']),('page',data['pages'])]:
                    for asset in values:
                        self.copy_legacy(subject,kind,asset['id'],asset['revision'],asset['source_hash'])
                        state['migration']['classified_sources_copied']+=1
            state['migration']['english_resources_migration']=self.copy_english_resources()
            state['migration']['completed']=True;state['active']=state.get('intended_active','english');self.root.save_config(KEY,state)
        except Exception:
            # Leave the complete legacy workspace selected; never hide an incomplete migration.
            state['active']='legacy';state['migration']['completed']=False;self.root.save_config(KEY,state)
            raise
        return self.summary()

    def copy_english_resources(self):
        """Existing typed TOEFL/IELTS packs are English assets, including their reviewed audio."""
        child=self.runtime('english');count=0;issues=[]
        for original in self.root.service.resources():
            if original.get('exam') not in ['ielts','toefl']:continue
            try:
                pack=copy.deepcopy(original)
                if pack.get('media_path'):
                    source=Path(pack['media_path']);raw=source.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=pack['audio_sha256']:raise ValueError('旧英语题库音频发生变化，未迁入')
                    folder=child.folder/'media';folder.mkdir(exist_ok=True);target=folder/(pack['audio_sha256']+source.suffix)
                    if target.exists() and target.read_bytes()!=raw:raise ValueError('英语音频文件冲突')
                    if not target.exists():target.write_bytes(raw)
                    pack['media_path']=str(target)
                with child.db() as db:
                    old=db.execute('SELECT body FROM hd_resources WHERE id=?',(pack['id'],)).fetchone()
                    body=json.dumps(pack,ensure_ascii=False)
                    if old and json.loads(old['body'])!=pack:raise ValueError('英语题库版本冲突，未覆盖')
                    db.execute('INSERT OR IGNORE INTO hd_resources VALUES (?,?)',(pack['id'],body))
                count+=1
            except (OSError,ValueError,KeyError) as error:issues.append({'id':original.get('id'),'reason':str(error)})
        return {'copied':count,'issues':issues}

    def copy_legacy(self,subject,kind,id,revision,source_hash):
        from base.app.companion.functional.subject_materials import original
        actual=original(self.root,kind,id)
        if actual['revision']!=revision or actual['source_hash']!=source_hash:raise ValueError('旧资料版本变化，请重新核对后迁入')
        child=self.runtime(subject);table='companion_materials' if kind=='text' else 'companion_pages'
        from base.app.companion.functional.continuity import initialize
        initialize(child)
        with self.root.db() as old:rows=old.execute('SELECT * FROM '+table+' WHERE id=?',(id,)).fetchall()
        with child.db() as new:
            columns=[r['name'] for r in new.execute('PRAGMA table_info('+table+')')]
            for row in rows:
                previous=new.execute('SELECT body FROM '+table+' WHERE id=? AND revision=?',(id,row['revision'])).fetchone()
                if previous and previous['body']!=row['body']:raise ValueError('目标学科存在不同版本，未覆盖')
                if kind=='page':
                    value=json.loads(row['body']);name='page-'+value['source_hash'];raw=(self.root.folder/'uploads'/name).read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=value['source_hash']:raise ValueError('旧原图校验失败')
                    folder=child.folder/'uploads';folder.mkdir(exist_ok=True);target=folder/name
                    if target.exists() and target.read_bytes()!=raw:raise ValueError('目标原图文件冲突')
                    if not target.exists():target.write_bytes(raw)
                new.execute('INSERT OR IGNORE INTO '+table+' ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row[c] for c in columns))
        materialize(child)
        # Sources are now owned by the physical workspace; original classification history stays in legacy.
        return {'asset_id':id,'subject':subject,'copied_versions':len(rows),'original_preserved':True}

    @serialized
    def select(self,subject,track='materials'):
        state=self.state()
        if not state:raise ValueError('请先初始化学科工作区')
        if subject!='legacy':
            if subject not in state['subjects']:raise ValueError('未知学科工作区')
            allowed=['k12','study_abroad','materials'] if subject=='english' else ['materials']
            if track not in allowed:raise ValueError('该学科没有这条专门路线')
            self.runtime(subject);state['subjects'][subject]['track']=track
        state['active']=subject;self.root.save_config(KEY,state)
        return {'selection':{'subject':subject,'track':track},'workspace':self.summary()}

    @serialized
    def invoke_capability(self,raw):
        if not isinstance(raw,dict):raise ValueError('能力请求必须是对象')
        if raw.get('contract_version')=='companion.capability.v11' and raw.get('operation') in ['experience.read','experience.select']:
            return self.root._invoke_capability(raw)
        if raw.get('contract_version')=='companion.capability.v8':
            r=WorkspaceRequest.model_validate(raw);p=PAYLOADS[r.operation].model_validate(r.payload)
            if r.operation=='workspace.initialize':data=self.initialize()
            elif r.operation=='workspace.list':data=self.summary()
            else:
                study_store.initialize(self.root)
                def apply(body):
                    p=PAYLOADS[r.operation].model_validate(body)
                    if r.operation=='workspace.select':return self.select(p.subject,p.track)
                    if r.operation=='workspace.legacy.import':return self.copy_legacy(p.subject,p.asset_kind,p.asset_id,p.revision,p.source_hash)
                    if not self.enabled():self.initialize()
                    name=p.name.strip()
                    if not name:raise ValueError('请填写学科名称')
                    id='subject-'+digest([r.request_id,name])[:16];state=self.state()
                    if any(v['name']==name for k,v in state['subjects'].items() if k!=id):raise ValueError('该名称的学科已存在')
                    state['subjects'][id]={'name':name,'track':'materials'};self.root.save_config(KEY,state);self.runtime(id)
                    return {'subject':{'id':id,'name':name},'folder':str(subject_path(self.root.folder,id))}
                data=study_store.transact(self.root,r,lambda:p.model_dump(),apply)
            return WorkspaceResult(request_id=r.request_id,operation=r.operation,data=data,
                decision_trace={'layers':['functional','assets'],'scope':'independent_subject_database','legacy_originals_preserved':True}).model_dump(mode='json')
        if not self.enabled():return self.root._invoke_capability(raw)
        op=raw.get('operation');selected=self.active();subject=getattr(selected,'workspace_subject','legacy')
        if op=='academic.select':
            p=raw.get('payload',{});data=self.select(p.get('subject'),p.get('track','materials'))
            return {'contract_version':'companion.capability.v7','request_id':raw['request_id'],'operation':op,'status':'completed','data':data,'decision_trace':{'layers':['functional','assets']}}
        legacy_read=bool(isinstance(op,str) and (op.endswith(('.list','.read')) or op in ['academic.catalog','academic.context','study.options','policy.catalog','policy.task','academic.asset.info','architecture.describe','evidence.read','evidence.list','asset.resolve','writing.history','benchmark.runs','benchmark.result','k12.report','k12.next','k12.notifications','review.context','review.settings','policy.cases'])) and op!='k12.notifications.read'
        if subject=='legacy' and not legacy_read:
            raise PermissionError('历史工作区只读；请切换到目标学科，或明确迁入资料后继续')
        if subject!='legacy':
            if raw.get('contract_version')=='companion.capability.v10' and subject!='english':raise PermissionError('英语教学工作流只在英语工作区使用')
            if (op.startswith(('k12.','route.','scope.')) and subject!='english'):raise PermissionError('K12英语能力只在英语工作区使用')
            if op in ['bank.preview','bank.commit'] and subject!='english':raise PermissionError('现有托福雅思题库导入仅在英语工作区使用')
            if op in ['academic.material.save','academic.page.save','academic.asset.classify'] and raw.get('payload',{}).get('subject')!=subject:
                raise PermissionError('请先切换到目标学科；不能向当前工作区写入其他学科资料')
            if op in ['academic.material.list']:
                if raw.get('payload',{}).get('subject') not in [subject,'all']:raise PermissionError('请先切换学科工作区，再读取该学科的资料')
                # All means all sources in this database, never across subject folders.
                raw=copy.deepcopy(raw);raw['payload']['subject']='all'
            if op in ['academic.material.save','academic.page.save'] and subject.startswith('subject-'):
                raw=copy.deepcopy(raw);raw['payload']['subject']='other'
        materialize(selected)
        result=selected._invoke_capability(raw)
        if op=='academic.catalog':
            state=self.state();result['data']['subjects']={id:{'name':v['name'],'tracks':result['data']['subjects'][id]['tracks'] if id in result['data']['subjects'] else {'materials':'通用资料学习'}} for id,v in state['subjects'].items()}
            result['data']['workspace']=self.summary()
            result['data']['subjects']['legacy']={'name':'历史工作区（待归属）','tracks':{'materials':'历史资料与作业（只读）'}}
        elif op=='academic.context':
            state=self.state();result['data']['selection']={'subject':subject,'track':state['subjects'].get(subject,{}).get('track','materials')};result['data']['workspace']=self.summary()
        elif op=='policy.catalog' and subject!='legacy':
            from base.app.companion.aesthetic.workspace_rules import allowed_scenarios
            result['data']['scenarios']={k:v for k,v in result['data']['scenarios'].items() if k in allowed_scenarios(subject)}
        elif op=='evidence.read' and subject not in ['english','legacy']:
            result['data']['workspace_subject']=subject;result['data']['subject']['exam']=None;result['data']['subject']['stage']=None
        materialize(selected)
        return result

    @serialized
    def status(self):
        result=self.active().status();result['workspace']=self.summary();result['root_data_folder']=str(self.root.folder)
        return result

    def peer(self,peer_id,active=True):
        self.root.peer(peer_id,active)
        return self.active().peer(peer_id,active)

    def unpair(self,peer_id):
        result=self.root.unpair(peer_id)
        for child in self.children.values():self.sync_peers(child)
        return result

    def pending(self,peer_id):
        self.root.peer(peer_id);return [env for runtime in self.runtimes() for env in runtime.pending(peer_id)]

    def ack(self,peer_id,event_id):
        for runtime in self.runtimes():runtime.ack(peer_id,event_id)

    @serialized
    def receive(self,envelope):
        if not isinstance(envelope,dict) or len(canonical(envelope))>20*1024*1024:raise ValueError('同步消息无效或过大')
        body=envelope.get('body',{});peer=self.root.peer(body.get('sender'))
        Identity.verify(peer['public_key'],body,envelope.get('signature'))
        if body.get('recipient')!=self.root.identity.id:raise PermissionError('消息并非发送给本机')
        if body.get('kind')=='ack':
            self.ack(peer['id'],body.get('payload',{}).get('id'))
            return self.root.receive(envelope)
        space=body.get('payload',{}).get('subject_workspace')
        target=self.root
        if space:
            if not self.enabled():raise ValueError('对方使用分学科工作区，请升级并初始化本机后重试，消息未确认送达')
            subject=space.get('id');state=self.state()
            if subject not in state['subjects']:
                if peer['role']!='teacher' or self.root.role!='student' or body.get('kind') not in ['task.assigned','task.updated','growth.plan']:raise PermissionError('只有已配对老师的任务或规划可以引入新学科')
                if not isinstance(subject,str) or not subject.startswith('subject-'):raise ValueError('收到未知学科标识')
                subject_path(self.root.folder,subject)
                name=space.get('name')
                if not isinstance(name,str) or not 1<=len(name)<=40:raise ValueError('学科名称无效')
                if any(v['name']==name for v in state['subjects'].values()):name=(name[:30]+'（老师任务）')
                state['subjects'][subject]={'name':name,'track':'materials'};self.root.save_config(KEY,state)
            target=self.runtime(subject)
        # Delivery never changes the currently selected workspace.
        return target.receive(envelope)

async def review_workers(runtime,background):
    """A worker remains pinned to one database even if the browser switches subjects."""
    import asyncio
    from base.app.companion.functional.review_agent import review_worker
    started=set()
    while True:
        candidates=runtime.runtimes() if runtime.enabled() else [runtime.root]
        for child in candidates:
            if runtime.enabled() and child is runtime.root:continue
            if str(child.folder) in started:continue
            with child.db() as db:
                db.execute("UPDATE local_jobs SET status='failed',error='程序上次退出时任务未完成，请重新发起。' WHERE status='running' OR (status='queued' AND id NOT LIKE 'review-job-%')")
            started.add(str(child.folder));task=asyncio.create_task(review_worker(child,background));background.add(task);task.add_done_callback(background.discard)
        await asyncio.sleep(.5)

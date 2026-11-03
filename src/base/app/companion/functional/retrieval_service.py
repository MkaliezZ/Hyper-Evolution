"""Shared v4 Harness for immutable indexes, comparisons and policy review records."""
import json,time
from uuid import uuid4
from base.core import now
from base.app.companion.assets.references import digest
from base.app.companion.assets.retrieval import config,content_identity,rank,document_key
from base.app.companion.aesthetic.cases import case_catalog,run_cases,binding
from base.app.companion.functional.retrieval_contracts import RetrievalRequest,RetrievalResult,PAYLOADS
from base.app.companion.functional.retrieval_sources import scope_key,collect_sources,current_documents,resolve_source,authorize_refs
from base.app.companion.functional.study_store import transact

TABLES={'index':'companion_indexes','benchmark':'companion_benchmarks','run':'companion_retrieval_runs',
        'check':'companion_policy_checks','review':'companion_policy_reviews'}

def initialize(runtime):
    from base.app.companion.functional.continuity import initialize as previous
    previous(runtime)
    with runtime.db() as db:
        for table in TABLES.values():db.execute('CREATE TABLE IF NOT EXISTS '+table+'(id TEXT NOT NULL,revision INTEGER NOT NULL,scope TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(id,revision))')

def rows(runtime,kind,scope):
    with runtime.db() as db:return [json.loads(r['body']) for r in db.execute('SELECT body FROM '+TABLES[kind]+' t WHERE scope=? AND revision=(SELECT MAX(revision) FROM '+TABLES[kind]+' WHERE id=t.id) ORDER BY rowid DESC',(scope,))]

def get(runtime,kind,id,scope,revision=None):
    with runtime.db() as db:
        row=db.execute('SELECT body FROM '+TABLES[kind]+' WHERE id=? AND scope=? '+('AND revision=? ' if revision else '')+'ORDER BY revision DESC LIMIT 1',
            (id,scope,revision) if revision else (id,scope)).fetchone()
    if not row:raise PermissionError('记录不存在或不属于当前检索范围')
    return json.loads(row['body'])

def save(runtime,kind,value):
    with runtime.db() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT body FROM '+TABLES[kind]+' WHERE id=? AND revision=?',(value['id'],value['revision'])).fetchone()
        if row:
            if json.loads(row['body'])!=value:raise ValueError('不可变版本冲突，请刷新后重试')
            return value
        head=db.execute('SELECT MAX(revision) FROM '+TABLES[kind]+' WHERE id=?',(value['id'],)).fetchone()[0]
        if value['revision']!=(head or 0)+1:raise ValueError('版本已被其他操作更新')
        if kind=='index':
            existing=db.execute('SELECT body FROM companion_indexes WHERE scope=?',(value['scope'],)).fetchall()
            if any(json.loads(x['body'])['generation']==value['generation'] for x in existing):raise ValueError('索引代次被其他操作更新，请重新构建')
        db.execute('INSERT INTO '+TABLES[kind]+' VALUES (?,?,?,?)',(value['id'],value['revision'],value['scope'],json.dumps(value,ensure_ascii=False)))
    return value

def index_summary(runtime,index,peer_id):
    docs,excluded=current_documents(runtime,index,peer_id)
    return {k:index[k] for k in ['id','revision','generation','parent_id','scope','created','manifest_hash','config','skipped']}|{
        'documents':len(docs),'chunks':sum(len(d['chunks']) for d in docs),'excluded':excluded,'indexed_documents':len(index['documents']),
        'state':'needs_rebuild' if excluded else 'ready' if docs else 'empty','domain_review':'unknown'}

def search(runtime,index,peer_id,query,method,k,documents=None):
    started=time.perf_counter()
    docs,excluded=current_documents(runtime,index,peer_id) if documents is None else (documents,[])
    failure=None
    try:
        if index['config']!=config(index['config']['chunk_characters'],index['config']['overlap_characters']):raise ValueError()
        hits=rank(docs,query,method,k)
    except Exception:hits=[];failure='索引配置或执行失效，请重建；本次不是未命中。'
    for hit in hits:hit['quality']={**hit['quality'],'retrieved':True}
    return {'state':'execution_failed' if failure else 'matched' if hits else 'source_unavailable' if not docs and excluded else 'empty_index' if not docs else 'no_match',
        'index_id':index['id'],'manifest_hash':index['manifest_hash'],'query':query,'method':method,'k':k,'hits':hits,
        'excluded':excluded,'error':failure,'elapsed_ms':round((time.perf_counter()-started)*1000,3),
        'boundary':'检索相关不等于专业正确或适合当前任务；原图仅检索标题/附注，未做OCR。'}

def expected_current(runtime,case,peer_id):
    for label in case['expected']:
        try:
            doc=resolve_source(runtime,label['source'],peer_id)
            if label['quote'] and label['quote'] not in doc['text']:return False
        except (PermissionError,ValueError,KeyError,FileNotFoundError):return False
    return True

def evaluate(runtime,benchmark,indexes,peer_id,methods,k):
    valid_cases=[(c,expected_current(runtime,c,peer_id)) for c in benchmark['cases']]
    corpora=[current_documents(runtime,i,peer_id) for i in indexes];results=[]
    for index,(documents,excluded) in zip(indexes,corpora):
        for method in methods:
            outcomes=[];positives=[];negatives=[]
            for case,valid in valid_cases:
                if not valid:
                    outcomes.append({'case_id':case['case_id'],'state':'not_scored_source_changed_or_revoked'});continue
                found=search(runtime,index,peer_id,case['query'],method,k,documents)
                if found['state']=='execution_failed':
                    outcomes.append({'case_id':case['case_id'],'state':'execution_failed','error':found['error']});continue
                ranks=[j+1 for j,h in enumerate(found['hits']) if any(document_key(e['source'])==h['document_key'] and
                    (not e['quote'] or e['quote'] in h['text']) for e in case['expected'])]
                reciprocal=1/min(ranks) if ranks else 0.
                outcome={'case_id':case['case_id'],'query':case['query'],'state':found['state'],'hits':found['hits'],
                    'elapsed_ms':found['elapsed_ms'],'expected_source_keys':[document_key(e['source']) for e in case['expected']],
                    'hit':bool(ranks) if case['expected'] else None,'reciprocal_rank':reciprocal if case['expected'] else None,
                    'unexpected_hits':bool(found['hits']) if not case['expected'] else None}
                outcomes.append(outcome)
                (positives if case['expected'] else negatives).append(outcome)
            results.append({'index_id':index['id'],'index_generation':index['generation'],'index_hash':index['manifest_hash'],'index_config':index['config'],'method':method,'k':k,
                'metrics':{'positive_cases':len(positives),'hit_at_k':sum(x['hit'] for x in positives)/len(positives) if positives else None,
                    'mrr_at_k':sum(x['reciprocal_rank'] for x in positives)/len(positives) if positives else None,
                    'negative_cases':len(negatives),'negative_false_positive_rate':sum(x['unexpected_hits'] for x in negatives)/len(negatives) if negatives else None,
                    'not_scored':sum(not valid for _,valid in valid_cases),'execution_failed_cases':sum(x['state']=='execution_failed' for x in outcomes),'excluded_sources':len(excluded),
                    'mean_elapsed_ms':sum(x['elapsed_ms'] for x in positives+negatives)/max(1,len(positives+negatives))},
                'cases':outcomes})
    corpus_hashes=[digest(sorted((d['key'],d['text_hash']) for d in docs)) for docs,_ in corpora]
    return {'results':results,'comparison_basis':'same_current_corpus' if len(set(corpus_hashes))==1 else 'corpus_or_processing_changed',
        'corpus_hashes':corpus_hashes,'benchmark_id':benchmark['id'],'benchmark_revision':benchmark['revision'],
        'case_set_hash':benchmark['case_set_hash'],'label_origin':benchmark['label_origin'],
        'source_refs':[d['source_ref'] for docs,_ in corpora for d in docs],
        'boundary':'只报告所选固定题集与标注下的结果，不自动选胜者。未命中、来源失效、执行失败分开；不是学习效果或专业审核。'}

def invoke(runtime,raw):
    if runtime.role not in ['student','teacher']:raise PermissionError('请先设置本机身份')
    try:
        r=RetrievalRequest.model_validate(raw);p=PAYLOADS[r.operation].model_validate(r.payload) if r.operation in PAYLOADS else None
        if p is None and r.payload:raise ValueError()
    except ValueError:raise ValueError('v4 请求格式无效，请核对动作、来源、版本与必填项') from None
    initialize(runtime)
    policy=r.operation.startswith('policy.')
    if policy and r.peer_id:raise ValueError('规则案例审阅不绑定学生，不接收学生上下文')
    selected='policy' if policy else scope_key(runtime,r.peer_id)
    if r.operation.startswith('policy.review'):runtime.require_role('teacher')
    if r.operation.startswith('index.') and hasattr(p,'index_id'):index=get(runtime,'index',p.index_id,selected)
    if r.operation.startswith('benchmark.') and hasattr(p,'benchmark_id') and p.benchmark_id:
        benchmark=get(runtime,'benchmark',p.benchmark_id,selected,getattr(p,'revision',None))
        authorize_refs(runtime,[e['source'] for c in benchmark['cases'] for e in c['expected']],r.peer_id)
    if r.operation=='benchmark.run':indexes=[get(runtime,'index',id,selected) for id in p.index_ids]
    if r.operation=='benchmark.result':
        result=get(runtime,'run',p.run_id,selected);authorize_refs(runtime,result['source_refs'],r.peer_id)
    if r.operation=='policy.check.read':result=get(runtime,'check',p.run_id,'policy')
    def prepare():
        if r.operation=='index.build':
            cfg=config(p.chunk_size,p.overlap);docs,skipped=collect_sources(runtime,r.peer_id,cfg)
            history=rows(runtime,'index',selected);manifest=content_identity(docs,cfg,selected);old=next((i for i in history if i['manifest_hash']==manifest),None)
            return old or {'id':'idx-'+uuid4().hex,'revision':1,'generation':max((i['generation'] for i in history),default=0)+1,
                'parent_id':history[0]['id'] if history else None,'scope':selected,'created':now(),'manifest_hash':manifest,
                'config':cfg,'documents':docs,'skipped':skipped}
        if r.operation=='benchmark.save':
            cases=[]
            for c in p.cases:
                value=c.model_dump();labels=[]
                for expected in c.expected:
                    doc=resolve_source(runtime,expected.source,r.peer_id)
                    if expected.quote and expected.quote not in doc['text']:raise ValueError('期望引文不在实际来源中')
                    labels.append({'source':doc['source_ref'],'quote':expected.quote})
                value['expected']=labels;cases.append(value)
            old=get(runtime,'benchmark',p.benchmark_id,selected) if p.benchmark_id else None
            if old and old['revision']!=p.expected_revision:raise ValueError('对照题集版本已更新')
            if not p.title.strip():raise ValueError('题集标题不能为空')
            return {'id':p.benchmark_id or 'bench-'+uuid4().hex,'revision':old['revision']+1 if old else 1,'scope':selected,'created':now(),
                'title':p.title.strip(),'label_origin':p.label_origin,'cases':cases,'case_set_hash':digest(cases),'domain_review':'NOT_REVIEWED'}
        if r.operation=='benchmark.run':
            return {'id':'run-'+uuid4().hex,'revision':1,'scope':selected,'created':now(),**evaluate(runtime,benchmark,indexes,r.peer_id,p.methods,p.k)}
        if r.operation=='policy.check':return {'id':'check-'+uuid4().hex,'revision':1,'scope':'policy','created':now(),**run_cases(p.pack)}
        if r.operation=='policy.review.record':
            check=get(runtime,'check',p.check_id,'policy')
            if check['binding_hash']!=digest(binding()):raise ValueError('规则或案例版本已变化，请重新检查再审阅')
            ids={c['case_id'] for c in check['cases'] if c['pack']==p.pack}
            if not ids or ids!={c.case_id for c in p.observations}:raise ValueError('请逐例审阅所选规则包的正例和反例')
            if p.conclusion=='approved_for_pilot' and (not check['engineering_passed'] or any(c.verdict!='appropriate' for c in p.observations)):
                raise ValueError('工程检查失败或案例仍有待修订，不能放行为限定试用')
            return {'id':'review-'+uuid4().hex,'revision':1,'scope':'policy','created':now(),**p.model_dump(),
                'binding':check['binding'],'binding_hash':check['binding_hash'],'reviewer_device':runtime.identity.id,
                'reviewer_role':'local_teacher','credentials':'self_declared_not_verified','effect':'local_scoped_pilot_only_no_runtime_rule_change',
                'learning_effect':'NOT_TESTED'}
    kind={'index.build':'index','benchmark.save':'benchmark','benchmark.run':'run','policy.check':'check','policy.review.record':'review'}.get(r.operation)
    def apply(body):
        if not policy and scope_key(runtime,r.peer_id)!=selected:raise PermissionError('当前范围变化')
        if kind=='index':
            documents,excluded=current_documents(runtime,body,r.peer_id)
            if excluded:raise ValueError('来源在构建时发生变化，请重新构建索引')
        if kind=='benchmark':authorize_refs(runtime,[e['source'] for c in body['cases'] for e in c['expected']],r.peer_id)
        if kind=='run':authorize_refs(runtime,body['source_refs'],r.peer_id)
        if kind=='review':runtime.require_role('teacher')
        return save(runtime,kind,body)
    if kind:
        value=transact(runtime,r,prepare,apply)
        if kind=='index':data={'index':index_summary(runtime,value,r.peer_id)}
        elif kind=='benchmark':
            authorize_refs(runtime,[e['source'] for c in value['cases'] for e in c['expected']],r.peer_id);data={'benchmark':value}
        elif kind=='run':authorize_refs(runtime,value['source_refs'],r.peer_id);data={'run':value}
        else:data={'check' if kind=='check' else 'review':{**value,'current_binding':value['binding_hash']==digest(binding())}}
    elif r.operation=='index.list':data={'indexes':[index_summary(runtime,i,r.peer_id) for i in rows(runtime,'index',selected)]}
    elif r.operation=='index.read':
        docs,excluded=current_documents(runtime,index,r.peer_id);data={'index':index_summary(runtime,index,r.peer_id),
            'sources':[{k:d[k] for k in ['key','title','source','kind','source_ref','quality']} for d in docs],'excluded':excluded}
    elif r.operation=='index.search':data=search(runtime,index,r.peer_id,p.query,p.method,p.k)
    elif r.operation=='benchmark.list':data={'benchmarks':[{k:b[k] for k in ['id','revision','title','created','case_set_hash','label_origin']} for b in rows(runtime,'benchmark',selected)]}
    elif r.operation=='benchmark.read':data={'benchmark':benchmark}
    elif r.operation=='benchmark.runs':
        visible=[]
        for run in rows(runtime,'run',selected):
            if run['benchmark_id']!=benchmark['id']:continue
            try:authorize_refs(runtime,run['source_refs'],r.peer_id)
            except PermissionError:continue
            visible.append({k:run[k] for k in ['id','created','benchmark_revision','case_set_hash','comparison_basis']})
        data={'runs':visible}
    elif r.operation=='benchmark.result':
        data={'run':result}
    elif r.operation=='policy.cases':data=case_catalog(p.pack)
    elif r.operation=='policy.check.read':data={'check':result,'current_binding':result['binding_hash']==digest(binding())}
    else:data={'reviews':[{**value,'current_binding':value['binding_hash']==digest(binding())} for value in rows(runtime,'review','policy') if p.pack is None or value['pack']==p.pack]}
    if 'run' in data:
        run=data['run'];data['run']={**run,'current_source_state':'changed' if any(not expected_current(runtime,
            {'expected':[{'source':ref,'quote':''}]},r.peer_id) for ref in run['source_refs']) else 'current'}
    status='completed'
    if r.operation=='index.search':
        status='failed' if data['state']=='execution_failed' else 'partial' if data['excluded'] or data['state'] in ['source_unavailable','empty_index'] else 'completed'
    if r.operation=='index.build' and (data['index']['skipped'] or not data['index']['documents']):status='partial'
    if r.operation=='policy.check' and not data['check']['engineering_passed']:status='needs_review'
    if r.operation=='benchmark.run':
        metrics=[x['metrics'] for x in data['run']['results']]
        if any(m['execution_failed_cases'] or m['not_scored'] for m in metrics):status='partial'
        if all(m['execution_failed_cases'] and not m['positive_cases'] and not m['negative_cases'] for m in metrics):status='failed'
    return RetrievalResult(request_id=r.request_id,operation=r.operation,status=status,data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'actor':runtime.role,'scope':selected,'domain_review':'NOT_AUTOMATIC',
            'mastery_updated':False},**({'commit_receipt':{'saved':True,'request_id':r.request_id}} if kind else {})).model_dump(mode='json',exclude_none=True)

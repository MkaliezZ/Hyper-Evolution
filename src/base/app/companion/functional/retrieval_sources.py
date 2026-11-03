"""Resolve index inputs from current local authorization; no answer keys/private notes."""
import json
from base.app.companion.assets.references import digest
from base.app.companion.assets.retrieval import chunks,document_key
from base.app.companion.functional.continuity import initialize,page
from base.app.companion.functional.continuity_contracts import Source
from base.app.companion.functional.study import authorized_task,read_material
from base.app.companion.functional.study_contracts import MaterialRead
from base.app.companion.functional.evidence import authorized_tasks

def scope_key(runtime,peer_id=None):
    if runtime.role=='student':
        if peer_id:raise PermissionError('学生只能使用自己的资料检索')
        return 'self'
    runtime.require_role('teacher')
    if not peer_id:return 'library'
    peer=runtime.peer(peer_id)
    if peer['role']!='student':raise PermissionError('请选择已连接学生')
    return 'peer:'+peer_id

def resolve_source(runtime,source,peer_id=None,current=True):
    p=source if isinstance(source,Source) else Source.model_validate(source)
    if p.task_id:
        task=authorized_task(runtime,p.task_id,peer_id);pack=task['pack']
        if pack.get('source_page'):
            original=page(runtime,p,peer_id,False)
            text='\n'.join([original['title'],original.get('caption','')]);kind='image_metadata'
            ref={'task_id':p.task_id,'revision':original['revision'],'source_hash':original['source_hash']}
        else:
            text=pack.get('stimulus','');kind='text'
            ref={'task_id':p.task_id,'revision':pack.get('companion_plan',{}).get('source_ref',{}).get('revision',1),'source_hash':digest(text)}
            if p.revision and p.revision!=ref['revision']:raise ValueError('任务来源版本变化')
            if p.source_hash and p.source_hash!=ref['source_hash']:raise ValueError('任务来源内容变化')
        title=pack['title'];origin=pack.get('source',{}).get('title','任务绑定资料')
    elif p.page_id:
        original=page(runtime,p,None,False)
        if current:
            head=page(runtime,Source(page_id=p.page_id),None,False)
            if head['revision']!=original['revision']:raise ValueError('原图已有新版本，请重建索引')
        text='\n'.join([original['title'],original.get('caption','')]);kind='image_metadata';title=original['title'];origin=original['source']
        ref={'page_id':p.page_id,'revision':original['revision'],'source_hash':original['source_hash']}
    else:
        original=read_material(runtime,MaterialRead(material_id=p.material_id,revision=p.revision,source_hash=p.source_hash),None)
        if digest(original['text'])!=original['source_hash']:raise ValueError('文字原件内容变化')
        if current and original['superseded']:raise ValueError('文字已有新版本，请重建索引')
        text=original['text'];kind='text';title=original['title'];origin=original['source']
        ref={'material_id':p.material_id,'revision':original['revision'],'source_hash':original['source_hash']}
    if not text.strip():raise ValueError('来源没有可索引文字，未把媒体伪装成转写')
    return {'key':document_key(ref),'title':title,'source':origin,'kind':kind,'text':text,'text_hash':digest(text),'source_ref':ref,
        'quality':{'ingested':True,'parsed':'metadata_only_no_ocr' if kind=='image_metadata' else 'text_readable',
            'indexed':False,'retrieved':False,'domain_review':'unknown','task_fit':'requires_task_judgment'}}

def collect_sources(runtime,peer_id,cfg):
    initialize(runtime);refs=[];skipped=[]
    with runtime.db() as db:
        for table,field in [('companion_materials','material_id'),('companion_pages','page_id')]:
            refs.extend({field:r['id']} for r in db.execute('SELECT DISTINCT id FROM '+table+' ORDER BY id'))
    if runtime.role=='student' or peer_id:
        refs.extend({'task_id':t['id']} for t in authorized_tasks(runtime,peer_id)[1])
    docs=[];characters=0
    for ref in refs:
        try:
            doc=resolve_source(runtime,ref,peer_id)
            if len(docs)>=200 or characters+len(doc['text'])>500000:
                skipped.append({'source_ref':ref,'reason':'capacity_limit; split corpus before rebuilding'});continue
            characters+=len(doc['text'])
            doc['chunks']=[{'start':s,'end':e,'text':t} for s,e,t in chunks(doc['text'],cfg['chunk_characters'],cfg['overlap_characters'])]
            del doc['text'];doc['quality']['indexed']=True;docs.append(doc)
        except (ValueError,KeyError,FileNotFoundError):skipped.append({'source_ref':ref,'reason':'source_unavailable_or_no_text'})
    return sorted(docs,key=lambda d:d['key']),skipped

def current_documents(runtime,index,peer_id=None):
    documents=[];excluded=[]
    for doc in index['documents']:
        try:
            fresh=resolve_source(runtime,doc['source_ref'],peer_id)
            if fresh['text_hash']!=doc['text_hash']:raise ValueError('派生文本变化')
            expected=[{'start':s,'end':e,'text':t} for s,e,t in chunks(fresh['text'],index['config']['chunk_characters'],index['config']['overlap_characters'])]
            if expected!=doc['chunks']:raise ValueError('索引片段与原件或位置不匹配')
            documents.append(doc)
        except PermissionError:excluded.append({'key':None,'reason':'permission_revoked'})
        except (ValueError,KeyError,FileNotFoundError):excluded.append({'key':doc['key'],'reason':'source_updated_or_missing'})
    return documents,excluded

def authorize_refs(runtime,refs,peer_id=None):
    for ref in refs:
        if ref.get('task_id'):authorized_task(runtime,ref['task_id'],peer_id)

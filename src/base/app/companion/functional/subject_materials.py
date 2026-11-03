"""Own-device material organization behind the shared capability facade."""
from base.core import now
from base.app.companion.assets.references import digest
from base.app.companion.assets.academic import seal
from base.app.companion.assets.subjects import binding_id,project_subject
from base.app.companion.functional import academic_store as store
from base.app.companion.functional.study_store import transact
from base.app.companion.functional.academic_contracts import AcademicResult

KIND='asset_subject'

def binding(runtime,kind,id):
    try:return store.get(runtime,KIND,binding_id(kind,id))
    except KeyError:return None

def original(runtime,kind,id):
    if kind=='text':
        from base.app.companion.functional.study import read_material
        from base.app.companion.functional.study_contracts import MaterialRead
        value=read_material(runtime,MaterialRead(material_id=id))
    else:
        from base.app.companion.functional.continuity import initialize,page
        from base.app.companion.functional.continuity_contracts import Source
        initialize(runtime);value=page(runtime,Source(page_id=id),include_image=False)
    return {k:v for k,v in value.items() if k not in ['text','selection','data_base64']}

def listing(runtime,subject):
    def call(version,operation):return runtime._invoke_capability({'contract_version':version,'request_id':'subject-list-'+operation,
        'operation':operation,'payload':{}})['data']
    labels={v['id']:v for v in store.rows(runtime,KIND)};materials=[];pages=[];counts={k:0 for k in ['english','mathematics','science','humanities','other','unclassified']}
    for kind,key,values in [('text','materials',call('companion.capability.v2','material.list')['materials']),
                            ('page','pages',call('companion.capability.v3','page.list')['pages'])]:
        for value in values:
            classification=project_subject(value,labels.get(binding_id(kind,value['id'])));category=classification['subject'] or 'unclassified'
            counts[category]+=1
            if subject=='all' or category==subject:(materials if kind=='text' else pages).append({**value,'classification':classification})
    return {'subject':subject,'materials':materials,'pages':pages,'counts':counts,'unclassified_count':counts['unclassified'],
        'boundary':'分类仅组织本人本机资料；旧全库接口保留兼容，分类不是权限边界或学科内容审核。'}

def invoke(runtime,r,p):
    if runtime.role not in ['teacher','student'] or r.peer_id:raise PermissionError('资料分类仅用于本机身份，不读取配对方的个人资料库')
    store.initialize(runtime);op=r.operation
    def check_revision(kind,id,expected):
        old=binding(runtime,kind,id)
        if (old['revision'] if old else 0)!=expected:raise ValueError('资料分类已更新，请刷新后再操作')
    def value(kind,meta,subject,expected,created):
        return seal({'id':binding_id(kind,meta['id']),'revision':expected+1,'peer_id':None,'created':created,
            'asset_kind':kind,'asset_ref':{k:meta[k] for k in ['id','revision','source_hash']},'subject':subject,
            'authority':'user_declared_category_not_domain_review'})
    def prepare():
        if op=='academic.asset.classify':
            meta=original(runtime,p.asset_kind,p.asset_id)
            if meta['revision']!=p.asset_revision or meta['source_hash']!=p.source_hash:raise ValueError('原资料版本变化，请重新查看后再分类')
            check_revision(p.asset_kind,p.asset_id,p.expected_revision)
            return {'binding':value(p.asset_kind,meta,p.subject,p.expected_revision,now())}
        kind='text' if op=='academic.material.save' else 'page';id=p.material_id if kind=='text' else p.page_id
        if id:check_revision(kind,id,p.classification_revision)
        elif p.classification_revision:raise ValueError('新资料的分类版本应为0')
        return {'kind':kind,'subject':p.subject,'classification_revision':p.classification_revision,'created':now(),
            'payload':p.model_dump(exclude={'subject','classification_revision'})}
    def apply(body):
        if op=='academic.asset.classify':
            v=body['binding'];meta=original(runtime,v['asset_kind'],v['asset_ref']['id'])
            if any(meta[k]!=v['asset_ref'][k] for k in ['revision','source_hash']):raise ValueError('执行前原资料变化，请重新分类')
            saved=store.save(runtime,KIND,v);return {'record':saved,'classification':project_subject(meta,saved)}
        kind=body['kind'];version='companion.capability.v2' if kind=='text' else 'companion.capability.v3';key='material' if kind=='text' else 'page'
        result=runtime.invoke_capability({'contract_version':version,'request_id':'subject-save-'+digest(r.request_id),
            'operation':key+'.save','payload':body['payload']})['data'][key]
        latest=original(runtime,kind,result['id'])
        if any(latest[k]!=result[k] for k in ['revision','source_hash']):raise ValueError('资料已被另一次操作修改，请刷新核对分类')
        saved=store.save(runtime,KIND,value(kind,result,body['subject'],body['classification_revision'],body['created']))
        return {key:{**result,'classification':project_subject(result,saved)}}
    write=op in ['academic.material.save','academic.page.save','academic.asset.classify']
    if write:data=transact(runtime,r,prepare,apply)
    elif op=='academic.material.list':data=listing(runtime,p.subject)
    else:
        meta=original(runtime,p.asset_kind,p.asset_id)
        data={'asset':meta,'classification':project_subject(meta,binding(runtime,p.asset_kind,p.asset_id))}
    return AcademicResult(request_id=r.request_id,operation=op,status='completed',data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'classification_authority':'user_declared',
            'automatic_content_inference':False,'domain_review':'not_inferred'},
        **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if write else {})).model_dump(mode='json',exclude_none=True)

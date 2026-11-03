"""Explicit candidate -> declared review -> local release, separate from personal memory."""
from uuid import uuid4
from base.core import now
from base.app.companion.assets.methods import METHOD_FIELDS,screened_content,portable_release
from base.app.companion.functional import evolution_store as store
from base.app.companion.functional.study_store import transact
from base.app.companion.functional.evolution_contracts import EvolutionResult

def invoke_method(runtime,r,p):
    from base.app.companion.functional.evolution import seal
    runtime.require_role('teacher')
    if r.peer_id:raise ValueError('共享方法库独立于学生档案；请先切换到我的方法库')
    def own(kind,id):
        value=store.get(runtime,kind,id)
        if value['scope']!='library' or value['owner_device']!=runtime.identity.id:raise PermissionError('方法资产不属于本机负责人')
        return value
    candidate=own('method',p.candidate_id) if hasattr(p,'candidate_id') else None
    def common(prefix):return {'id':prefix+uuid4().hex,'revision':1,'scope':'library','created':now(),'owner_device':runtime.identity.id}
    def prepare():
        if r.operation=='method.candidate':return seal({**common('method-'),**screened_content(p.model_dump()),'state':'candidate','authorship':'caller_declared'})
        if r.operation=='method.review':
            if p.candidate_hash!=candidate['content_hash']:raise ValueError('候选版本已变化')
            if p.conclusion=='pass_for_declared_scope' and not all([p.use_basis_checked,p.deidentification_checked,p.cases_checked,p.scope_checked]):raise ValueError('用途、脱敏、正反例和范围须全部审阅后才能声明通过')
            return seal({**common('method-review-'),**p.model_dump(),'identity_assurance':'caller_declaration_only'})
        if r.operation=='method.publish':
            review=own('method_review',p.review_id)
            reviews=[v for v in store.rows(runtime,'method_review','library') if v['candidate_id']==candidate['id']]
            if not reviews or reviews[0]['id']!=review['id']:raise ValueError('请采用最新审阅，较早通过不能覆盖后续否决')
            if review['candidate_hash']!=candidate['content_hash'] or review['conclusion']!='pass_for_declared_scope':raise ValueError('这份候选没有适用范围内的通过审阅')
            releases=[v for v in store.rows(runtime,'method_release','library') if v['candidate_id']==candidate['id']]
            generation=max([v['artifact']['version'] for v in releases],default=0)+1
            artifact=portable_release(candidate,review,p.publisher_name,p.publication_note,generation)
            return seal({**common('method-release-'),'candidate_id':candidate['id'],'candidate_hash':candidate['content_hash'],
                'review_id':review['id'],'artifact':artifact,'delivery':'local_release_only','runtime_policy_changed':False})
    writes=r.operation in ['method.candidate','method.review','method.publish']
    def apply(value):
        runtime.require_role('teacher')
        if candidate:own('method',candidate['id'])
        if r.operation=='method.publish':
            # Recheck the latest review if a prepared operation is retried after interruption.
            reviews=[v for v in store.rows(runtime,'method_review','library') if v['candidate_id']==candidate['id']]
            if not reviews or reviews[0]['id']!=value['review_id'] or reviews[0]['conclusion']!='pass_for_declared_scope':raise ValueError('审阅已变化，请重新发布')
        key={'method.candidate':'method','method.review':'method_review','method.publish':'method_release'}[r.operation]
        return {key:store.save(runtime,key,value)}
    if writes:data=transact(runtime,r,prepare,apply)
    elif r.operation=='method.list':
        data={'candidates':store.rows(runtime,'method','library')[:100],'releases':store.rows(runtime,'method_release','library')[:100]}
    elif r.operation=='method.read':
        data={'candidate':candidate,'reviews':[v for v in store.rows(runtime,'method_review','library') if v['candidate_id']==candidate['id']],
            'releases':[v for v in store.rows(runtime,'method_release','library') if v['candidate_id']==candidate['id']]}
    else:
        releases=[v for v in store.rows(runtime,'method_release','library') if v['candidate_id']==candidate['id']]
        if not releases:raise ValueError('请先完成独立审阅与负责人发布，再导出共享方法')
        reviews=[v for v in store.rows(runtime,'method_review','library') if v['candidate_id']==candidate['id']]
        if not reviews or reviews[0]['id']!=releases[0]['review_id']:raise ValueError('审阅有后续变更，旧发布不再作为当前导出')
        data={'artifact':releases[0]['artifact'],'contains_private_record_links':False,'runtime_policy_changed':False}
    return EvolutionResult(request_id=r.request_id,operation=r.operation,status='completed',data=data,
        decision_trace={'layers':['aesthetic','functional','assets'],'identity_assurance':'caller_declaration_only',
            'personal_memory_copied':False,'runtime_policy_changed':False},
        **({'commit_receipt':{'saved':True,'request_id':r.request_id}} if writes else {})).model_dump(mode='json',exclude_none=True)

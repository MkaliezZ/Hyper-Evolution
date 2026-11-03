"""Pure asset identities and public K12 projections. No database or judgments."""
from base.app.companion.assets.references import digest

def question_fingerprint(q):
    return digest({k:q.get(k) for k in ['type','material','prompt','options']})

def public_academic(meta):
    return {k:meta[k] for k in ['version','subject','track','level','grade','route_id','scope_refs','mode','target','supports','question_refs','audio_ref','policy_ref'] if k in meta}

def seal(value):return {**value,'content_hash':digest({k:v for k,v in value.items() if k!='content_hash'})}

def verify_task(task):
    meta=task['pack'].get('academic')
    if not meta:return
    if meta.get('version')!='k12.task.v1' or meta.get('subject')!='english' or meta.get('track')!='k12':raise ValueError('学科任务标识不匹配')
    refs=meta.get('question_refs',{})
    if set(refs)!={q['id'] for q in task['pack']['items']}:raise ValueError('题目引用与任务不匹配')
    if meta.get('mode') not in ['practice','target']:raise ValueError('未知施测条件')
    if meta.get('mode')=='target' and (not meta.get('target') or meta.get('supports')):raise ValueError('目标测验不得带提示或缺目标覆盖')
    qids={q['id'] for q in task['pack']['items']};submissions={a['id'] for a in task['attempts']}
    values=task.get('academic_feedback',[])
    if not isinstance(values,list) or len(values)>200:raise ValueError('学科反馈数量无效')
    allowed={'problem','explanation','score','erratum'}
    for value in values:
        if value.get('kind') not in allowed or value.get('task_id')!=task['id'] or value.get('question_id') not in qids:raise ValueError('学科反馈与当前题目不匹配')
        if value.get('kind')!='erratum' and value.get('submission_id') not in submissions:raise ValueError('学科反馈与当前原答不匹配')
        if any(key in value for key in ['tutor','evidence_note','student_quote','peer_id','check_task_id','check_submission_id']):raise ValueError('学科反馈不能携带教师私有内容')
        if value.get('content_hash')!=digest({k:v for k,v in value.items() if k not in ['content_hash','kind']}):raise ValueError('学科反馈内容指纹不一致')

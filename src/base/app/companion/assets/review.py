"""Pure review source locations, draft deltas and immutable content hashes."""
from base.app.companion.assets.references import digest

def quote_refs(dimensions,task_id,submission_id,work,material):
    refs=[]
    for d in dimensions:
        if not d['evidence']:continue
        for kind,text,id in [('answer',work,submission_id),('task_material',material,task_id)]:
            start=text.find(d['evidence'])
            if start>=0:refs.append({'criterion':d['criterion'],'kind':kind,'id':id,'task_id':task_id,'source_hash':digest(text),
                'start':start,'end':start+len(d['evidence']),'quote':d['evidence']})
    return refs

def field_changes(before,after):
    return [{'field':k,'before':before.get(k),'after':after.get(k)} for k in ['comment','next_step','outcome','dimensions'] if before.get(k)!=after.get(k)]

def seal(value):return {**value,'content_hash':digest({k:v for k,v in value.items() if k!='content_hash'})}

def validate_assistance(task):
    values=task.get('companion_review_assistance',[])
    if not isinstance(values,list) or len(values)>50:raise ValueError('评阅辅助来源格式无效')
    allowed={'assessment_id','submission_id','used_ai','model_name','teacher_modified','draft_revision','created'}
    records={r['id']:r for r in task.get('companion_assessments',[])}
    for v in values:
        if not isinstance(v,dict) or set(v)!=allowed or v.get('assessment_id') not in records:raise ValueError('辅助来源未关联本任务正式评阅')
        if records[v['assessment_id']]['submission_id']!=v['submission_id']:raise ValueError('评阅辅助来源作品不匹配')
        if type(v['used_ai']) is not bool or type(v['teacher_modified']) is not bool or type(v['draft_revision']) is not int or v['draft_revision']<1:raise ValueError('评阅辅助声明无效')
        if not isinstance(v['model_name'],str) or len(v['model_name'])>160 or not isinstance(v['created'],str) or len(v['created'])>80:raise ValueError('评阅辅助声明无效')

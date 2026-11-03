"""Pure, Unicode-codepoint changes and integrity checks; authorship is declared."""
from difflib import SequenceMatcher
import json,re
from base.app.companion.assets.references import digest

def text_changes(before,after):
    # Trim identical margins before matching; long repetitive essays otherwise make even
    # a one-character append quadratic. Offsets still refer to the exact original text.
    left=0;limit=min(len(before),len(after))
    while left<limit and before[left]==after[left]:left+=1
    right=0
    while right<limit-left and before[len(before)-1-right]==after[len(after)-1-right]:right+=1
    old=before[left:len(before)-right if right else len(before)]
    new=after[left:len(after)-right if right else len(after)]
    return [{'kind':kind,'before_start':a+left,'before_end':b+left,'after_start':c+left,'after_end':d+left,
             'before':old[a:b],'after':new[c:d]} for kind,a,b,c,d in SequenceMatcher(None,old,new,autojunk=False).get_opcodes() if kind!='equal']

def plan_changes(before,after):
    changes=[]
    for field in ['title','goal','task_ids']:
        if before.get(field)!=after.get(field):changes.append({'field':field,'before':before.get(field),'after':after.get(field)})
    old={s['id']:s for s in before.get('steps',[])};new={s['id']:s for s in after['steps']}
    for id in dict.fromkeys(list(old)+list(new)):
        if old.get(id)!=new.get(id):changes.append({'field':'step:'+id,'before':old.get(id),'after':new.get(id)})
    if list(old)!=list(new):changes.append({'field':'step_order','before':list(old),'after':list(new)})
    return changes

def apply_suggestions(text,suggestions):
    ordered=sorted(suggestions,key=lambda s:(s['start'],s['end']));last=-1
    for s in ordered:
        if not 0<=s['start']<=s['end']<=len(text) or text[s['start']:s['end']]!=s['original']:
            raise ValueError('建议位置或原文不匹配，请基于当前稿重新准备')
        if s['start']<last or s['start']==last and s['start']==s['end']:
            raise ValueError('建议位置重叠，请分次选择')
        last=s['end']
    result=text
    for s in reversed(ordered):result=result[:s['start']]+s['replacement']+result[s['end']:]
    if len(result)>12000:raise ValueError('修订稿超过12000字')
    return result

def validate_writing_history(history,text):
    """Validate bytes/links, never claim that device declarations prove human authorship."""
    if not isinstance(history,dict) or set(history)-{'document_id','title','versions','truncated','boundary'}:raise ValueError('写作历史结构无效')
    versions=history.get('versions')
    if not isinstance(history.get('document_id'),str) or not 1<=len(history['document_id'])<=80 or not isinstance(history.get('title'),str) or len(history['title'])>160:
        raise ValueError('写作历史标识无效')
    if len(json.dumps(history,ensure_ascii=False))>1500000:raise ValueError('写作历史过大，请减少单次同步范围')
    if not isinstance(versions,list) or not 1<=len(versions)<=25 or type(history.get('truncated',False)) is not bool:raise ValueError('写作历史最多同步25版')
    previous=0
    allowed={'revision','text','text_hash','parent_hash','contribution','contribution_note','additional_help','suggestion_refs','changes','created'}
    for v in versions:
        if not isinstance(v,dict) or set(v)!=allowed or type(v.get('revision')) is not int or not previous<v['revision']<=100000:raise ValueError('写作版本顺序无效')
        if not isinstance(v.get('text'),str) or len(v['text'])>12000 or digest(v['text'])!=v.get('text_hash'):raise ValueError('写作原文校验失败')
        if v.get('contribution') not in ['learner_declared','learner_revision_declared','external_assisted_revision','teacher_proposed_revision','submitted_work_snapshot']:
            raise ValueError('不能伪造写作贡献类型')
        if any(not isinstance(v[k],str) or len(v[k])>limit for k,limit in [('contribution_note',2000),('additional_help',800),('created',80)]):raise ValueError('写作声明格式无效')
        if not isinstance(v['suggestion_refs'],list) or len(v['suggestion_refs'])>6 or not isinstance(v['changes'],list):raise ValueError('写作改动引用无效')
        for ref in v['suggestion_refs']:
            if not isinstance(ref,dict) or set(ref)!={'id','owner_device','contributor','base_text_hash'}:raise ValueError('建议来源声明无效')
            if any(not isinstance(ref[k],str) or not 1<=len(ref[k])<=128 for k in ['id','owner_device']):raise ValueError('建议来源声明无效')
            if ref['contributor'] not in ['external_suggestion','teacher_suggestion'] or not re.fullmatch('[0-9a-f]{64}',str(ref['base_text_hash'])):raise ValueError('建议来源声明无效')
        previous=v['revision']
    if versions[0]['revision']!=1 or versions[0]['parent_hash'] is not None or versions[0]['changes']:raise ValueError('必须保留原始首稿')
    if versions[-1]['text']!=text:raise ValueError('提交内容与写作末版不一致')
    for a,b in zip(versions,versions[1:]):
        if b['revision']!=a['revision']+1 and not history.get('truncated'):raise ValueError('缺失的历史版本必须明确标记')
        if b['revision']==a['revision']+1 and (b.get('parent_hash')!=a['text_hash'] or b.get('changes')!=text_changes(a['text'],b['text'])):
            raise ValueError('写作差异与原件不一致')
    return {**history,'boundary':'来自提交设备的贡献与帮助声明；完整性校验不证明独立完成或实际作者身份。'}

def validate_history_ref(ref):
    if not isinstance(ref,dict) or set(ref)!={'id','hash','document_id','revision'}:raise ValueError('写作历史引用无效')
    if not all(isinstance(ref[k],str) and 1<=len(ref[k])<=80 for k in ['id','document_id']) or not re.fullmatch('[0-9a-f]{64}',str(ref['hash'])):
        raise ValueError('写作历史引用无效')
    if type(ref['revision']) is not int or not 1<=ref['revision']<=100000:raise ValueError('写作历史版本无效')
    return ref

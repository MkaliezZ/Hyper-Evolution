"""Source-bound semantic review adapted from DeepTutor's assessment pattern.

Upstream: HKUDS/DeepTutor@1ea7df155447f4caf0e3abc86b3ff5395479cd4a,
learning/semantic_assessment.py (Apache-2.0; third_party/deeptutor).
Different policy: no model-confidence threshold becomes a formal teacher result.
"""
import hashlib,json

VERSION='teacher-prereview-1.0.0'
RULES={
    'basis':'只评价本次任务发布的目标、题目、标准和实际提交；不臆造学生能力或原题依据。',
    'semantics':'接受有依据的同义表达，检查否定和矛盾；不以关键词重合判对错。',
    'quotation':'引用必须逐字来自当前作品或文字材料；无法核验时删除候选引用，该维度降为未判定并明确提示教师。',
    'unknown':'缺少依据、声音、图面或语义有歧义时保留未判定，明确需要教师核对的内容。',
    'feedback':'先指出可观察表现，再说明一项最值得改的操作；保留学习者责任与外部帮助。',
    'authority':'模型结果是候选，不确认正式达标、官方分数或长期掌握；教师另行修改确认。',
    'commit':'模型调用后重新核对来源、当前配对、任务和提交版本；异常不写入正式评阅。'}

def descriptor():
    raw={'id':'learning.teacher_prereview','version':VERSION,'rules':RULES,
        'professional_validation':'NOT_REVIEWED','policy_indexes':['P02','P03','P06','P07','P08','P10']}
    return {**raw,'hash':hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}

def normalize_report(report,criteria,work,material,coverage):
    """Validate exact source quotes and downgrade unsupported modalities, not semantic truth."""
    result=json.loads(json.dumps(report,ensure_ascii=False));rows=result['dimensions']
    if len({r['criterion'] for r in rows})!=len(rows) or set(r['criterion'] for r in rows)!=set(criteria):raise ValueError('预审维度须与本次发布标准一一对应')
    for row in rows:
        if not row['observation'].strip():raise ValueError('模型缺少分项观察；不能只给状态标签')
        quote=row['evidence']
        if quote and quote not in work and quote not in material:raise ValueError('预审引用未出现在当前原答或文字材料中')
        if row['status']=='supported' and not quote:raise ValueError('支持性判断需要可回查的原文依据')
        if coverage['requires_unread_media']:
            if row['status']=='supported':row['status']='partial'
            if any(s in row['criterion'].lower() for s in ['发音','流利','声音','语音','录音','听辨','pronunciation','fluency']):row['status']='ungraded'
    result['dimensions']=sorted(rows,key=lambda r:criteria.index(r['criterion']))
    result['uncertainties']=list(dict.fromkeys(result['uncertainties']+coverage['limitations']))
    return result

def check_teacher_fields(fields,criteria,work,material,needs_sound=False,has_sound=False,sound_confirmed=False):
    if set(d['criterion'] for d in fields['dimensions'])!=set(criteria):raise ValueError('请保留并核对本次任务全部评价维度')
    for d in fields['dimensions']:
        if d['evidence'] and d['evidence'] not in work and d['evidence'] not in material:raise ValueError('教师引用须能在本次原答或文字材料中回查')
    if fields['outcome']=='meets_criteria':
        if any(d['status']!='supported' or not d['observation'].strip() for d in fields['dimensions']):raise ValueError('确认达标前，请逐项记录已有支持证据')
        if needs_sound and not (has_sound and sound_confirmed):raise ValueError('声音维度需有录音，并由教师明确确认已听取核对')

def discard_unverified_quotes(report,work,material):
    """Salvage an internal candidate without legitimizing invented evidence or support."""
    result=json.loads(json.dumps(report,ensure_ascii=False));notices=[]
    for row in result['dimensions']:
        quote=row['evidence']
        if (quote and quote not in work and quote not in material) or (row['status']=='supported' and not quote):
            row['evidence']='';row['status']='ungraded'
            notices.append('“'+row['criterion']+'”的模型引用未通过原文核对，已弃用该引用并保留未判定；请教师核对当前作品。')
    result['uncertainties']=list(dict.fromkeys(notices+result['uncertainties']))
    return result

"""K12 professional policy candidates. Pure judgments, not an execution or storage layer."""
import hashlib,json,re

VERSION='learning.k12_teaching@1.0.0'
SUBJECTS={
 'english':{'name':'英语','tracks':{'k12':'K12英语','study_abroad':'留学英语（托福 / 雅思）','materials':'英语资料学习'}},
 'mathematics':{'name':'数学','tracks':{'materials':'通用资料学习（未建设专用数学测评）'}},
 'science':{'name':'科学与理科','tracks':{'materials':'通用资料学习'}},
 'humanities':{'name':'人文与社会','tracks':{'materials':'通用资料学习'}},
 'other':{'name':'其他学科','tracks':{'materials':'通用资料学习'}}}
LEVELS={'primary':'小学','junior':'初中','senior':'高中'}
TYPES={'grammar_mcq':'语法选择','cloze':'完形','reading_mcq':'阅读选择','listening':'听力','reading_match':'信息匹配',
 'reading_response':'阅读表达','writing':'写作','writing_task':'写作任务','true_false':'判断','dialogue':'补全对话',
 'unscramble':'连词成句','seven_choose':'选句填空','grammar_fill':'语法填空'}
OPEN={'reading_response','writing','writing_task'}
CHOICE={'grammar_mcq','reading_mcq','listening'}
TRAPS=['张冠李戴','过度推断','意思相反','原文照搬','无关','语法形式错误']
CAUSES=['没看到信息','词义误判','推断越界','表达资源不足','偏离题意','语法形式','题目或设备问题']
SKILLS={
 'primary':['be动词主谓一致','名词词义','细节理解','句子组织','简单表达'],
 'junior':['动词时态','代词辨析','词义辨析','细节理解','推理判断','主旨大意','信息匹配','写作表达'],
 'senior':['时态与语态','语法语境','细节理解','推理判断','词句猜测','篇章连贯','写作表达']}
RULES=[
 {'id':'K01','condition':'选择K12学习','action':'根据学段、明确范围与本次目标选择题型，不因导入文件就宣称完整课标覆盖。','check':'来源、范围及可靠性随任务冻结；缺范围不补造教材进度。','on_unknown':'采用显式知识点试练，不宣称教材同步。'},
 {'id':'K02','condition':'准备发布题目','action':'逐题独立作答，逐个检验选项成立性、歧义及具体误读路径。','check':'答案一致、选项覆盖和审题指纹匹配；语义仍须实际审阅。','on_unknown':'保留待审，不能仅因格式通过发布。'},
 {'id':'K03','condition':'学生答错','action':'分开记录原答、错项类型、原因假设及补充验证证据。','check':'没有证据不确认真实错因；测后追问不能修改原成绩。','on_unknown':'原因保持未知，可先提出一个可区分的检查。'},
 {'id':'K04','condition':'评价目标是否达到','action':'施测前冻结目标与题号覆盖，独立目标测验和带帮助练习分开。','check':'待评、帮助、坏题或未覆盖均不确认达标；阈值明确为本次试行标准。','on_unknown':'结果待核对，不推断长期掌握或考试等级。'},
 {'id':'K05','condition':'下一次训练','action':'优先处理坏题与未评作品，再验证原因，选择与困难匹配的操作，最后用未见题检查。','check':'训练决定有实际作品依据，不从一个标签直接固定题型。','on_unknown':'推荐少量追问，不制造确定诊断。'},
 {'id':'K06','condition':'听力活动','action':'使用有来源的录音与配套原文，教师完整试听。','check':'哈希与实际录音匹配；真人来源是声明，不由技术校验认证。','on_unknown':'不自动合成替代或把文字正确当实际听辨。'}]

def policy():
    value={'id':VERSION,'rules':RULES,'professional_validation':'NOT_REVIEWED','parent_indexes':['P02','P03','P04','P05','P07','P08','P10'],
     'owner':'K12内容负责人待专业审定','good_case':'错选扩大范围的选项，先记录错法，再用限定词检查区分可能原因。',
     'bad_case':'一次误选就确认推断能力差，并把所有困难固定成连线训练。'}
    return {**value,'hash':hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}

def validate_draft(body):
    questions=body['questions'];ids=[q['id'] for q in questions]
    if len(set(ids))!=len(ids):raise ValueError('题号不能重复')
    if any(not c.strip() or len(c)>500 for c in body['criteria']):raise ValueError('评价标准须为1—500字')
    if any(not s.strip() or len(s)>1500 for s in body['supports']):raise ValueError('提示须为1—1500字')
    for q in questions:
        if q['type'] in CHOICE:
            if not 2<=len(q['options'])<=6 or len(q['key'])!=1 or q['key'][0] not in [chr(65+i) for i in range(len(q['options']))]:raise ValueError('选择题需完整选项和一个有效答案')
            wrong={chr(65+i) for i in range(len(q['options']))}-{q['key'][0]}
            if set(q['traps'])!=wrong or any(x not in TRAPS for x in q['traps'].values()):raise ValueError('每个错误选项须记录允许的干扰类型')
        elif q['type'] not in OPEN and not q['key']:raise ValueError('客观题须明确可接受答案；不支持任意同义答案自动判分')
        if any(not str(s).strip() or len(s)>2000 for s in q['options']+q['key']):raise ValueError('选项或答案过长、为空')
        if q['type'] in ['reading_mcq','reading_match','reading_response','seven_choose']:
            if not q['material'].strip():raise ValueError('阅读题须包含本题原始材料')
            if q['evidence'] and q['evidence'] not in q['material']:raise ValueError('阅读依据必须逐字来自本题材料')
        if q['type']=='listening' and not body.get('audio_id'):raise ValueError('听力需先导入实际录音')
    return {'status':'structure_checked','semantic_quality':'requires_review','policy':policy()}

def check_reviews(body,reviews):
    if {r['question_id'] for r in reviews}!={q['id'] for q in body['questions']} or len(reviews)!=len(body['questions']):raise ValueError('请逐题完成审校，不能漏题或重复')
    by_id={r['question_id']:r for r in reviews}
    for q in body['questions']:
        r=by_id[q['id']]
        if not r['basis'].strip() or not r['ambiguity_check'].strip():raise ValueError('请记录具体依据与替代解排查')
        if q['type'] in CHOICE:
            expected={chr(65+i) for i in range(len(q['options']))}
            if {c['option'] for c in r['choices']}!=expected or len(r['choices'])!=len(expected):raise ValueError('须审查所有选项')
            if [c['option'] for c in r['choices'] if c['defensible']]!=q['key']:raise ValueError('成立选项须恰好与原答案一致')
            for c in r['choices']:
                if not c['reasoning'].strip() or (not c['defensible'] and (len(c['why_not'].strip())<4 or len(c['next_step'].strip())<4)):raise ValueError('错项需具体误读路径、排除依据和补练动作')
    return {'policy_ref':policy(),'semantic_review':'teacher_declared','machine_proved_correct':False}

def grade(pack,answers):
    if not isinstance(answers,dict) or set(answers)-{q['id'] for q in pack['items']}:raise ValueError('作答须对应本次题号')
    rows=[]
    for q in pack['items']:
        value=answers.get(q['id'],'')
        if not isinstance(value,str) or len(value)>4000:raise ValueError('单题作答须为4000字以内的文字')
        norm=lambda x:' '.join(x.strip().casefold().split())
        correct=None if q.get('open_response') else norm(value) in [norm(x) for x in q['key']]
        rows.append({'id':q['id'],'answer':value,'correct':correct,'accepted':q['key'],'skill':q['skill'],'evidence':q['evidence'],
            'explanation':q['explanation'],'points':q.get('points',1),'selected_trap':q.get('traps',{}).get(value),'cause_state':'unknown'})
    objective=[r for r in rows if r['correct'] is not None];score=sum(r['points'] for r in objective if r['correct'])
    return {'status':'pending' if len(objective)!=len(rows) else 'reviewed','correct':None,'score':score,
     'total':sum(r['points'] for r in objective),'items':rows,'pending':[r['id'] for r in rows if r['correct'] is None],
     'weak_skills':sorted({r['skill'] for r in rows if r['correct'] is False}),
     'comment':'已核对客观作答；主观题与具体原因须另行评阅。','next_step':'先查看实际错法，再选择少量追问、补练或新题验证。',
     'meaning':'本次表现，不是已确认错因、长期掌握或考试等级。'}

def scope_check(text,scopes,exempt):
    words={w.casefold() for s in scopes for w in s['words']};tokens=set(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",text))
    unknown=sorted(w for w in tokens if w.casefold() not in words and w.casefold() not in {x.casefold() for x in exempt})
    reliable=bool(words) and all(s['content_reviewed'] and s['complete'] for s in scopes)
    return {'ok':not unknown if reliable else None,'unmatched_words':unknown,'status':'unmatched_requires_review' if unknown else 'no_unmatched_in_supplied_list',
     'meaning':'只核对提供词表的表面词形；未命中不直接判超纲。词形变化、专名及中文词注需人工核对。','reliable_scope_declared':reliable}

def next_step(report):
    if report['invalid_questions']:return {'action':'排除题目/设备问题并安排有效补测','basis':'有勘误或无效题；保留原成绩，不用其推断困难','method':'验证材料'}
    if report['pending_reviews']:return {'action':'先评阅主观作品','basis':'尚有未评内容，不能以未评分当零分','method':'评价与观察'}
    if report['unconfirmed_problems']:return {'action':'挑选少量代表错题做答后追问或对照检查','basis':'已有错误表现，原因尚未得到确认','method':'提问与探究'}
    if report['confirmed_problems']:return {'action':'围绕已确认原因设计一个关键操作，再用未见题验证','basis':'已有可回查的补充证据；练习形式仍须匹配目标','method':'针对困难练习'}
    return {'action':'按当前目标选择新情境应用或独立检查','basis':'当前范围未见明确待处理问题，不代表全部掌握','method':'应用与表达'}

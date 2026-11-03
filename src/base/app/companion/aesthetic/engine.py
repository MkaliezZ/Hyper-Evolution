"""Executable teaching decisions. Pure rules: no database, transport or model access.

General judgments choose/check a design; domain examples do not become universal
cognitive structures. A successful check is not professional validation.
"""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

VERSION = '0.3.0'
METHODS = {
    'understand': ('M01', '理解与讲解', '先用解释、例子或反例弄清概念，按需检查理解。', '用自己的话说明关键观点，指出依据和仍不确定之处。'),
    'inquire': ('M02', '提问与探究', '比较有依据的解释，允许保留问题，不以猜中教师答案为目标。', '提出一个可讨论的问题，比较两种解释及其依据，记录未知。'),
    'targeted': ('M03', '针对困难练习', '由困难假设决定关键操作，再选择形式、素材、帮助和目标任务验证。', ''),
    'apply': ('M04', '应用与表达', '保留完整成果与本人责任，分别检查作品质量和学习证据。', '在具体情境中运用资料，完成解释或作品，说明依据与限制。'),
    'review': ('M05', '复习与巩固', '尝试提取或再次使用，区分熟悉答案和在适当条件下重新完成。', '先尝试回忆或再用，再对照原资料，说明需要修订之处。'),
    'reflect': ('M06', '复盘与近期安排', '回看方法、作品和帮助条件，选择一项可以改变的下一步。', '指出本次一个有效做法、一个待确认问题和下一次小行动。'),
}
SCENES = {
    'general': {'name':'通用资料学习','operation':'用本领域合适的方式解释、判断或完成作品。',
        'form':'short_response','criteria':['回应本次目标','依据和过程可检查','区分已做到与仍不确定之处'],'evidence':'text'},
    'rhetorical_purpose': {'name':'英语修辞目的','operation':'判断特定信息在上下文中怎样服务作者的表达目的。',
        'form':'matching','criteria':['说明信息在上下文中的作用','作用判断有上下文支持','回到完整段落检验判断'],
        'evidence':'text','form_reason':'关系连线可使作用判断显性化；A—R—B 只属于此场景的候选拆解。'},
    'listening': {'name':'听力信息辨识','operation':'在连续声音中辨识目标信息，结合上下文检查判断。',
        'form':'audio_comparison','criteria':['依据实际录音定位信息','区分听辨困难和词义或推断困难','在未见录音中再次观察'],
        'evidence':'audio','form_reason':'听辨需要真实声音；转写只能辅助核对，不能替代听觉表现。'},
    'writing': {'name':'写作组织与修订','operation':'组织主张和支持，修订一段完整表达并说明改动理由。',
        'form':'draft_revision','criteria':['内容回应任务','结构和支持服务表达目的','能说明本人修订的依据'],
        'evidence':'text','form_reason':'保留首稿与修订稿，观察表达组织，不用关系连线代替写作。'},
    'speaking': {'name':'口语表达','operation':'在约定条件下表达观点，结合实际声音观察表达表现。',
        'form':'recorded_response','criteria':['表达回应情境','组织使听者可以理解','声音维度依据录音或直接观察'],
        'evidence':'audio_response','form_reason':'文本可支持内容观察；发音和流利度必须有声音或适当直接观察。'},
    'math_concept': {'name':'数学概念理解','operation':'用例子、反例和适用条件解释概念。',
        'form':'example_counterexample','criteria':['概念及条件表达准确','例子和反例有区分作用','解释能关联到推理步骤'],
        'evidence':'text','form_reason':'检验概念边界，不把英语修辞结构当作数学操作模型。'},
    'debugging': {'name':'程序调试理解','operation':'提出故障假设，解释一个可复核的验证和修订过程。',
        'form':'debug_trace','criteria':['假设关联观察','验证能区分可能原因','说明修改及测试范围'],
        'evidence':'text','form_reason':'本批只分析提供的代码或轨迹，不执行用户电脑上的命令。'},
    'visual_reading': {'name':'原图与图表阅读','operation':'依据原始图面区分可见观察、解释和未知。',
        'form':'visual_observation','criteria':['观察能定位到原图区域','解释与图中信息相符','不猜测不可见文字或被裁掉内容'],
        'evidence':'image','form_reason':'以原始像素为依据，模型描述与用户转写均是派生观察。'},
}

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def catalog():
    packs=[]
    for path in sorted((Path(__file__).parent/'packs').glob('P*.json')):
        value=json.loads(path.read_text(encoding='utf8'))
        index=value.get('design_index','')
        if not value.get('rules') or not value.get('examples') or index!=path.name[:3]:
            raise ValueError('规则包缺少判断或正反例')
        rule_ids=[r.get('rule_id') for r in value['rules']]
        if len(set(rule_ids))!=len(rule_ids) or any(not str(rid).startswith(index+'-R') for rid in rule_ids):
            raise ValueError('规则标识缺失或重复')
        if any(not all(r.get(k) for k in ['decision','check','on_unknown_or_failure']) for r in value['rules']):
            raise ValueError('规则必须包含决定、检查和不确定时的处理')
        packs.append({**value,'content_hash':fingerprint(value)})
    if {p['design_index'] for p in packs}!={f'P{i:02}' for i in range(1,11)}:raise ValueError('P01—P10 规则包不完整，停止装配')
    return packs

def compose(context):
    """Consumes trusted material/evidence facts assembled by the functional layer."""
    packs=catalog();rules={p['design_index']:{r['rule_id']:r for r in p['rules']} for p in packs}
    c=deepcopy(context);scene=deepcopy(SCENES[c.get('scenario','general')]);method=c.get('method','understand')
    mid,name,rationale,prompt=METHODS[method]
    goal=c.get('goal','').strip();obstacle=c.get('obstacle','').strip()
    operation=c.get('target_operation','').strip() or scene['operation']
    criteria=c.get('criteria') or scene['criteria']
    material=c.get('material',{});evidence=c.get('evidence',[]);checks=[]
    def check(pack,rule,status,decision,reason):
        source=rules[pack][pack+'-'+rule]
        checks.append({'instruction':source['decision'],'acceptance':source['check'],'on_unknown':source['on_unknown_or_failure'],'pack':pack,'rule_id':pack+'-'+rule,'status':status,'decision':decision,'rationale':reason})
    check('P01','R1','pass' if goal else 'needs_input',goal or '补充本次目标','只收集足以开始本次活动的信息，不要求完整档案。')
    check('P02','R1','pass' if evidence else 'needs_review',
          '使用当前授权作品提出可修正假设' if evidence else '尚无作品依据；困难只作为设计者假设',
          '一次错答可能有多种原因，不能将标签当作诊断。')
    check('P03','R1','needs_review','内容正确性与领域适用性需审阅','读取、引用匹配和专业核验是不同状态。')
    targeted_ok=method!='targeted' or all([obstacle,c.get('target_operation','').strip(),c.get('question','').strip(),c.get('criteria')])
    form_ok=not c.get('form') or c['form']==scene['form'] or bool(c.get('form_reason','').strip())
    check('P04','R2' if method=='targeted' else 'R1','pass' if targeted_ok and form_ok else 'needs_input',
          name+'：'+operation if targeted_ok and form_ok else '补齐困难、操作、任务和标准；更换形式时说明理由',rationale)
    kind=material.get('kind','none');required=scene['evidence']
    source_ok=bool(material.get('verified')) or method=='reflect'
    media_ok=required not in ['audio','image'] or kind==required
    check('P05','R3','pass' if source_ok and media_ok else 'needs_input',
          '使用绑定版本的'+kind+'来源；难度未标定' if source_ok and media_ok else '补充本场景所需的原始材料',
          scene.get('form_reason','内容服务目标，再考虑兴趣和外观。'))
    independent_conflict=c.get('independent_claim',False) and c.get('additional_help') not in [None,'','none','没有额外帮助']
    check('P06','R1','blocked' if independent_conflict else 'pass',
          c.get('learner_responsibility') or '本人完成约定的理解、判断与表达；额外贡献另行说明。',
          '正常协作不等于代做；帮助声明不被自动认定为独立证据。')
    check('P07','R1','pass','反馈先指出可观察表现，再给一项可执行修改','不用泛夸或一次倾倒全部错误替代反馈。')
    overclaim=c.get('proposed_conclusion','this_work')!='this_work'
    check('P08','R2','blocked' if overclaim else 'pass',
          '不允许从本次活动宣称长期掌握或官方等级' if overclaim else '只记录本次作品观察，正式判断由实际教师确认',
          '完成、模型输出和帮助后正确不能自动升级为稳定掌握。')
    check('P09','R1','pass',f"建议本次约 {c.get('minutes',10)} 分钟，可调整或停止",'时间是用户可调负担，不是精确掌握曲线。')
    check('P10','R1','pass','先按反馈修订；按目标选择新情境观察，方法变更保留候选','个人回流不自动发布跨人共享规则。')
    status='blocked' if any(x['status']=='blocked' for x in checks) else 'needs_input' if any(x['status']=='needs_input' for x in checks) else 'ready_for_use_with_review'
    used=packs
    return {'engine':'learning.policy.runtime','version':VERSION,'scenario_id':c.get('scenario','general'),
        'scenario_name':scene['name'],'subject':c.get('subject','general'),'goal':goal,
        'method':method,'method_id':mid,'name':name,'rationale':rationale,'operation':operation,
        'form':c.get('form') or scene['form'],'form_reason':c.get('form_reason') or scene.get('form_reason','选择能使本次目标操作可观察的载体。'),
        'question':c.get('question','').strip() or (prompt if method!='targeted' else ''),
        'criteria':criteria,'obstacle_hypothesis':obstacle or '未确定，不据此诊断能力',
        'hypothesis_source':'authorized_evidence_and_designer' if evidence else 'designer_statement_only',
        'normal_conditions':c.get('normal_conditions') or '可使用本次原始资料及正常澄清；额外帮助另行记录。',
        'learner_responsibility':c.get('learner_responsibility') or '本人承担目标操作，说明外部帮助。',
        'evidence_requirement':required,'evidence_refs':evidence,'material_ref':material.get('ref'),
        'verification':'按本次标准回查作品，必要时换材料或情境再观察；不自动确认长期掌握。',
        'policy_refs':[{'id':x['policy_id'],'version':x['version'],'hash':x['content_hash'],'index':x['design_index']} for x in used],
        'decisions':checks,'status':status,'professional_validation':'NOT_REVIEWED',
        'missing':[x['rule_id'] for x in checks if x['status']=='needs_input'],
        'precedence':['platform_authorization','general_learning_boundaries','subject_and_scene','user_adjustments'],
        'method_policy':json.loads((Path(__file__).parent/'packs/M03-targeted-practice.json').read_text(encoding='utf8')) if method=='targeted' else None,
        'review_required':['领域内容正确性','本次形式是否实际训练到目标操作','真实使用和学习效果']}

def check_assessment(plan,record,has_sound=False):
    """Check evidence conditions, not the semantic truth of teacher observations."""
    formal=record.get('outcome')=='meets_criteria'
    if formal and plan.get('scenario_id')=='speaking' and not has_sound:
        raise ValueError('口语声音维度缺少录音或已记录的直接观察，不能确认整体达标')
    if formal:
        supported={d.get('criterion') for d in record.get('dimensions',[]) if d.get('status')=='supported' and d.get('observation','').strip()}
        if supported!=set(plan.get('criteria',[])):raise ValueError('确认达标前，请逐项记录与发布标准对应的支持观察')
    return {'policy_version':plan.get('version'),'checks':['P07-R1','P08-R1','P08-R2'],
        'status':'conditions_checked','semantic_review':'teacher_responsibility','mastery_updated':False}

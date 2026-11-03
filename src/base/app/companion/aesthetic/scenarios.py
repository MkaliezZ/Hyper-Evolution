"""Candidate teaching decisions. Each method keeps its own operations and evidence."""
from copy import deepcopy

METHODS = {
    'understand': {'name':'理解与讲解','method_id':'M01','operation':'用自己的话说明关键观点，并区分已理解和仍不确定的部分。',
        'rationale':'先观察学习者怎样理解资料，必要时再解释或举反例；不预设需要刷题。',
        'prompt':'用自己的话概括资料的关键观点，引用一处依据，并写下一个仍不确定的问题。',
        'criteria':['关键观点与资料相符','能说明所引用内容怎样支持解释','能区分已知与疑问']},
    'targeted': {'name':'针对困难练习','method_id':'M03','operation':'针对已声明的困难完成相关操作，并用资料说明判断依据。',
        'rationale':'围绕困难假设选择操作和素材，反馈后再用目标任务检验；活动形式不固定为选择或连线。',
        'prompt':'围绕本次困难，完成老师或自己设定的问题，说明采用的步骤，并引用资料支持判断。',
        'criteria':['操作对应本次困难假设','步骤与依据可以检查','修订后能说明改变了什么']},
    'apply': {'name':'应用与表达','method_id':'M04','operation':'用资料完成一个具体情境下的表达或方案，说明依据与适用边界。',
        'rationale':'保留完整成果及学习者责任，分别检查作品质量和本人学习证据。',
        'prompt':'选择资料中的一个观点，给出应用情境，形成一段解释或小方案，并说明依据与限制。',
        'criteria':['成果回应所选情境','引用与推理支持自己的表达','能说明适用条件或限制']},
}


def options():
    return deepcopy(METHODS)


def design(method, goal, obstacle, question, source_ref,target_operation='',criteria=None):
    if method not in METHODS:
        raise ValueError('请选择理解、针对困难练习或应用表达')
    if method == 'targeted' and not obstacle.strip():
        raise ValueError('针对训练需要先说明困难假设；尚不确定时可以先选择理解资料')
    if method=='targeted' and (not target_operation.strip() or not question.strip() or not criteria):
        raise ValueError('针对训练请写清要练的操作、具体问题和完成标准；不要用通用题目替代专业设计')
    if criteria and any(not isinstance(c,str) or not c.strip() or len(c)>300 for c in criteria):raise ValueError('完成标准每项须为1—300字')
    m = deepcopy(METHODS[method])
    if target_operation.strip():m['operation']=target_operation.strip()
    if criteria:m['criteria']=[c.strip() for c in criteria]
    plan={'scenario_id':'reading.source_response','version':'1.0.0','validation':'candidate_not_domain_validated',
        'goal':goal,'obstacle_hypothesis':obstacle or '未确定，不据此诊断能力',
        'hypothesis_source':'task_designer_statement','method':method,**m,
        'question':question.strip() or m['prompt'],'source_ref':source_ref,
        'material_fit':{'scope':'本次所选片段','difficulty':'未标定，按实际表现调整','on_mismatch':'若材料遮蔽目标操作，应更换片段或方法'},
        'policy_refs':[{'id':'learning.reading_design','version':'1.0.0'},
                       {'id':'learning.evidence_boundary','version':'1.0.0'}],
        'normal_conditions':'可阅读原文、正常澄清问题；额外示范、提示或 AI 改写应另行记录。',
        'learner_responsibility':'本人解释、判断与表达；外部贡献不可记为本人独立表现。',
        'on_missing':'缺必要证据时保留未知，不能把完成或自动分数升级为稳定掌握。',
        'verification':'按目标先修订，必要时换片段或情境再次观察；不要求每次走完整测试流水线。',
        'good_example':'解释自己的判断并指出资料依据；需要帮助时如实记录。',
        'counterexample':'仅复制原文或 AI 完稿，仍被记为本人独立掌握。'}

    from base.app.companion.aesthetic.engine import compose
    decision=compose({'scenario':'general','goal':goal,'method':method,'obstacle':obstacle,
        'target_operation':m['operation'] if method!='targeted' else target_operation,'question':question,
        'criteria':m['criteria'],'material':{'kind':'text','verified':True,'ref':source_ref}})
    if decision['status'] in ['blocked','needs_input']:raise ValueError('规则装配未通过，请补充本次任务必要条件')
    plan['runtime_policy']=decision
    plan['policy_refs']+=decision['policy_refs']
    plan['version']='1.1.0'
    return plan

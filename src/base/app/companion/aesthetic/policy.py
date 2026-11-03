"""Executable evidence-boundary subset, not the whole professional Policy Pack."""
from copy import deepcopy

POLICY = {
    'id': 'learning.evidence_boundary', 'version': '1.0.0',
    'design_ref': 'general-companion-v0.2/P02/P03/P06/P08/P10',
    'professional_validation': 'NOT_REVIEWED',
    'scope': '授权证据、来源与结论边界；不是十个专业规则包已全面运行',
    'rules': [
        {'id': 'authorized_only', 'requires': '当前角色与仍有效的师生关系；仅必要的已提交作品和可见反馈'},
        {'id': 'source_bound', 'requires': '原件引用绑定版本；解析或读取成功不代表领域核验'},
        {'id': 'unknown_is_unknown', 'requires': '缺少帮助条件、场景规则或专业证据时明确未记录，不补造'},
        {'id': 'authority_separate', 'requires': '客观核对、模型建议、本人自评与教师明确判断分别表达'},
        {'id': 'no_mastery_inference', 'requires': '完成、核对分数、已讲解和摘要不升级为稳定掌握'},
    ],
    'not_implemented': ['十个专业规则包完整装配', '跨学科学科评价', '学习效果判断'],
}


def policy_descriptor():
    return deepcopy(POLICY)


def missing_conditions(task):
    # Existing records never recorded these. Absence must not be backfilled as independence.
    return ['scenario_policy_not_recorded', 'participation_conditions_not_recorded',
            'additional_help_not_recorded', 'dimension_evidence_contract_not_recorded']


def assessment_authority(evaluation, review_history, origin):
    if evaluation.get('review_state') == 'confirmed' and review_history:
        return 'signed_teacher_review' if origin == 'teacher' else 'local_maintainer_review'
    if evaluation.get('review_state') == 'automatic':
        return 'objective_check'
    return 'pending_or_unknown'

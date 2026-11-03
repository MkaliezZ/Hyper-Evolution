"""Shared teaching contract checks. Domain judgement remains in app/assessment.py."""
import json
from base.app import activities
from base.app.assessment import validate_activity


def teaching_rules():
    path = activities.ROOT / 'teaching.json'
    try:
        rules = json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, OSError) as error:
        raise ValueError('app/teaching.json 无法读取，请检查教学规则文件') from error
    if not isinstance(rules, dict) or not isinstance(rules.get('version'), str) or not rules['version'].strip():
        raise ValueError('app/teaching.json：需要非空version')
    roles = rules.get('roles')
    if not isinstance(roles, dict) or set(roles) != {'maintainer', 'learner'} or any(not isinstance(v, str) or not 0 < len(v.strip()) <= 80 for v in roles.values()):
        raise ValueError('teaching.roles：仅配置maintainer和learner两个权限组的称呼')
    principles = rules.get('principles')
    if not isinstance(principles, list) or not principles or not all(isinstance(v, str) and 0 < len(v.strip()) <= 2000 for v in principles):
        raise ValueError('teaching.principles：请填写教学约定列表')
    if not isinstance(rules.get('feedback_reference'), str) or not 0 < len(rules['feedback_reference'].strip()) <= 2000:
        raise ValueError('teaching.feedback_reference：请填写反馈参考')
    return rules


def validate_teaching_fields(draft):
    for field in ('assessment_version', 'teaching_version'):
        if field in draft and (not isinstance(draft[field], str) or not 0 < len(draft[field].strip()) <= 80):
            raise ValueError(field + '：须为1至80字的版本说明')
    for field in ('goal', 'deliverable'):
        if field in draft and (not isinstance(draft[field], str) or not 0 < len(draft[field].strip()) <= 20000):
            raise ValueError(field + '：须为1至20000字')
    sources = draft.get('sources', [])
    if not isinstance(sources, list) or len(sources) > 30:
        raise ValueError('sources：最多30条来源记录')
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError('sources：每条须为对象')
        for key in ('title', 'locator', 'version'):
            if not isinstance(source.get(key), str) or not 0 < len(source[key].strip()) <= 500:
                raise ValueError('sources.' + key + '：须为1至500字')
        if source.get('extraction_status') not in ('not_extracted', 'readable', 'failed') or source.get('verification_status') not in ('unverified', 'verified'):
            raise ValueError('sources：请区分抽取状态与人工核验状态')
        if source.get('verification_status') == 'verified' and not all(isinstance(source.get(k), str) and 0 < len(source[k].strip()) <= 200 for k in ('verified_by', 'verified_at')):
            raise ValueError('sources：标为已核验须记录verified_by和verified_at')
        for key in ('file', 'excerpt', 'note'):
            if key in source and (not isinstance(source[key], str) or len(source[key]) > 2000):
                raise ValueError('sources.' + key + '：须为最多2000字的文字')
        if 'sha256' in source:
            import re
            if not isinstance(source['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', source['sha256']):
                raise ValueError('sources.sha256：须为64位小写十六进制摘要')
        if source.get('verification_status') == 'verified' and 'sha256' not in source:
            raise ValueError('sources：已核验资料须保留sha256，以便识别所核验版本')


def check_activity(draft):
    validate_activity(draft)
    validate_teaching_fields(draft)
    warnings = []
    for key, label in [('goal', '学习目标'), ('deliverable', '成果/证据要求')]:
        if not draft.get(key):
            warnings.append('尚未单列' + label + '；建议补充。旧活动仍可运行。')
    if not draft.get('sources'):
        warnings.append('尚未记录来源与核验状态。')
    elif any(v['verification_status'] != 'verified' for v in draft['sources']):
        warnings.append('存在尚未人工核验的资料；可读取不代表知识正确。')
    return {'valid': True, 'warnings': warnings, 'semantic_quality_verified': False}

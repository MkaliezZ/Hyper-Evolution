"""Domain rules live here; the storage and access layer never knows the subject."""
from fractions import Fraction
import math
import re


def number(value):
    text = str(value).strip()
    if len(text) > 64 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d+)?|\d+/[1-9]\d*)', text):
        raise ValueError('请输入整数、小数或分数，例如 0.5 或 1/2')
    return Fraction(text)


def validate_activity(draft):
    if not isinstance(draft, dict):
        raise ValueError('活动必须是一个对象')
    for field in ('name', 'activity_title', 'instructions', 'criteria', 'next_step', 'material'):
        if not isinstance(draft.get(field), str) or not draft[field].strip() or len(draft[field]) > 20000:
            raise ValueError(f'{field}：请填写非空文字，最长20000字')
    if draft.get('mode') not in ('text', 'numeric'):
        raise ValueError('mode：请选择 text 或 numeric')
    if draft['mode'] == 'numeric':
        number(draft.get('expected', ''))
    rubric = draft.get('rubric', [])
    if not isinstance(rubric, list) or len(rubric) > 20:
        raise ValueError('rubric：最多20项评价维度')
    labels = set()
    for item in rubric:
        if not isinstance(item, dict) or not isinstance(item.get('label'), str) or not 0 < len(item['label'].strip()) <= 80:
            raise ValueError('rubric.label：请填写1至80字的维度名称')
        if item['label'] in labels or not valid_number(item.get('max_score')) or item['max_score'] <= 0:
            raise ValueError('rubric：名称不能重复，max_score必须为正数')
        labels.add(item['label'])
    structure_hint(draft, '')  # Also validate optional structure configuration.
    from base.teaching import validate_teaching_fields
    validate_teaching_fields(draft)
    return draft


def valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and abs(value) <= 1000000


def structure_hint(activity, answer):
    rule = activity.get('structure')
    if rule is None:
        return None
    if not isinstance(rule, dict):
        raise ValueError('structure：必须为对象')
    for field in ('sections', 'vague_phrases'):
        values = rule.get(field, [])
        if not isinstance(values, list) or len(values) > 30 or not all(isinstance(v, str) and 0 < len(v) <= 80 for v in values):
            raise ValueError(f'structure.{field}：最多30条非空短文字')
    low, high = rule.get('min_chars', 0), rule.get('max_chars', 20000)
    if type(low) is not int or type(high) is not int or not 0 <= low <= high <= 20000:
        raise ValueError('structure：字数范围须在0至20000内')
    count = len(re.sub(r'\s+', '', answer))
    return {'characters': count, 'missing_sections': [v for v in rule.get('sections', []) if v not in answer],
            'vague_phrases': [v for v in rule.get('vague_phrases', []) if v in answer], 'length_ok': low <= count <= high}


def evaluate_submission(activity, answer):
    if 'growth' in activity:
        from base.app.content import evaluate_base
        return evaluate_base(activity, answer)
    if activity['mode'] == 'text':
        result = {'status': 'pending', 'comment': '已收到，等待维护者依据活动要求反馈。', 'next_step': '收到反馈后可修订并再次提交。', 'correct': None}
        hint = structure_hint(activity, answer)
        if hint is not None:
            result['structure'] = hint
            missing = '、'.join(hint['missing_sections']) or '无'
            vague = '、'.join(hint['vague_phrases']) or '无'
            length = '符合范围' if hint['length_ok'] else '不符合范围'
            result['comment'] += f' 结构提示（不评分）：非空白字符{hint["characters"]}个，字数{length}；缺少段落：{missing}；模糊表述：{vague}。仅检查格式，不判断内容真实性、质量或能力达标。'
        return result
    correct = number(answer) == number(activity['expected'])
    return {'status': 'reviewed', 'correct': correct, 'comment': '数值等值，符合要求。' if correct else '数值暂不相符，请重新检查计算。', 'next_step': activity['next_step']}

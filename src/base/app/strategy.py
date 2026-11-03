"""Ordinary editable function, not a workflow engine or a mastery formula."""


def plan_next(profile, growth):
    if growth['encountered'] and not growth['open_activities']:
        return {'action': 'new_activity', 'suggestion': '已有活动均已归档；回顾记录，为同一学习者创建新的目标或活动。'}
    if growth['pending_submissions']:
        return {'action': 'review', 'suggestion': '先依据作品完成反馈，再决定修订或进入下一活动。'}
    if growth['needs_revision']:
        return {'action': 'revise', 'suggestion': '先按具体反馈修改作品，再提交；保留初稿作为对照。'}
    if growth['meets_criteria'] and not growth['independent_transfer']:
        return {'action': 'transfer', 'suggestion': '准备一个新情境，约定独立完成条件，再收集作品并人工核验。'}
    if growth['completed']:
        return {'action': 'confirm', 'suggestion': '已提交不等于达标；核对评价依据与证据，再确定下一目标。'}
    return {'action': 'start', 'suggestion': '从一个可观察的小目标开始；已有能力不清楚时先做简短诊断。', 'goal': profile.get('goal', '')}

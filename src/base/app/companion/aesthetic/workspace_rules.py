"""Scenario availability is a declared teaching boundary, not inferred expertise."""

def allowed_scenarios(subject):
    common={'general','writing','visual_reading'}
    if subject=='english':return common|{'rhetorical_purpose','listening','speaking'}
    if subject=='mathematics':return common|{'math_concept'}
    return common

def require_scenario(subject,scenario):
    if scenario not in allowed_scenarios(subject):
        raise ValueError('这个学习情境未在当前学科工作区启用，请选择本学科情境或通用资料学习')

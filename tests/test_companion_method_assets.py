import json
import pytest
from test_local_runtime import instance
from test_companion_evolution import call

def candidate(t,**kw):
    return call(t,'method.candidate',{'title':'先定位困难，再选择练习形式','problem':'学习者只会复述，难以解释观点与证据的关系',
        'intended_scope':'适用于需要解释观点和理由的短篇写作，不推广为所有题型的标准流程',
        'use_basis':'团队原创合成方法，不包含真实师生材料或受限原件',
        'provenance_statement':'作者声明为团队原创合成案例；未借用个人未授权作品',
        'deidentification_note':'没有人名、学校、联系信息、原始档案与作品，案例全部合成',
        'procedure':['先看实际作品能否提供理由','只练习最关键的一处连接，再换材料验证'],
        'acceptance':['观点与理由实际对应；只改文字表面不算达标'],
        'good_case':'短篇观点缺少理由时，用一个反例让学习者说明条件边界，而不是给整篇成稿',
        'bad_case':'把每种学科、每种语言困难都当成修辞目的关系连线，未观察实际问题',
        'evidence_limits':'只有合成案例，真实教学体验与学习效果未验证',**kw})['method']

def review(t,c,conclusion='pass_for_declared_scope',**kw):
    return call(t,'method.review',{'candidate_id':c['id'],'candidate_hash':c['content_hash'],'reviewer_name':'工程测试声明者',
        'expertise_statement':'工程流程测试，不声明英语教学资质或真实效果','use_basis_checked':True,
        'deidentification_checked':True,'cases_checked':True,'scope_checked':True,'conclusion':conclusion,
        'reason':'逐项核对合成案例，只验证记录流程与边界','human_confirmed':True,**kw})['method_review']

def publish(t,c,r):return call(t,'method.publish',{'candidate_id':c['id'],'review_id':r['id'],'publisher_name':'合成负责人',
    'publication_note':'仅用于工程流程测试，不授权自动教学规则生效','human_confirmed':True})['method_release']

def test_candidate_requires_review_then_explicit_local_release(tmp_path):
    t=instance(tmp_path,'teacher','T');c=candidate(t)
    with pytest.raises(ValueError):call(t,'method.export',{'candidate_id':c['id']})
    with pytest.raises(ValueError):review(t,c,deidentification_checked=False)
    r=review(t,c);released=publish(t,c,r)
    assert released['runtime_policy_changed'] is False and released['delivery']=='local_release_only'
    exported=call(t,'method.export',{'candidate_id':c['id']})
    assert exported['artifact']['sha256']==released['artifact']['sha256']
    assert not exported['contains_private_record_links'] and 'owner_device' not in json.dumps(exported['artifact'])
    review(t,c,'needs_revision')
    with pytest.raises(ValueError):publish(t,c,r)
    with pytest.raises(ValueError):call(t,'method.export',{'candidate_id':c['id']})
    r2=review(t,c);release2=publish(t,c,r2)
    assert release2['artifact']['version']==2 and release2['artifact']['asset_id']==released['artifact']['asset_id']

def test_role_scope_and_obvious_identifier_screening(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S')
    with pytest.raises(PermissionError):call(s,'method.list')
    for bad in ['联系方式 student@example.com','私人手机号 13812345678','本机路径 C:/Users/test/private']:
        with pytest.raises(ValueError):candidate(t,good_case=bad)
    c=candidate(t)
    with pytest.raises(ValueError):review(t,c,human_confirmed=False)
    assert not call(t,'method.read',{'candidate_id':c['id']})['releases']

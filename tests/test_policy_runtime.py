import copy
import pytest
from test_local_runtime import instance,pair,drain
from test_companion_study import material,create,call
from base.app.companion.aesthetic.engine import catalog,compose,check_assessment

def context(scenario='general',kind='text',**kw):
    return {'goal':'解释本次依据与适用条件','scenario':scenario,'method':'apply',
        'material':{'kind':kind,'verified':True,'ref':{'id':'synthetic'}},**kw}

def test_all_ten_loaded_packs_actually_supply_runtime_instructions(monkeypatch):
    packs=catalog();assert len(packs)==10
    decision=compose(context())
    assert {x['pack'] for x in decision['decisions']}=={f'P{i:02}' for i in range(1,11)}
    assert all(x['instruction'] and x['acceptance'] and x['on_unknown'] for x in decision['decisions'])
    changed=copy.deepcopy(packs);changed[0]['rules'][0]['decision']='Synthetic amended policy instruction'
    monkeypatch.setattr('base.app.companion.aesthetic.engine.catalog',lambda:changed)
    assert compose(context())['decisions'][0]['instruction']=='Synthetic amended policy instruction'

def test_different_learning_mechanisms_do_not_inherit_rhetorical_matching():
    cases=[('rhetorical_purpose','text','matching'),('listening','audio','audio_comparison'),
        ('writing','text','draft_revision'),('speaking','text','recorded_response'),
        ('math_concept','text','example_counterexample'),('debugging','text','debug_trace')]
    for scenario,kind,form in cases:
        out=compose(context(scenario,kind))
        assert out['form']==form
        if scenario!='rhetorical_purpose':assert 'A—R—B' not in str(out)
        assert out['professional_validation']=='NOT_REVIEWED'
    assert compose(context('listening'))['status']=='needs_input'

def test_policy_changes_outcome_when_practice_is_underspecified_or_claims_exceed_evidence():
    assert compose(context(method='targeted',obstacle='猜测困难'))['status']=='needs_input'
    assert compose(context(method='targeted',obstacle='猜测困难',target_operation='比较两种解释',
        question='哪个解释更符合已有观察？',criteria=['能说明判据']))['status']=='ready_for_use_with_review'
    assert compose(context(independent_claim=True,additional_help='AI代写主要内容'))['status']=='blocked'
    assert compose(context(proposed_conclusion='long_term_mastery'))['status']=='blocked'

def test_source_creation_really_freezes_policy_execution_and_legacy_feedback_cannot_skip_it(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s)
    m=material(t);tid=create(t,m,s.identity.id)['data']['task_id'];drain(t,s)
    policy=s.task(tid)['pack']['companion_plan']['runtime_policy']
    assert len(policy['decisions'])==10 and policy['material_ref']['source_hash']==m['source_hash']
    s.submit(tid,{},'Synthetic work.',[],'work');drain(s,t);drain(t,s)
    sid=t.task(tid)['attempts'][0]['id']
    with pytest.raises(ValueError,match='Policy Pack'):t.feedback(sid,'x','y','meets_criteria',None,'bypass')
    r=call(t,'assessment.record',{'task_id':tid,'submission_id':sid,'source_type':'teacher_review',
        'human_review_confirmed':True,'outcome':'needs_revision','comment':'观察不足','next_step':'补充依据'},s.identity.id,'review')
    assert r['data']['record']['evidence']['policy_execution']['version']==policy['version']

def test_text_does_not_support_a_speaking_sound_judgment():
    plan=compose(context('speaking'))
    record={'outcome':'meets_criteria','dimensions':[{'criterion':c,'status':'supported','observation':'Synthetic observation'} for c in plan['criteria']]}
    with pytest.raises(ValueError,match='声音维度'):check_assessment(plan,record,has_sound=False)
    assert check_assessment(plan,record,has_sound=True)['mastery_updated'] is False

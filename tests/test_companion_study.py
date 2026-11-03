import asyncio,copy,json
import pytest
from pydantic_ai.models.test import TestModel
from test_local_runtime import instance,pair,drain
from base.app.local_agent import run_agent
from base.app.content import make_drill

def call(r,operation,payload=None,peer=None,key='test'):
    return r.invoke_capability({'contract_version':'companion.capability.v2','request_id':key,'operation':operation,'payload':payload or {},'peer_id':peer})

def material(r):
    return call(r,'material.save',{'title':'Original passage','text':'Some nearby paths cooled while distant streets changed little. Check local conditions before drawing conclusions.','source':'Original synthetic teaching example'},key='material')['data']['material']

def create(r,m,peer=None,method='understand',key='activity',**kw):
    return call(r,'activity.create',{'material_id':m['id'],'revision':m['revision'],'source_hash':m['source_hash'],
                'goal':'Explain the supported claim','method':method,**kw},peer,key)

def test_material_versions_and_operation_retry(tmp_path):
    s=instance(tmp_path,'student','S');m=material(s)
    assert material(s)==m
    updated=call(s,'material.save',{'material_id':m['id'],'expected_revision':1,'title':'New','text':'Updated text.','source':'Original'},key='update')['data']['material']
    assert updated['revision']==2
    old=call(s,'material.read',{'material_id':m['id'],'revision':1})['data']
    assert old['superseded'] and old['text'].startswith('Some nearby')
    with pytest.raises(ValueError):call(s,'material.save',{'material_id':m['id'],'expected_revision':1,'title':'Bad','text':'x','source':'s'},key='stale')
    with pytest.raises(ValueError):call(s,'material.read',{'material_id':m['id'],'source_hash':'0'*64})

def test_method_specific_design_and_frozen_source(tmp_path):
    s=instance(tmp_path,'student','S');m=material(s)
    with pytest.raises(ValueError):create(s,m,method='targeted')
    with pytest.raises(ValueError):create(s,m,method='targeted',key='no-operation',obstacle='Cannot distinguish a claim from evidence')
    specific=create(s,m,method='targeted',key='specific',obstacle='Cannot distinguish a claim from evidence',
                    target_operation='Separate the claim from its supporting observation',question='Which observation supports the limited claim?',criteria=['The selected observation supports the claim'])
    assert specific['data']['plan']['operation']=='Separate the claim from its supporting observation'
    result=create(s,m,method='apply',key='apply');tid=result['data']['task_id']
    assert create(s,m,method='apply',key='apply')['data']['task_id']==tid
    plan=s.task(tid)['pack']['companion_plan']
    assert plan['method_id']=='M04' and '关系连线' not in plan['operation']
    assert plan['source_ref']['source_hash']==m['source_hash']
    call(s,'material.save',{'material_id':m['id'],'expected_revision':1,'title':'Changed','text':'Changed source','source':'Original'},key='new')
    assert s.task(tid)['pack']['stimulus'].startswith('Some nearby')

def test_teacher_assignment_conditions_ledger_and_signed_feedback(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s)
    m=material(t);result=create(t,m,s.identity.id);tid=result['data']['task_id'];drain(t,s)
    assert s.task(tid)['pack']['companion_plan']['policy_refs']
    s.submit(tid,{},'The distant streets changed little.',[],'first',{'normal_participation':'Read original text','additional_help':'Asked for clarification'})
    drain(s,t);drain(t,s)
    task=t.task(tid);sid=task['attempts'][0]['id']
    assert task['attempts'][0]['answer']['learning_conditions']['additional_help']=='Asked for clarification'
    record={'task_id':tid,'submission_id':sid,'source_type':'teacher_review','outcome':'needs_revision','comment':'Explain the conditions.','next_step':'Add an example.','human_review_confirmed':True}
    a=call(t,'assessment.record',record,s.identity.id,'review')
    assert call(t,'assessment.record',record,s.identity.id,'review')==a
    drain(t,s)
    entries=call(s,'assessment.list',{'task_id':tid})['data']['entries']
    assert len(entries)==1 and entries[0]['source_type']=='teacher_review'
    assert entries[0]['evidence']['learning_conditions']['declaration']=='learner_self_report'
    s.submit(tid,{},'Revised explanation with an example.',[],'second');drain(s,t);drain(t,s)
    assert len(s.task(tid)['attempts'])==2
    assert len(call(s,'assessment.list',{'task_id':tid})['data']['entries'])==1
    t.unpair(s.identity.id)
    with pytest.raises(PermissionError):call(t,'assessment.list',{'task_id':tid},s.identity.id)
    s.unpair(t.identity.id)
    with pytest.raises(PermissionError):call(s,'material.read',{'task_id':tid})

def test_assessment_authority_and_fabricated_quotes(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s)
    m=material(t);tid=create(t,m,s.identity.id)['data']['task_id'];drain(t,s)
    s.submit(tid,{},'My actual response',[],'first');drain(s,t);drain(t,s);sid=s.task(tid)['attempts'][0]['id']
    base={'task_id':tid,'submission_id':sid,'source_type':'self_report','outcome':'meets_criteria','comment':'x','next_step':'y'}
    with pytest.raises(PermissionError):call(s,'assessment.record',base)
    base.update(source_type='teacher_review',human_review_confirmed=True)
    with pytest.raises(PermissionError):call(s,'assessment.record',base)
    base['dimensions']=[{'criterion':s.task(tid)['pack']['companion_plan']['criteria'][0],'evidence':'Invented evidence'}]
    with pytest.raises(ValueError):call(t,'assessment.record',base,s.identity.id)


def test_formal_judgment_requires_supported_dimensions_and_archive_is_read_only(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S');pair(t,s)
    m=material(t);tid=create(t,m,s.identity.id)['data']['task_id'];drain(t,s)
    s.submit(tid,{},'The distant streets changed little.',[],'first');drain(s,t);drain(t,s)
    sid=t.task(tid)['attempts'][0]['id']
    data={'task_id':tid,'submission_id':sid,'source_type':'teacher_review','outcome':'meets_criteria',
          'comment':'Synthetic judgment','next_step':'Next context','human_review_confirmed':True}
    with pytest.raises(ValueError,match='逐项'):call(t,'assessment.record',data,s.identity.id,'missing-dimensions')
    data['dimensions']=[{'criterion':c,'observation':'Synthetic observed support','status':'supported'} for c in t.task(tid)['pack']['companion_plan']['criteria']]
    assert call(t,'assessment.record',data,s.identity.id,'supported')['data']['record']['outcome']=='meets_criteria'
    t.set_task_state(tid,'archived');drain(t,s)
    with pytest.raises(ValueError):call(s,'assessment.record',{'task_id':tid,'submission_id':sid,'source_type':'self_report','comment':'x','next_step':'y'})

def test_bank_preview_confirmation_dedup_and_review_not_inherited(tmp_path):
    t=instance(tmp_path,'teacher','T');pack=make_drill('toefl','predeparture',seed='bank')
    p=call(t,'bank.preview',{'format':'json','content':json.dumps([pack,pack])},key='preview')['data']
    assert p['duplicates_in_file']==1 and not t.service.resources()
    commit={'preview_id':p['id'],'preview_hash':p['preview_hash']}
    first=call(t,'bank.commit',commit,key='confirm')['data']
    assert len(first['imported'])==1 and first['status']=='pending_review'
    assert call(t,'bank.commit',commit,key='confirm')['data']==first
    assert len(call(t,'bank.commit',commit,key='again')['data']['skipped_existing'])==1
    stored=t.service.resources()[0];assert stored['status']=='pending_review' and stored['source']['verification_status']=='unverified'
    assert 'review' not in stored
    bad=copy.deepcopy(commit);bad['preview_hash']='0'*64
    with pytest.raises(ValueError):call(t,'bank.commit',bad,key='tamper')

def test_csv_bad_rows_and_student_bank_denied(tmp_path):
    t=instance(tmp_path/'t','teacher','T');s=instance(tmp_path/'s','student','S')
    csv='title,stimulus,exam,task_type,kind,prompt,options,answer,evidence,explanation,skill,source_title\nDemo,Starts at ten.,toefl,daily_life,mcq,When?,At ten|At noon,A,at ten,Explanation,detail,Original\n'
    preview=call(t,'bank.preview',{'format':'csv','content':csv},key='csv')['data']
    assert len(preview['packs'])==1 and not preview['errors']
    invalid=call(t,'bank.preview',{'format':'csv','content':csv.replace(',A,',',Z,')},key='invalid')['data']
    assert invalid['errors'] and invalid['status']=='blocked'
    with pytest.raises(ValueError):call(t,'bank.commit',{'preview_id':invalid['id'],'preview_hash':invalid['preview_hash']},key='badcommit')
    with pytest.raises(PermissionError):call(s,'bank.preview',{'format':'csv','content':csv})

def test_reading_model_quotes_bound_and_no_model_grading(tmp_path):
    s=instance(tmp_path,'student','S');m=material(s)
    source={'material_id':m['id'],'revision':1,'source_hash':m['source_hash']}
    model=TestModel(custom_output_args={'message':'原文强调效果有范围。','citations':['distant streets changed little'],'next_steps':['用自己的话解释限制。']})
    out=asyncio.run(run_agent(s,{'mode':'reading','source':source},model))
    assert out['tools_used']==['get_reading_source']
    assert out['output']['citations'][0]['source_ref']['source_hash']==m['source_hash']
    assert not out['automatic_teacher_judgement']
    bad=TestModel(custom_output_args={'message':'x','citations':['Fake quotation not in original'],'next_steps':['x']})
    with pytest.raises(ValueError,match='引用'):asyncio.run(run_agent(s,{'mode':'reading','source':source},bad))

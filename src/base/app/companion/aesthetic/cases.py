"""Policy examples and engineering assertions, distinct from professional review."""
import json,re
from pathlib import Path
from base.app.companion.aesthetic.engine import catalog,compose,fingerprint,VERSION

def validate_suite(value):
    ids=[c['case_id'] for c in value['cases']]
    if len(set(ids))!=len(ids) or {c['pack'] for c in value['cases']}!={f'P{i:02}' for i in range(1,11)}:
        raise ValueError('案例标识或十包覆盖不完整')
    if any({c['kind'] for c in value['cases'] if c['pack']==p}!={'positive','counterexample'} for p in {c['pack'] for c in value['cases']}):
        raise ValueError('每包需要正例和反例')
    if any(not all(c.get('evidence_bundle',{}).get(k) for k in ['original_text','learner_work','candidate_response','source']) for c in value['cases']):
        raise ValueError('案例缺少原文、作品、候选做法或来源')
    for c in value['cases']:
        assertions=c.get('expected',{})
        if not assertions or 'decisions.'+c['pack']+'.status' not in assertions:raise ValueError('每例必须检查本包的实际决定，不能空断言通过')
        if any(not re.fullmatch(r'decisions\.P(?:0[1-9]|10)\.status|status|form|professional_validation',path)
               or not isinstance(expected,str) or not expected for path,expected in assertions.items()):raise ValueError('案例检查字段或预期无效')
    return value

def case_catalog(pack=None):
    value=validate_suite(json.loads((Path(__file__).parent/'cases/learning-policy-cases.v1.json').read_text(encoding='utf8')))
    return {**value,'suite_hash':fingerprint(value),'cases':[c for c in value['cases'] if pack is None or c['pack']==pack]}

def binding():
    return {'engine_version':VERSION,'case_suite_hash':case_catalog()['suite_hash'],
        'packs':{p['design_index']:p['content_hash'] for p in catalog()}}

def run_cases(pack=None):
    suite=case_catalog(pack);results=[]
    for case in suite['cases']:
        plan=compose(case['context']);flat={**plan,'decisions':{d['pack']:d for d in plan['decisions']}}
        checks=[]
        for path,expected in case['expected'].items():
            actual=flat
            for key in path.split('.'):actual=actual.get(key) if isinstance(actual,dict) else None
            checks.append({'path':path,'expected':expected,'actual':actual,'passed':actual==expected})
        results.append({'case_id':case['case_id'],'pack':case['pack'],'checks':checks,
            'engineering_passed':all(c['passed'] for c in checks),'professional_acceptance':case['professional_acceptance'],
            'actual_decision':next(d for d in plan['decisions'] if d['pack']==case['pack']),
            'professional_status':'NOT_REVIEWED'})
    return {'binding':binding(),'binding_hash':fingerprint(binding()),'cases':results,
        'engineering_passed':all(c['engineering_passed'] for c in results),
        'professional_status':'NOT_REVIEWED','learning_effect':'NOT_TESTED'}

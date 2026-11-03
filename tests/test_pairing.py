import concurrent.futures
import hashlib
import time
import pytest
from fastapi.testclient import TestClient
from base.app.growth import GrowthService
from growth.web import create_app

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'data')) as c: yield c

def auth(p): return {'Authorization':'Bearer '+p['access']}
def owner(c): return {'X-Owner-Token':c.app.state.service.base.owner_token}
def new(c): return c.post('/api/enroll',json={'name':'合成配对学生','exam':'toefl','stage':'enrolled'}).json()
def code(c,**fields):
    r=c.post('/api/teacher/pair-codes',headers=owner(c),json=fields)
    assert r.status_code==200
    return r.json()

def test_role_choice_is_not_authority_and_unpaired_student_is_private(client):
    p=new(client); id=p['person']['id']
    assert p['person']['teacher'] is None
    assert client.post('/api/teacher/pair-codes',headers=auth(p),json={}).status_code==403
    assert client.get('/api/teacher',headers=owner(client)).json()['learners']==[]
    assert client.post('/api/teacher/assign',headers=owner(client),json={'learner_id':id,'purpose':'diagnostic','request_key':'x'}).status_code==403
    assert client.post('/api/teacher/students/'+id+'/link',headers=owner(client)).status_code==403
    assert client.post('/api/teacher/generate',headers=owner(client),json={'learner_id':id}).status_code==403
    assert client.post('/api/activities',headers=auth(p),json={'purpose':'diagnostic','request_key':'own'}).status_code==200

def test_pairing_preserves_work_revokes_teacher_and_reconnects(client):
    p=new(client); id=p['person']['id']
    task=client.post('/api/activities',headers=auth(p),json={'purpose':'writing','request_key':'original'}).json()
    submitted=client.post('/api/activities/'+task['id']+'/submit',headers=auth(p),json={'text':'Synthetic original work','request_key':'work'}).json()
    sid=submitted['attempts'][0]['id']
    invite=code(client)
    result=client.post('/api/pairing/redeem',headers=auth(p),json={'code':invite['code'].lower()})
    assert result.status_code==200 and result.json()['person']['teacher']['name']=='伴学老师'
    assert client.get('/api/teacher',headers=owner(client)).json()['learners'][0]['tasks'][0]['id']==task['id']
    feedback={'comment':'合成配对反馈','next_step':'补充具体证据','judgement':'needs_revision','request_key':'f'}
    assert client.post('/api/teacher/feedback/'+sid,headers=owner(client),json=feedback).status_code==200
    assert client.post('/api/pairing/leave',headers=auth(p)).json()['records_preserved']
    assert client.get('/api/teacher',headers=owner(client)).json()['learners']==[]
    assert client.post('/api/teacher/feedback/'+sid,headers=owner(client),json={**feedback,'request_key':'f2'}).status_code==403
    assert client.post('/api/teacher/state/'+task['id'],headers=owner(client),json={'state':'paused'}).status_code==403
    own=client.get('/api/activities/'+task['id'],headers=auth(p)).json()
    assert own['attempts'][0]['evaluation']['comment']=='合成配对反馈'
    again=code(client)
    assert client.post('/api/pairing/redeem',headers=auth(p),json={'code':again['code']}).status_code==200
    assert len(client.get('/api/teacher',headers=owner(client)).json()['learners'][0]['tasks'])==1

def test_personal_code_recovers_same_profile_once_and_does_not_merge(client):
    p=client.post('/api/teacher/students',headers=owner(client),json={'name':'老师建档','exam':'ielts','stage':'application'}).json()
    invite=code(client,learner_id=p['person']['id'])
    other=new(client)
    assert client.post('/api/pairing/redeem',headers=auth(other),json={'code':invite['code']}).status_code==400
    first=client.post('/api/pairing/redeem',json={'code':invite['code']})
    assert first.status_code==200 and first.json()['person']['id']==p['person']['id']
    assert client.get('/api/me',headers=auth(p)).status_code==403
    assert client.get('/api/me',headers=auth(first.json())).status_code==200
    assert client.post('/api/pairing/redeem',json={'code':invite['code']}).status_code==400
    assert client.get('/api/me',headers=auth(other)).json()['person']['teacher'] is None

def test_expired_revoked_and_hashed_codes(client):
    s=client.app.state.service
    p=new(client)
    invitation=code(client)
    digest=hashlib.sha256(invitation['code'].replace('-','').encode()).hexdigest()
    with s.base.db() as db:
        row=db.execute('SELECT * FROM hd_pair_codes WHERE id=?',(invitation['id'],)).fetchone()
        assert row['digest']==digest and invitation['code'] not in str(dict(row))
        db.execute('UPDATE hd_pair_codes SET expires=? WHERE id=?',(int(time.time())-1,invitation['id']))
    assert client.post('/api/pairing/redeem',headers=auth(p),json={'code':invitation['code']}).status_code==400
    invitation=code(client)
    client.post('/api/teacher/pair-codes/'+invitation['id']+'/revoke',headers=owner(client))
    assert client.post('/api/pairing/redeem',headers=auth(p),json={'code':invitation['code']}).status_code==400

def test_parallel_redemption_is_single_use_and_unpaired_stays_private_after_restart(tmp_path):
    s=GrowthService(tmp_path)
    a=s.create_learner('合成A',paired=False); b=s.create_learner('合成B',paired=False)
    invitation=s.create_pair_code()
    def use(person):
        try: return s.redeem_pair_code(invitation['code'],person['person']['id'])['paired']
        except ValueError: return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(use,[a,b]))
    assert sorted(results)==[False,True]
    restored=GrowthService(tmp_path)
    assert len(restored.teacher_overview()['learners'])==1
    paired=restored.teacher_overview()['learners'][0]['person']['id']
    restored.unpair(paired)
    assert GrowthService(tmp_path).teacher_overview()['learners']==[]

def test_bad_code_rate_limit_and_invitation_needs_profile(client):
    s=client.app.state.service
    invitation=code(client)
    assert client.post('/api/pairing/redeem',json={'code':invitation['code']}).json()['needs_profile']
    for _ in range(10): assert client.post('/api/pairing/redeem',json={'code':'BAD-CODE'}).status_code==400
    blocked=client.post('/api/pairing/redeem',json={'code':invitation['code']})
    assert '10分钟' in blocked.json()['error']

def test_legacy_migration_preserves_original_teacher_links_only_once(tmp_path):
    from base.core import Store
    store=Store(tmp_path)
    person=store.save_learner('旧版合成学生',{})
    with store.db() as db:
        db.execute("CREATE TABLE hd_people(id TEXT PRIMARY KEY,exam TEXT,stage TEXT,revision INTEGER DEFAULT 1,demo INTEGER DEFAULT 0,notes TEXT DEFAULT '',goal TEXT DEFAULT '{}')")
        db.execute("INSERT INTO hd_people(id,exam,stage) VALUES (?,'ielts','application')",(person['id'],))
    s=GrowthService(tmp_path)
    assert s.require_paired(person['id'])==person['id']
    token=s.capability(person['id'])
    s.unpair(person['id'])
    restart=GrowthService(tmp_path)
    assert restart.authorize(token)==person['id']
    assert restart.teacher_overview()['learners']==[]

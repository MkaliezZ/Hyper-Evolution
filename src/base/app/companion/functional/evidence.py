"""Read-only role projection over existing BASE and signed peer copies; no migration."""
import json
from base.app.companion.assets.references import reference
from base.app.companion.aesthetic.policy import assessment_authority, missing_conditions


def pick(value, names):
    return {k: value[k] for k in names if k in value}


def public_material(pack):
    value = pick(pack, ['id','title','exam','stage','task_type','blueprint','purpose','instructions','stimulus','audio'])
    value['items'] = [pick(i, ['id','kind','prompt','options','skill','word_limit']) for i in pack.get('items', [])]
    value['source'] = pick(pack.get('source', {}), ['kind','title','version','verification_status'])
    return value


def visible_evaluation(value):
    # Deliberately excludes accepted answers, teacher identities and arbitrary extra fields.
    out = pick(value, ['status','comment','next_step','judgement','score','total','correct',
                       'scores','max_total','evaluation_version','review_state','reviewed_at'])
    if isinstance(value.get('items'), list):
        out['items'] = [pick(i, ['id','correct','answer','skill']) for i in value['items']]
    return out


def stored_tasks(runtime, learner_id):
    """Read stored evaluation, never re-grade historical work with current Python code."""
    tasks = []
    for raw in runtime.service.tasks(learner_id):
        attempts = []
        for s in runtime.service.base.submissions(raw['id']):
            ev = s['evaluation']
            attempts.append({'id': s['id'], 'created': s['created'], 'answer': json.loads(s['answer']),
                             'evaluation': ev, 'review_history': s['review_history'],
                             'automatic': ev if ev.get('review_state') == 'automatic' else None})
        tasks.append({**pick(raw, ['id','learner_id','created','state']), 'origin': 'self',
                      'purpose': raw['snapshot']['growth']['purpose'],
                      'pack': raw['snapshot']['growth'], 'attempts': attempts})
    return tasks


def authorized_tasks(runtime, peer_id=None, task_id=None):
    """Current authorization is checked on EVERY read, including resolving old references."""
    if runtime.role == 'student':
        if peer_id is not None:
            raise PermissionError('学生证据只来自自己的本机档案')
        person = runtime.service.public_person(runtime.profile['learner_id'])
        local = stored_tasks(runtime, runtime.profile['learner_id'])
        with runtime.db() as db:
            remote = [json.loads(r['body']) for r in db.execute('SELECT body FROM local_remote_tasks ORDER BY created,id')]
        tasks = []
        excluded = 0
        for t in local + remote:
            if t.get('origin') == 'teacher':
                try:
                    peer = runtime.peer(t['peer_id'])
                    if peer['role'] != 'teacher':
                        raise PermissionError('配对角色无效')
                except PermissionError:
                    excluded += 1
                    continue
            tasks.append(t)
    else:
        runtime.require_role('teacher')
        if not peer_id:
            raise ValueError('请先选择一位已配对学生')
        peer = runtime.peer(peer_id)
        if peer['role'] != 'student':
            raise PermissionError('证据对象不是已配对学生')
        runtime.service.require_paired(peer['learner_id'])
        person = runtime.service.public_person(peer['learner_id'])
        with runtime.db() as db:
            ids = {r['task_id'] for r in db.execute('SELECT task_id FROM local_task_links WHERE peer_id=?', (peer_id,))}
        tasks = [{**t, 'origin': 'teacher', 'peer_id': peer_id} for t in stored_tasks(runtime, peer['learner_id']) if t['id'] in ids]
        excluded = 0
    if task_id is not None:
        tasks = [t for t in tasks if t['id'] == task_id]
        if not tasks:
            raise PermissionError('任务不在当前授权证据范围内')
    return person, sorted(tasks, key=lambda t: (t['created'], t['id'])), excluded


def project(runtime, task, attempt_limit):
    tid = task['id']
    origin = task.get('origin', 'self')
    # Teacher and student's local copies refer to the publishing device as task owner.
    publisher = task['peer_id'] if runtime.role == 'student' and origin == 'teacher' else runtime.identity.id
    owner = 'device:' + publisher
    records = {}

    def add(kind, rid, value):
        ref = reference(tid, kind, str(rid), owner, value)
        records[ref['asset_id']] = (ref, value)
        return ref

    material = public_material(task['pack'])
    snapshot = {'created': task['created'], 'purpose': task['purpose'], 'material': material}
    snapshot_ref = add('task_snapshot', tid, snapshot)
    source_ref = add('source_text', tid, {'text': material.get('stimulus', ''), 'source': material['source']})
    attempts = []
    selected = task.get('attempts', [])[-attempt_limit:]
    for a in selected:
        answer = pick(a.get('answer', {}), ['answers','text','learning_conditions'])
        answer['files'] = []
        for fid in a.get('answer', {}).get('files', []):
            try:
                f = runtime.service.file(fid)
                # task authorization is insufficient for an unrelated attachment ID.
                learner = runtime.profile.get('learner_id') if runtime.role == 'student' else runtime.peer(task['peer_id'])['learner_id']
                if f['learner_id'] != learner:
                    continue
                metadata = pick(f, ['id','mime','sha256'])
                answer['files'].append({'metadata': metadata, 'asset_ref': add('attachment', fid, metadata)})
            except KeyError:
                pass
        answer_ref = add('submission', a['id'], answer)
        history = []
        for r in a.get('review_history', []):
            value = visible_evaluation(r.get('evaluation', {}))
            history.append({'created': r.get('created'), 'evaluation': value,
                            'asset_ref': add('review', str(a['id'])+':'+str(r['id']), value)})
        evaluation = visible_evaluation(a.get('evaluation', {}))
        authority = assessment_authority(a.get('evaluation', {}), history, origin)
        # Legacy remote task payloads also contain a freshly re-computed `automatic`.
        # Only a stored automatic evaluation is eligible evidence here; once replaced
        # by teacher review its original automatic result may no longer be available.
        auto = evaluation if a.get('evaluation', {}).get('review_state') == 'automatic' else {}
        attempts.append({'id': a['id'], 'created': a['created'], 'answer': answer, 'answer_ref': answer_ref,
                         'evaluation': evaluation, 'evaluation_ref': add('evaluation', a['id'], evaluation),
                         'assessment_authority': authority, 'automatic': auto or None, 'review_history': history,
                         'historical_automatic': 'stored' if auto else 'not_preserved_or_not_applicable',
                         'conditions':a.get('answer',{}).get('learning_conditions','not_recorded'),
                         'additional_help':a.get('answer',{}).get('learning_conditions',{}).get('additional_help','not_recorded')})
    queue = []
    if runtime.role == 'student' and origin == 'teacher':
        for pending in runtime.pending_submissions(tid)[-attempt_limit:]:
            answer = pick(pending['body'], ['answers','text'])
            queue.append({'id': pending['id'], 'delivery': pending.get('delivery') or 'unknown', 'answer': answer,
                          'asset_ref': add('local_submission', pending['id'], answer),
                          'meaning': '本地提交队列；不自动合并为教师已确认的评价或新尝试'})
    view = {'id': tid, 'origin': origin, 'purpose': task['purpose'], 'state': task['state'],
            'created': task['created'], 'material': material, 'snapshot_ref': snapshot_ref, 'source_ref': source_ref,
            'attempts': attempts, 'local_submission_queue': queue, 'missing': missing_conditions(task),
            'coverage': {'attempts_total': len(task.get('attempts', [])), 'attempts_returned': len(attempts)},
            'quality': {'processing': 'readable', 'domain_review': material['source'].get('verification_status', 'unknown'),
                        'task_fit': 'unknown', 'meaning': '可读取不等于领域核验或教学有效'}}
    if task['pack'].get('companion_plan'):
        view['policy_decision']=task['pack']['companion_plan']
        view['missing']=['task_fit_requires_professional_review']
        if any(a['conditions']=='not_recorded' for a in attempts):view['missing'].append('participation_conditions_not_recorded')
        from base.app.companion.functional.study_store import ledger
        view['assessment_records']=ledger(runtime,tid)+task.get('companion_assessments',[])
    if task['pack'].get('academic'):view['subject_context']=task['pack']['academic']
    return view, records


def evidence_view(runtime, peer_id=None, task_id=None, task_limit=20, attempt_limit=5):
    person, tasks, excluded = authorized_tasks(runtime, peer_id, task_id)
    selected = tasks[-task_limit:]
    projected = [project(runtime, task, attempt_limit)[0] for task in selected]
    weak = {}
    for t in projected:
        if t.get('subject_context',{}).get('track')=='k12':continue
        if t['attempts']:
            for item in (t['attempts'][-1].get('automatic') or {}).get('items', []):
                if 'correct' in item and item.get('skill'):
                    weak.setdefault(item['skill'], []).append(item['correct'])
    return {'schema_version': 'companion.evidence.v1', 'subject': pick(person, ['exam','stage']),
            'goal': person.get('profile', {}).get('goal', ''), 'tasks': projected,
            'weak_skills': sorted(k for k,v in weak.items() if not all(v)),
            'coverage': {'tasks_total': len(tasks), 'tasks_returned': len(projected), 'excluded_revoked_tasks': excluded,
                         'truncated': len(tasks) > len(selected) or any(t['coverage']['attempts_total'] > t['coverage']['attempts_returned'] for t in projected)},
            'limits': ['客观核对不是稳定掌握或正式考试等级', '学习条件缺项如实保留，摘要不能代替原始证据']}

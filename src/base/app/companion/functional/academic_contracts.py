"""v7 subject entry and K12 teaching; v1-v6 remain unchanged."""
from typing import Literal
from pydantic import Field,model_validator
from base.app.companion.functional.study_contracts import Strict,StudyResult

class AcademicRequest(Strict):
    contract_version: Literal['companion.capability.v7']
    request_id: str=Field(min_length=1,max_length=96)
    operation: str=Field(min_length=1,max_length=60)
    peer_id: str | None=Field(default=None,max_length=128)
    payload: dict=Field(default_factory=dict)

class AcademicResult(StudyResult):
    contract_version: Literal['companion.capability.v7']='companion.capability.v7'

class Select(Strict):
    subject: Literal['english','mathematics','science','humanities','other']='english'
    track: Literal['k12','study_abroad','materials']='k12'

class Identity(Strict):
    id: str=Field(min_length=1,max_length=100)

class Version(Identity):
    expected_revision: int=Field(ge=1)

class RouteSave(Strict):
    id: str | None=Field(default=None,max_length=100)
    expected_revision: int=Field(default=0,ge=0)
    title: str=Field(min_length=1,max_length=160)
    level: Literal['primary','junior','senior']
    grade: int=Field(ge=1,le=12)
    kind: Literal['curriculum','exam']='curriculum'
    goal: str=Field(min_length=1,max_length=1000)
    exam_name: str=Field(default='',max_length=160)
    exam_date: str=Field(default='',max_length=10)
    weekly_sessions: int=Field(default=2,ge=1,le=14)
    scope_order: int=Field(default=1,ge=1,le=1000)
    archived: bool=False

class RouteRead(Strict):
    route_id: str=Field(min_length=1,max_length=100)

class ScopeSave(RouteRead):
    id: str | None=Field(default=None,max_length=100)
    expected_revision: int=Field(default=0,ge=0)
    textbook: str=Field(min_length=1,max_length=160)
    unit: str=Field(min_length=1,max_length=100)
    order: int=Field(ge=1,le=1000)
    source: str=Field(min_length=1,max_length=1000)
    material_id: str | None=Field(default=None,max_length=100)
    words: list[str]=Field(default_factory=list,max_length=3000)
    phrases: list[str]=Field(default_factory=list,max_length=200)
    grammar: list[str]=Field(default_factory=list,max_length=200)
    complete: bool=False
    content_reviewed: bool=False
    @model_validator(mode='after')
    def lengths(self):
        if any(not x.strip() or len(x)>300 for x in self.words+self.phrases+self.grammar):raise ValueError('知识项不能留空或超过300字')
        return self

class ScopeCheck(RouteRead):
    scope_ids: list[str]=Field(default_factory=list,max_length=50)
    text: str=Field(min_length=1,max_length=30000)
    exempt_words: list[str]=Field(default_factory=list,max_length=100)

class Question(Strict):
    id: str=Field(min_length=1,max_length=40)
    type: Literal['grammar_mcq','cloze','reading_mcq','listening','reading_match','reading_response','writing','writing_task','true_false','dialogue','unscramble','seven_choose','grammar_fill']
    skill: str=Field(min_length=1,max_length=120)
    material: str=Field(default='',max_length=12000)
    prompt: str=Field(min_length=1,max_length=2000)
    options: list[str]=Field(default_factory=list,max_length=6)
    key: list[str]=Field(default_factory=list,max_length=10)
    evidence: str=Field(default='',max_length=2000)
    explanation: str=Field(default='',max_length=2000)
    traps: dict[str,str]=Field(default_factory=dict)
    points: float=Field(default=1,gt=0,le=100)

class DraftBody(Strict):
    title: str=Field(min_length=1,max_length=160)
    instructions: str=Field(min_length=1,max_length=2000)
    goal: str=Field(min_length=1,max_length=1000)
    source: str=Field(min_length=1,max_length=1000)
    questions: list[Question]=Field(min_length=1,max_length=80)
    criteria: list[str]=Field(min_length=1,max_length=8)
    supports: list[str]=Field(default_factory=list,max_length=10)
    scope_ids: list[str]=Field(default_factory=list,max_length=50)
    audio_id: str | None=Field(default=None,max_length=100)

class DraftSave(RouteRead):
    id: str | None=Field(default=None,max_length=100)
    expected_revision: int=Field(default=0,ge=0)
    body: DraftBody

class ChoiceReview(Strict):
    option: str=Field(min_length=1,max_length=1)
    defensible: bool
    reasoning: str=Field(min_length=4,max_length=2000)
    why_not: str=Field(default='',max_length=2000)
    next_step: str=Field(default='',max_length=2000)

class ItemReview(Strict):
    question_id: str=Field(min_length=1,max_length=40)
    basis: str=Field(min_length=4,max_length=2000)
    ambiguity_check: str=Field(min_length=4,max_length=2000)
    choices: list[ChoiceReview]=Field(default_factory=list,max_length=6)

class CandidateReview(Version):
    draft_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    questions: list[ItemReview]=Field(min_length=1,max_length=80)
    independent_answers: dict[str,list[str]]=Field(default_factory=dict)
    issues: list[str]=Field(default_factory=list,max_length=10)

class DraftReview(CandidateReview):
    human_review_confirmed: Literal[True]
    audio_listened: bool=False
    resolution_note: str=Field(default='',max_length=2000)

class SelfPractice(Version):
    pass

class Target(Strict):
    title: str=Field(min_length=1,max_length=160)
    threshold: float=Field(default=.8,gt=0,le=1)
    outcomes: dict[str,list[str]]
    coverage_note: str=Field(min_length=4,max_length=2000)

class TargetConfirm(Version):
    draft_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    target: Target
    human_review_confirmed: Literal[True]

class Publish(Version):
    mode: Literal['practice','target']='practice'
    human_review_confirmed: Literal[True]

class BankPick(RouteRead):
    skills: list[str]=Field(default_factory=list,max_length=20)
    count: int=Field(default=5,ge=1,le=80)
    scope_ids: list[str]=Field(default_factory=list,max_length=50)

class BankCompose(Version):
    title: str=Field(min_length=1,max_length=160)

class Work(Strict):
    task_id: str=Field(min_length=1,max_length=128)
    submission_id: str=Field(min_length=1,max_length=128)

class ProblemRecord(Work):
    expected_revision: int=Field(default=0,ge=0)
    question_id: str=Field(min_length=1,max_length=40)
    observation: str=Field(min_length=4,max_length=2000)
    cause: str=Field(default='',max_length=100)
    evidence_source: Literal['unverified','student_explanation','teacher_observation','diagnostic_check']='unverified'
    evidence_note: str=Field(default='',max_length=2000)
    student_quote: str=Field(default='',max_length=1200)
    check_task_id: str | None=Field(default=None,max_length=128)
    check_submission_id: str | None=Field(default=None,max_length=128)
    human_confirmed: bool=False

class Explain(Work):
    expected_revision: int=Field(default=0,ge=0)
    question_id: str=Field(min_length=1,max_length=40)
    student: str=Field(min_length=4,max_length=1000)
    tutor: str=Field(min_length=4,max_length=4000)
    next_step: str=Field(min_length=4,max_length=1000)
    quote: str=Field(default='',max_length=2000)
    human_confirmed: Literal[True]

class Score(Work):
    expected_revision: int=Field(default=0,ge=0)
    question_id: str=Field(min_length=1,max_length=40)
    score: float=Field(ge=0,le=100)
    rubric: dict[str,int]=Field(default_factory=dict)
    comment: str=Field(min_length=4,max_length=2000)
    evidence: str=Field(default='',max_length=2000)
    human_confirmed: Literal[True]

class Erratum(Strict):
    task_id: str=Field(min_length=1,max_length=128)
    question_id: str=Field(min_length=1,max_length=40)
    quote: str=Field(default='',max_length=2000)
    reason: str=Field(min_length=4,max_length=2000)
    invalid_item: bool=False
    human_confirmed: Literal[True]

class ClassSave(Strict):
    id: str | None=Field(default=None,max_length=100)
    expected_revision: int=Field(default=0,ge=0)
    title: str=Field(min_length=1,max_length=160)
    peers: list[str]=Field(min_length=1,max_length=50)
    archived: bool=False

class ClassAssign(Version):
    source_draft_id: str=Field(min_length=1,max_length=100)
    source_revision: int=Field(ge=1)

class MediaSave(Strict):
    name: str=Field(min_length=1,max_length=160)
    source: str=Field(min_length=1,max_length=1000)
    mime: Literal['audio/wav','audio/mpeg']
    data_base64: str=Field(min_length=1,max_length=17000000)
    speech_origin: Literal['unverified','human_declared']='unverified'

class ImportPreview(RouteRead):
    content: str=Field(min_length=1,max_length=500000)

class ImportCommit(Identity):
    preview_hash: str=Field(pattern=r'^[0-9a-f]{64}$')

PAYLOADS={'academic.select':Select,'route.save':RouteSave,'route.read':RouteRead,'scope.save':ScopeSave,'scope.read':Identity,'scope.list':RouteRead,'scope.check':ScopeCheck,
 'k12.draft.save':DraftSave,'k12.draft.read':Identity,'k12.draft.list':RouteRead,'k12.draft.review':DraftReview,'k12.draft.publish':Publish,
 'k12.draft.candidate_review':CandidateReview,'k12.draft.self_practice':SelfPractice,
 'k12.target.confirm':TargetConfirm,'k12.bank.list':RouteRead,'k12.bank.retire':Version,'k12.bank.pick':BankPick,'k12.bank.compose':BankCompose,
 'k12.problem.list':Work,'k12.problem.record':ProblemRecord,'k12.explain.save':Explain,'k12.score.record':Score,'k12.evidence.correct':Erratum,
 'k12.report':RouteRead,'k12.next':RouteRead,'k12.class.save':ClassSave,'k12.class.assign':ClassAssign,'k12.class.report':Identity,
 'k12.notifications.read':Identity,'k12.media.save':MediaSave,'k12.media.read':Identity,'k12.import.preview':ImportPreview,'k12.import.commit':ImportCommit,
 'k12.replenishment.list':RouteRead,'k12.class.candidates':RouteRead}
EMPTY={'academic.catalog','academic.context','route.list','k12.class.list','k12.notifications'}
from base.app.companion.functional.subject_contracts import SUBJECT_PAYLOADS
PAYLOADS.update(SUBJECT_PAYLOADS)

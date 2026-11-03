"""v10 teaching workflow contracts; v1-v9 remain frozen."""
from datetime import date
from typing import Literal
from pydantic import Field, model_validator
from base.app.companion.functional.study_contracts import Strict, StudyResult
from base.app.companion.functional.academic_contracts import Question, ItemReview

class TeachingRequest(Strict):
    contract_version: Literal['companion.capability.v10']
    request_id: str=Field(min_length=1,max_length=96)
    operation: str=Field(min_length=1,max_length=60)
    peer_id: str | None=Field(default=None,max_length=128)
    payload: dict=Field(default_factory=dict)

class TeachingResult(StudyResult):
    contract_version: Literal['companion.capability.v10']='companion.capability.v10'

class Empty(Strict):pass
class Identity(Strict):
    id: str=Field(min_length=1,max_length=100)
class Version(Identity):
    expected_revision: int=Field(ge=1)
class Route(Strict):
    route_id: str=Field(min_length=1,max_length=100)
class RosterSave(Strict):
    id: str | None=Field(default=None,max_length=100)
    expected_revision: int=Field(default=0,ge=0)
    name: str=Field(min_length=1,max_length=80)
    aliases: list[str]=Field(default_factory=list,max_length=10)
    note: str=Field(default='',max_length=1000)
    peer_id: str | None=Field(default=None,max_length=128)
class RosterResolve(Strict):
    query: str=Field(min_length=1,max_length=100)
class Unit(Strict):
    unit: str=Field(min_length=1,max_length=160)
    order: int=Field(ge=1,le=1000)
    words: list[str]=Field(default_factory=list,max_length=3000)
    phrases: list[str]=Field(default_factory=list,max_length=200)
    grammar: list[str]=Field(default_factory=list,max_length=200)
    complete: bool=False
class CatalogPreview(Strict):
    title: str=Field(min_length=1,max_length=160)
    source: str=Field(min_length=3,max_length=1000)
    units: list[Unit]=Field(min_length=1,max_length=200)
class CatalogExtract(Strict):
    title: str=Field(min_length=1,max_length=160)
    source: str=Field(min_length=3,max_length=1000)
    text: str=Field(min_length=1,max_length=50000)
class CatalogCommit(Version):
    content_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    human_review_confirmed: Literal[True]
class CatalogApply(Route):
    catalog_id: str=Field(min_length=1,max_length=100)
    catalog_revision: int=Field(ge=1)
    unit_orders: list[int]=Field(min_length=1,max_length=200)
class Lexical(Route):
    scope_ids: list[str]=Field(min_length=1,max_length=50)
    text: str=Field(min_length=1,max_length=30000)
    exemptions: list[str]=Field(default_factory=list,max_length=200)
    proper_names: list[str]=Field(default_factory=list,max_length=200)
class Section(Strict):
    title: str=Field(min_length=1,max_length=160)
    types: list[str]=Field(min_length=1,max_length=13)
    question_ids: list[str]=Field(min_length=1,max_length=80)
    count: int=Field(ge=1,le=80)
    points: float=Field(gt=0,le=8000)
    minutes: int=Field(ge=1,le=240)
class Blueprint(Version):
    template: Literal['k12-custom','toefl-2026','ielts-academic-computer']='k12-custom'
    sections: list[Section]=Field(min_length=1,max_length=20)
class Prepare(Route):
    focus: str=Field(min_length=1,max_length=120)
    count: int=Field(default=5,ge=1,le=80)
    scope_ids: list[str]=Field(default_factory=list,max_length=50)
    use_fallback: bool=True
    exclude_draft_id: str | None=Field(default=None,max_length=100)
class Patch(Version):
    questions: list[Question]=Field(min_length=1,max_length=80)
class Merge(Version):
    source_draft_id: str=Field(min_length=1,max_length=100)
class ReviewItems(Version):
    questions: list[ItemReview]=Field(min_length=1,max_length=80)
    human_review_confirmed: Literal[True]
    audio_listened: bool=False
    resolution_note: str=Field(default='',max_length=2000)
class ReviewFinalize(Version):
    human_review_confirmed: Literal[True]
    audio_listened: bool=False
    resolution_note: str=Field(default='',max_length=2000)
class BankExport(Version):
    personal_content_checked: Literal[True]
    reuse_source: str=Field(min_length=3,max_length=1000)
class BankRetire(Identity):
    reason: str=Field(min_length=3,max_length=1000)
class Forecast(Route):
    scope_ids: list[str]=Field(min_length=1,max_length=100)
    skills: list[str]=Field(min_length=1,max_length=20)
    count_per_skill: int=Field(default=5,ge=1,le=80)
    due_date: str=Field(min_length=10,max_length=10)
    @model_validator(mode='after')
    def valid(self):date.fromisoformat(self.due_date);return self
class PrepState(Version):
    state: Literal['planned','in_progress','done','paused']
class GoalSave(Strict):
    id: str | None=Field(default=None,max_length=100)
    expected_revision: int=Field(default=0,ge=0)
    title: str=Field(min_length=1,max_length=160)
    outcomes: list[str]=Field(min_length=1,max_length=20)
    threshold: float=Field(default=.8,gt=0,le=1)
class GoalBind(Version):
    goal_id: str=Field(min_length=1,max_length=100)
    goal_revision: int=Field(ge=1)
    outcomes: dict[str,list[str]]
    coverage_note: str=Field(min_length=4,max_length=2000)
    human_review_confirmed: Literal[True]
class Withdraw(Strict):
    task_id: str=Field(min_length=1,max_length=128)
    replacement_task_id: str | None=Field(default=None,max_length=128)
    reason: str=Field(min_length=3,max_length=1000)
    human_review_confirmed: Literal[True]
class Report(Route):
    audience: Literal['teacher','learner','parent']='teacher'
class WeeklyPlan(Route):
    start_date: str=Field(min_length=10,max_length=10)
    session_minutes: int=Field(default=20,ge=5,le=120)
    @model_validator(mode='after')
    def valid(self):date.fromisoformat(self.start_date);return self
class MemberMap(Strict):
    peer_id: str=Field(min_length=1,max_length=128)
    route_id: str=Field(min_length=1,max_length=100)
    scope_ids: list[str]=Field(default_factory=list,max_length=50)
class ClassAssign(Version):
    source_draft_id: str=Field(min_length=1,max_length=100)
    source_revision: int=Field(ge=1)
    mappings: list[MemberMap]=Field(min_length=1,max_length=50)
    human_review_confirmed: Literal[True]

PAYLOADS={
 'workflow.catalog':Empty,'roster.list':Empty,'roster.save':RosterSave,'roster.resolve':RosterResolve,
 'curriculum.preview':CatalogPreview,'curriculum.extract':CatalogExtract,'curriculum.commit':CatalogCommit,'curriculum.list':Empty,'curriculum.apply':CatalogApply,
 'lexical.check':Lexical,'blueprint.save':Blueprint,'blueprint.read':Identity,
 'workflow.prepare':Prepare,'workflow.resume':Identity,'workflow.merge':Merge,'draft.patch':Patch,'draft.review_items':ReviewItems,'draft.finalize_review':ReviewFinalize,
 'bank.export':BankExport,'bank.list':Empty,'bank.retire':BankRetire,
 'prep.forecast':Forecast,'prep.list':Route,'prep.state':PrepState,
 'goal.save':GoalSave,'goal.list':Empty,'goal.bind':GoalBind,'goal.history':Identity,
 'publication.withdraw':Withdraw,'report.read':Report,'report.weekly_plan':WeeklyPlan,
 'class.assign':ClassAssign,'class.report':Identity,'class.evidence':Route,
}

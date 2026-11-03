"""v5 optional plan changes and attributable writing. Earlier schemas are frozen."""
from typing import Literal
from datetime import date
from pydantic import Field,model_validator
from base.app.companion.functional.study_contracts import Strict,StudyResult

class EvolutionRequest(Strict):
    contract_version: Literal['companion.capability.v5']
    request_id: str=Field(min_length=1,max_length=96)
    operation: Literal['path.list','path.read','path.create','path.preview','path.confirm','path.publish',
        'writing.list','writing.read','writing.create','writing.suggestions','writing.suggest','writing.share_suggestion',
        'writing.preview','writing.confirm','writing.submit','writing.history',
        'method.list','method.read','method.candidate','method.review','method.publish','method.export']
    payload: dict=Field(default_factory=dict)
    peer_id: str | None=Field(default=None,max_length=128)

class EvolutionResult(StudyResult):
    contract_version: Literal['companion.capability.v5']='companion.capability.v5'

class Step(Strict):
    id: str=Field(min_length=1,max_length=64)
    action: str=Field(min_length=1,max_length=1000)
    minutes: int=Field(default=10,ge=1,le=120)
    due_date: str | None=Field(default=None,max_length=10)
    state: Literal['planned','in_progress','paused','done_declared']='planned'
    @model_validator(mode='after')
    def valid(self):
        if not self.id.strip() or not self.action.strip():raise ValueError('步骤不能留空')
        if self.due_date:date.fromisoformat(self.due_date)
        return self

class PathContent(Strict):
    title: str=Field(min_length=1,max_length=160)
    goal: str=Field(min_length=1,max_length=1000)
    steps: list[Step]=Field(min_length=1,max_length=20)
    task_ids: list[str]=Field(default_factory=list,max_length=20)
    reason: str=Field(min_length=3,max_length=2000)
    @model_validator(mode='after')
    def valid(self):
        if not all(s.strip() for s in [self.title,self.goal,self.reason]):raise ValueError('目标与理由不能留空')
        if len({s.id for s in self.steps})!=len(self.steps) or len(set(self.task_ids))!=len(self.task_ids):raise ValueError('步骤或任务不能重复')
        return self

class PathRead(Strict):
    path_id: str=Field(min_length=1,max_length=80)
    revision: int | None=Field(default=None,ge=1)

class PathPreview(PathContent):
    path_id: str=Field(min_length=1,max_length=80)
    expected_revision: int=Field(ge=1)

class PreviewConfirm(Strict):
    preview_id: str=Field(min_length=1,max_length=80)
    preview_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_revision: int=Field(ge=1)

class PathPublish(PathRead):
    expected_revision: int=Field(ge=1)

class WritingCreate(Strict):
    title: str=Field(min_length=1,max_length=160)
    goal: str=Field(min_length=1,max_length=1000)
    text: str=Field(default='',max_length=12000)
    task_id: str | None=Field(default=None,max_length=128)
    submission_id: str | None=Field(default=None,max_length=128)
    additional_help: str=Field(default='未说明',max_length=800)

class WritingRead(Strict):
    document_id: str=Field(min_length=1,max_length=80)
    revision: int | None=Field(default=None,ge=1)

class Edit(Strict):
    start: int=Field(ge=0)
    end: int=Field(ge=0)
    original: str=Field(max_length=3000)
    replacement: str=Field(max_length=3000)
    reason: str=Field(min_length=3,max_length=1500)
    @model_validator(mode='after')
    def valid(self):
        if self.start>self.end or self.original==self.replacement or not self.reason.strip():raise ValueError('建议没有有效变化')
        return self

class WritingSuggest(WritingRead):
    expected_revision: int=Field(ge=1)
    edits: list[Edit]=Field(min_length=1,max_length=6)
    contributor: Literal['external_suggestion','teacher_suggestion']='external_suggestion'

class SuggestionRead(Strict):
    suggestion_id: str=Field(min_length=1,max_length=80)

class WritingPreview(WritingRead):
    expected_revision: int=Field(ge=1)
    text: str | None=Field(default=None,max_length=12000)
    suggestion_ids: list[str]=Field(default_factory=list,max_length=6)
    contribution_note: str=Field(min_length=3,max_length=2000)
    additional_help: str=Field(default='未说明',max_length=800)
    @model_validator(mode='after')
    def valid(self):
        if (self.text is None)==(not self.suggestion_ids):raise ValueError('请选择建议或提交自己的新稿，不能混用')
        if len(set(self.suggestion_ids))!=len(self.suggestion_ids) or not self.contribution_note.strip():raise ValueError('修订说明或建议选择无效')
        return self

class WritingSubmit(WritingRead):
    expected_revision: int=Field(ge=1)
    additional_help: str=Field(default='未说明',max_length=800)

class WritingHistory(Strict):
    task_id: str=Field(min_length=1,max_length=128)
    history_id: str=Field(min_length=1,max_length=80)

class MethodCandidate(Strict):
    title: str=Field(min_length=3,max_length=160)
    problem: str=Field(min_length=5,max_length=2000)
    intended_scope: str=Field(min_length=5,max_length=2000)
    use_basis: str=Field(min_length=8,max_length=2000)
    provenance_statement: str=Field(min_length=8,max_length=2000)
    deidentification_note: str=Field(min_length=8,max_length=2000)
    procedure: list[str]=Field(min_length=1,max_length=8)
    acceptance: list[str]=Field(min_length=1,max_length=8)
    good_case: str=Field(min_length=10,max_length=4000)
    bad_case: str=Field(min_length=10,max_length=4000)
    evidence_limits: str=Field(min_length=8,max_length=2000)
    @model_validator(mode='after')
    def valid(self):
        if any(not s.strip() or len(s)>1500 for s in self.procedure+self.acceptance):raise ValueError('方法步骤与验收标准无效')
        return self

class MethodRead(Strict):
    candidate_id: str=Field(min_length=1,max_length=80)

class MethodReview(MethodRead):
    candidate_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    reviewer_name: str=Field(min_length=2,max_length=120)
    expertise_statement: str=Field(min_length=8,max_length=1500)
    use_basis_checked: bool
    deidentification_checked: bool
    cases_checked: bool
    scope_checked: bool
    conclusion: Literal['pass_for_declared_scope','needs_revision','reject']
    reason: str=Field(min_length=8,max_length=2000)
    human_confirmed: Literal[True]

class MethodPublish(MethodRead):
    review_id: str=Field(min_length=1,max_length=80)
    publisher_name: str=Field(min_length=2,max_length=120)
    publication_note: str=Field(min_length=8,max_length=2000)
    human_confirmed: Literal[True]

PAYLOADS={'path.read':PathRead,'path.create':PathContent,'path.preview':PathPreview,'path.confirm':PreviewConfirm,'path.publish':PathPublish,
    'writing.read':WritingRead,'writing.create':WritingCreate,'writing.suggestions':WritingRead,'writing.suggest':WritingSuggest,
    'writing.share_suggestion':SuggestionRead,'writing.preview':WritingPreview,'writing.confirm':PreviewConfirm,'writing.submit':WritingSubmit,'writing.history':WritingHistory,
    'method.read':MethodRead,'method.candidate':MethodCandidate,'method.review':MethodReview,'method.publish':MethodPublish,'method.export':MethodRead}

"""v6 teacher-owned pre-review, editable drafts and explicit publication. v1-v5 frozen."""
from typing import Literal
from pydantic import Field,model_validator
from base.app.companion.functional.study_contracts import Strict,StudyResult

class ReviewRequest(Strict):
    contract_version: Literal['companion.capability.v6']
    request_id: str=Field(min_length=1,max_length=96)
    operation: Literal['review.context','review.list','review.capture','review.start','review.job',
        'review.draft.save','review.draft.read','review.publish','review.settings','review.settings.save']
    payload: dict=Field(default_factory=dict)
    peer_id: str | None=Field(default=None,max_length=128)

class ReviewResult(StudyResult):
    contract_version: Literal['companion.capability.v6']='companion.capability.v6'

class Target(Strict):
    task_id: str=Field(min_length=1,max_length=128)
    submission_id: str=Field(min_length=1,max_length=128)

class TaskRead(Strict):
    task_id: str=Field(min_length=1,max_length=128)

class Dimension(Strict):
    criterion: str=Field(min_length=1,max_length=1500)
    observation: str=Field(default='',max_length=1500)
    evidence: str=Field(default='',max_length=1500,description='One exact continuous verbatim substring of CURRENT work or provided material. No corrections, ellipses, quotation marks, labels or joined excerpts. Empty when unavailable.')
    status: Literal['ungraded','partial','supported','needs_revision']='ungraded'

class ReviewFields(Strict):
    comment: str=Field(min_length=1,max_length=4000)
    next_step: str=Field(min_length=1,max_length=2000)
    outcome: Literal['ungraded','partial','needs_revision','meets_criteria']='ungraded'
    dimensions: list[Dimension]=Field(default_factory=list,max_length=10)
    @model_validator(mode='after')
    def valid(self):
        if not self.comment.strip() or not self.next_step.strip():raise ValueError('反馈和下一步不能留空')
        if len({d.criterion for d in self.dimensions})!=len(self.dimensions):raise ValueError('评价维度不能重复')
        return self

class PreReview(Strict):
    summary: str=Field(min_length=1,max_length=2000)
    comment: str=Field(min_length=1,max_length=4000)
    next_step: str=Field(min_length=1,max_length=2000)
    dimensions: list[Dimension]=Field(min_length=1,max_length=10)
    uncertainties: list[str]=Field(default_factory=list,max_length=10)
    @model_validator(mode='after')
    def valid(self):
        if any(not isinstance(x,str) or not 1<=len(x)<=1000 for x in self.uncertainties):raise ValueError('不确定项无效')
        return self

class Capture(Target):
    context_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    report: PreReview
    model_name: str=Field(min_length=1,max_length=160)

class Start(Target):
    pass

class JobRead(Strict):
    job_id: str=Field(min_length=1,max_length=128)

class DraftSave(Target):
    context_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    draft_id: str | None=Field(default=None,max_length=80)
    expected_revision: int=Field(default=0,ge=0)
    prereview_id: str | None=Field(default=None,max_length=80)
    fields: ReviewFields

class DraftRead(Strict):
    draft_id: str=Field(min_length=1,max_length=80)

class Publish(DraftRead):
    expected_revision: int=Field(ge=1)
    draft_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    human_review_confirmed: Literal[True]
    sound_review_confirmed: bool=False

class SettingsSave(Strict):
    automatic: bool

PAYLOADS={'review.context':Target,'review.list':TaskRead,'review.capture':Capture,'review.start':Start,'review.job':JobRead,
    'review.draft.save':DraftSave,'review.draft.read':DraftRead,'review.publish':Publish,'review.settings.save':SettingsSave}

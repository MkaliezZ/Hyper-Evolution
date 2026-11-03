"""v3 adds policy execution, original pages and bounded personal continuity.

v1/v2 schemas are unchanged. Payloads cannot supply trusted access/review flags.
"""
from typing import Literal
from pydantic import Field,model_validator
from base.app.companion.functional.study_contracts import Strict,StudyResult

class ContinuityRequest(Strict):
    contract_version: Literal['companion.capability.v3']
    request_id: str=Field(min_length=1,max_length=96)
    operation: Literal['policy.catalog','policy.plan','policy.task','page.save','page.list','page.read',
        'activity.create','memory.capture','memory.list','memory.correct','memory.visibility',
        'review.create','review.list','review.record','review.adjust']
    payload: dict=Field(default_factory=dict)
    peer_id: str | None=Field(default=None,max_length=128)

class ContinuityResult(StudyResult):
    contract_version: Literal['companion.capability.v3']='companion.capability.v3'

class Source(Strict):
    material_id: str | None=Field(default=None,max_length=64)
    page_id: str | None=Field(default=None,max_length=64)
    task_id: str | None=Field(default=None,max_length=128)
    revision: int | None=Field(default=None,ge=1)
    source_hash: str | None=Field(default=None,pattern=r'^[0-9a-f]{64}$')
    start: int=Field(default=0,ge=0)
    end: int | None=Field(default=None,ge=1)
    region: list[float] | None=Field(default=None,min_length=4,max_length=4)
    @model_validator(mode='after')
    def validate_source(self):
        if sum(x is not None for x in [self.material_id,self.page_id,self.task_id])!=1:
            raise ValueError('请选择一份本机资料、原图或已授权任务')
        if self.region and not (0<=self.region[0]<self.region[2]<=1 and 0<=self.region[1]<self.region[3]<=1):
            raise ValueError('原图区域应为有效的归一化矩形')
        return self

class PolicyPlan(Strict):
    source: Source | None=None
    goal: str=Field(min_length=1,max_length=1000)
    subject: str=Field(default='general',min_length=1,max_length=80)
    scenario: Literal['general','rhetorical_purpose','listening','writing','speaking','math_concept','debugging','visual_reading']='general'
    method: Literal['understand','inquire','targeted','apply','review','reflect']='understand'
    obstacle: str=Field(default='',max_length=1000)
    target_operation: str=Field(default='',max_length=1000)
    question: str=Field(default='',max_length=2000)
    criteria: list[str]=Field(default_factory=list,max_length=8)
    form: str=Field(default='',max_length=100)
    form_reason: str=Field(default='',max_length=1000)
    normal_conditions: str=Field(default='',max_length=1000)
    learner_responsibility: str=Field(default='',max_length=1000)
    minutes: int=Field(default=10,ge=2,le=120)
    independent_claim: bool=False
    additional_help: str=Field(default='',max_length=800)
    proposed_conclusion: Literal['this_work','long_term_mastery','official_exam_level']='this_work'
    @model_validator(mode='after')
    def criteria_valid(self):
        if any(not x.strip() or len(x)>300 for x in self.criteria):raise ValueError('完成标准须为1—300字')
        return self

class ActivityCreate(PolicyPlan):
    source: Source

class PageSave(Strict):
    title: str=Field(min_length=1,max_length=160)
    source: str=Field(min_length=1,max_length=500)
    data_base64: str=Field(min_length=1,max_length=2800000)
    caption: str=Field(default='',max_length=3000)
    page_id: str | None=Field(default=None,max_length=64)
    expected_revision: int | None=Field(default=None,ge=1)

class PageRead(Source):
    include_image: bool=True

class TaskRead(Strict):
    task_id: str=Field(min_length=1,max_length=128)

class MemoryCapture(Strict):
    task_ids: list[str]=Field(min_length=1,max_length=5)
    title: str=Field(default='学习札记',min_length=1,max_length=120)

class MemoryList(Strict):
    include_hidden: bool=False

class MemoryCorrect(Strict):
    memory_id: str=Field(min_length=1,max_length=64)
    expected_revision: int=Field(ge=1)
    body: str=Field(min_length=1,max_length=3000)
    allow_for_model: bool=False

class MemoryVisibility(Strict):
    memory_id: str=Field(min_length=1,max_length=64)
    hidden: bool

class ReviewCreate(TaskRead):
    prompt: str=Field(default='',max_length=1500)
    intervals: list[int]=Field(default_factory=lambda:[1,3,7,14],min_length=1,max_length=6)
    @model_validator(mode='after')
    def intervals_valid(self):
        if self.intervals!=sorted(set(self.intervals)) or any(x<1 or x>90 for x in self.intervals):
            raise ValueError('复习间隔须为1—90天的递增整数')
        return self

class ReviewList(Strict):
    include_paused: bool=False

class ReviewRecord(Strict):
    card_id: str=Field(min_length=1,max_length=64)
    expected_revision: int=Field(ge=1)
    response: str=Field(min_length=1,max_length=4000)
    rating: Literal['again','hard','good']
    additional_help: str=Field(default='未说明',max_length=800)

class ReviewAdjust(Strict):
    card_id: str=Field(min_length=1,max_length=64)
    expected_revision: int=Field(ge=1)
    paused: bool | None=None
    days_from_now: int | None=Field(default=None,ge=0,le=90)
    @model_validator(mode='after')
    def adjustment_present(self):
        if self.paused is None and self.days_from_now is None:raise ValueError('请说明改期或暂停安排')
        return self

PAYLOADS={'policy.plan':PolicyPlan,'policy.task':TaskRead,'page.save':PageSave,'page.read':PageRead,
    'activity.create':ActivityCreate,'memory.capture':MemoryCapture,'memory.list':MemoryList,
    'memory.correct':MemoryCorrect,'memory.visibility':MemoryVisibility,'review.create':ReviewCreate,
    'review.list':ReviewList,'review.record':ReviewRecord,'review.adjust':ReviewAdjust}

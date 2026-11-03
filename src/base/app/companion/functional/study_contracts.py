"""Additive v2 write capabilities; the v1 request/result schemas stay unchanged."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class StudyRequest(Strict):
    contract_version: Literal['companion.capability.v2']
    request_id: str=Field(min_length=1,max_length=96)
    operation: Literal['study.options','material.list','material.save','material.read','activity.create','assessment.list','assessment.record','bank.preview','bank.commit']
    payload: dict=Field(default_factory=dict)
    peer_id: str | None=Field(default=None,max_length=128)

class StudyResult(Strict):
    contract_version: Literal['companion.capability.v2']='companion.capability.v2'
    request_id: str
    operation: str
    status: Literal['completed','partial','needs_input','needs_review','unavailable','failed']
    data: dict
    decision_trace: dict
    commit_receipt: dict | None=None

class MaterialSave(Strict):
    title: str=Field(min_length=1,max_length=160)
    text: str=Field(min_length=1,max_length=60000)
    source: str=Field(min_length=1,max_length=500)
    material_id: str | None=Field(default=None,max_length=64)
    expected_revision: int | None=Field(default=None,ge=1)

class MaterialRead(Strict):
    material_id: str | None=Field(default=None,max_length=64)
    revision: int | None=Field(default=None,ge=1)
    source_hash: str | None=Field(default=None,pattern=r'^[0-9a-f]{64}$')
    task_id: str | None=Field(default=None,max_length=128)
    start: int=Field(default=0,ge=0)
    end: int | None=Field(default=None,ge=1)

class ActivityCreate(MaterialRead):
    goal: str=Field(min_length=1,max_length=1000)
    method: Literal['understand','targeted','apply']='understand'
    obstacle: str=Field(default='',max_length=1000)
    question: str=Field(default='',max_length=2000)
    target_operation: str=Field(default='',max_length=1000)
    criteria: list[str]=Field(default_factory=list,max_length=8)

class AssessmentList(Strict):
    task_id: str=Field(min_length=1,max_length=128)

class AssessmentRecord(AssessmentList):
    submission_id: str=Field(min_length=1,max_length=128)
    source_type: Literal['self_report','model_suggestion','teacher_review']
    outcome: Literal['ungraded','partial','needs_revision','meets_criteria']='ungraded'
    comment: str=Field(min_length=1,max_length=4000)
    next_step: str=Field(min_length=1,max_length=2000)
    dimensions: list[dict]=Field(default_factory=list,max_length=10)
    human_review_confirmed: bool=False

class LearningConditions(Strict):
    normal_participation: str=Field(default='',max_length=800)
    additional_help: str=Field(default='未说明',max_length=800)
    declaration: Literal['learner_self_report']='learner_self_report'

class BankPreview(Strict):
    format: Literal['csv','json']
    content: str=Field(min_length=1,max_length=400000)

class BankCommit(Strict):
    preview_id: str=Field(min_length=1,max_length=64)
    preview_hash: str=Field(pattern=r'^[0-9a-f]{64}$')

PAYLOADS={'material.save':MaterialSave,'material.read':MaterialRead,'activity.create':ActivityCreate,
          'assessment.list':AssessmentList,'assessment.record':AssessmentRecord,
          'bank.preview':BankPreview,'bank.commit':BankCommit}

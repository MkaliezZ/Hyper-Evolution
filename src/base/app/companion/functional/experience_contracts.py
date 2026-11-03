"""v11 experience selection and self-study composition. Identity roles remain unchanged."""
from typing import Literal
from pydantic import Field
from base.app.companion.functional.study_contracts import Strict,StudyResult
from base.app.companion.functional.continuity_contracts import ActivityCreate

class ExperienceRequest(Strict):
    contract_version: Literal['companion.capability.v11']
    request_id: str=Field(min_length=1,max_length=96)
    operation: Literal['experience.read','experience.select','self.context','self.start','self.feedback_context','self.reflect']
    peer_id: str | None=Field(default=None,max_length=128)
    payload: dict=Field(default_factory=dict)

class ExperienceResult(StudyResult):
    contract_version: Literal['companion.capability.v11']='companion.capability.v11'

class Empty(Strict):pass
class Select(Strict):
    experience: Literal['teacher','student','self']
class Work(Strict):
    task_id: str=Field(min_length=1,max_length=128)
    submission_id: str=Field(min_length=1,max_length=128)
class Reflection(Work):
    outcome: Literal['ungraded','partial','needs_revision']='ungraded'
    comment: str=Field(min_length=1,max_length=4000)
    next_step: str=Field(min_length=1,max_length=2000)
    schedule_review: bool=True

PAYLOADS={'experience.read':Empty,'experience.select':Select,'self.context':Empty,
    'self.start':ActivityCreate,'self.feedback_context':Work,'self.reflect':Reflection}

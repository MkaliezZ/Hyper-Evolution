from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,str_strip_whitespace=True)


class Requirement(Strict):
    requirement:str=Field(min_length=1,max_length=500)
    current_evidence:str=Field(default='',max_length=1000)
    gap:str=Field(default='',max_length=500)
    next_action:str=Field(default='',max_length=1000)
    completion_standard:str=Field(default='',max_length=1000)
    source_url:str=Field(default='',max_length=2000)
    @model_validator(mode='after')
    def url(self):
        if self.source_url and not self.source_url.startswith(('https://','http://')):raise ValueError('来源链接请用http或https地址')
        return self


class Content(Strict):
    current_situation:str=Field(min_length=1,max_length=2000)
    stage:Literal['exploring','preparing','acting','reviewing']='exploring'
    question:str=Field(default='',max_length=1000)
    strengths:str=Field(default='',max_length=2000)
    directions:str=Field(default='',max_length=2000)
    goal:str=Field(default='',max_length=1000)
    horizon:str=Field(default='',max_length=160)
    requirements:list[Requirement]=Field(default_factory=list,max_length=6)


class PlanningRequest(Strict):
    contract_version:Literal['companion.capability.v9']='companion.capability.v9'
    request_id:str=Field(min_length=1,max_length=128)
    operation:Literal['planning.context','planning.read','planning.save','planning.share']
    peer_id:str|None=Field(default=None,max_length=128)
    payload:dict=Field(default_factory=dict)


class Read(Strict):
    id:str=Field(pattern=r'^[a-f0-9]{32}$')


class Save(Strict):
    id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')
    expected_revision:int=Field(default=0,ge=0)
    content:Content
    task_ids:list[str]=Field(default_factory=list,max_length=10)
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.task_ids))!=len(self.task_ids):raise ValueError('作品不能重复选择')
        return self


class Share(Read):
    expected_revision:int=Field(ge=1)
    content_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    receiver_id:str|None=Field(default=None,max_length=128)


class PlanningResult(Strict):
    contract_version:Literal['companion.capability.v9']='companion.capability.v9'
    request_id:str
    operation:str
    status:Literal['completed']='completed'
    data:dict
    decision_trace:dict


PAYLOADS={'planning.read':Read,'planning.save':Save,'planning.share':Share}

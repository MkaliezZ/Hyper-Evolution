"""v8 local subject workspaces. Scope is resolved by the host, never by peer claims."""
from typing import Literal
from pydantic import Field
from base.app.companion.functional.study_contracts import Strict

class WorkspaceRequest(Strict):
    contract_version: Literal['companion.capability.v8']
    request_id: str=Field(min_length=1,max_length=128)
    operation: Literal['workspace.initialize','workspace.list','workspace.select','workspace.create','workspace.legacy.import']
    payload: dict=Field(default_factory=dict)
    peer_id: None=None

class WorkspaceResult(Strict):
    contract_version: Literal['companion.capability.v8']='companion.capability.v8'
    request_id: str
    operation: str
    status: Literal['completed']='completed'
    data: dict
    decision_trace: dict

class Select(Strict):
    subject: str=Field(pattern=r'^(english|mathematics|science|humanities|other|legacy|subject-[0-9a-f]{16})$')
    track: str=Field(default='materials',max_length=40)

class Create(Strict):
    name: str=Field(min_length=1,max_length=40)

class Import(Strict):
    subject: str=Field(pattern=r'^(english|mathematics|science|humanities|other|subject-[0-9a-f]{16})$')
    asset_kind: Literal['text','page']
    asset_id: str=Field(min_length=1,max_length=64)
    revision: int=Field(ge=1)
    source_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    human_confirmed: Literal[True]

PAYLOADS={'workspace.initialize':Strict,'workspace.list':Strict,'workspace.select':Select,'workspace.create':Create,'workspace.legacy.import':Import}

"""Versioned public contract. The caller cannot supply actor scope or approval."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from base.app.companion.assets.references import AssetReference

CONTRACT_VERSION = 'companion.capability.v1'


class EvidenceLimits(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    tasks: int = Field(default=20, ge=1, le=50)
    attempts: int = Field(default=5, ge=1, le=20)


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    contract_version: Literal['companion.capability.v1'] = CONTRACT_VERSION
    request_id: str = Field(min_length=1, max_length=128)
    operation: Literal['evidence.read', 'asset.resolve', 'architecture.describe']
    peer_id: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=128)
    input_refs: list[AssetReference] = Field(default_factory=list, max_length=1)
    limits: EvidenceLimits = Field(default_factory=EvidenceLimits)


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contract_version: Literal['companion.capability.v1'] = CONTRACT_VERSION
    request_id: str
    operation: str
    status: Literal['completed', 'partial', 'needs_input', 'needs_review', 'unavailable', 'failed']
    data: dict | None = None
    evidence_refs: list[AssetReference] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    decision_trace: dict = Field(default_factory=dict)
    commit_receipt: dict | None = None

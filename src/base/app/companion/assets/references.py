"""Content-bound references. A reference is not authorization or a quality certificate."""
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class Locator(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['whole', 'text', 'page', 'region', 'time'] = 'whole'
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=1)
    page: int | None = Field(default=None, ge=1)
    region: list[float] | None = Field(default=None, min_length=4, max_length=4)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def coherent(self):
        expected = {'whole': set(), 'text': {'start','end'}, 'page': {'page'},
                    'region': {'page','region'}, 'time': {'start_ms','end_ms'}}[self.kind]
        actual = {k for k, v in self.model_dump().items() if k != 'kind' and v is not None}
        if actual != expected:
            raise ValueError('定位字段与类型不匹配')
        if self.kind == 'text' and self.end <= self.start:
            raise ValueError('文字范围无效')
        if self.kind == 'time' and self.end_ms <= self.start_ms:
            raise ValueError('媒体时间范围无效')
        if self.kind == 'region':
            x, y, w, h = self.region
            if not all(0 <= v <= 1 for v in self.region) or not w or not h or x+w > 1 or y+h > 1:
                raise ValueError('图区须为归一化的有效范围')
        return self


class AssetReference(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    asset_id: str = Field(min_length=1, max_length=240)
    task_id: str = Field(min_length=1, max_length=128)
    kind: Literal['task_snapshot', 'source_text', 'submission', 'evaluation', 'review', 'attachment', 'local_submission']
    record_id: str = Field(min_length=1, max_length=128)
    owner_ref: str = Field(min_length=1, max_length=160)
    revision: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    locator: Locator = Field(default_factory=Locator)


def reference(task_id, kind, record_id, owner_ref, value):
    checksum = digest(value)
    return AssetReference(asset_id=f'{kind}:{task_id}:{record_id}', task_id=task_id,
                          kind=kind, record_id=str(record_id), owner_ref=owner_ref,
                          revision=checksum, source_hash=checksum).model_dump(mode='json', exclude_none=True)


def resolve(reference_request, current_ref, value):
    """Only call AFTER current role/task authorization. Check integrity before slicing."""
    requested = reference_request.model_dump(mode='json', exclude_none=True)
    if any(requested[k] != current_ref[k] for k in requested if k != 'locator'):
        return {'status': 'needs_input', 'data': None, 'missing': ['asset_version_changed_or_invalid']}
    locator = reference_request.locator
    if locator.kind == 'whole':
        return {'status': 'completed', 'data': value, 'missing': []}
    if locator.kind == 'text' and isinstance(value, dict) and isinstance(value.get('text'), str):
        if locator.end > len(value['text']):
            return {'status': 'needs_input', 'data': None, 'missing': ['text_range_out_of_bounds']}
        return {'status': 'completed', 'data': {'text': value['text'][locator.start:locator.end]}, 'missing': []}
    return {'status': 'unavailable', 'data': None, 'missing': ['locator_adapter_not_implemented']}

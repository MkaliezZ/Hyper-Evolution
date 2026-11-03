"""Additive v7 subject organization; existing v1-v7 request/result schemas stay fixed."""
from typing import Literal
from pydantic import Field
from base.app.companion.functional.study_contracts import Strict,MaterialSave
from base.app.companion.functional.continuity_contracts import PageSave

Subject=Literal['english','mathematics','science','humanities','other']

class SubjectList(Strict):
    subject: Literal['all','english','mathematics','science','humanities','other','unclassified']

class SubjectMaterialSave(MaterialSave):
    subject: Subject
    classification_revision: int=Field(default=0,ge=0)

class SubjectPageSave(PageSave):
    subject: Subject
    classification_revision: int=Field(default=0,ge=0)

class SubjectAsset(Strict):
    asset_kind: Literal['text','page']
    asset_id: str=Field(min_length=1,max_length=64)

class SubjectClassify(SubjectAsset):
    asset_revision: int=Field(ge=1)
    source_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    subject: Subject | None
    expected_revision: int=Field(default=0,ge=0)
    human_confirmed: Literal[True]

SUBJECT_PAYLOADS={'academic.material.list':SubjectList,'academic.material.save':SubjectMaterialSave,
    'academic.page.save':SubjectPageSave,'academic.asset.info':SubjectAsset,'academic.asset.classify':SubjectClassify}

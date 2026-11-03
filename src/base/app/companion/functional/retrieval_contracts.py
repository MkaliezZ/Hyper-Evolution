"""Additive v4 retrieval and review contracts. v1-v3 remain frozen."""
from typing import Literal
from pydantic import Field,model_validator
from base.app.companion.functional.study_contracts import Strict,StudyResult
from base.app.companion.functional.continuity_contracts import Source

class RetrievalRequest(Strict):
    contract_version: Literal['companion.capability.v4']
    request_id: str=Field(min_length=1,max_length=96)
    operation: Literal['index.build','index.list','index.read','index.search','benchmark.save','benchmark.list','benchmark.read',
        'benchmark.run','benchmark.result','benchmark.runs','policy.cases','policy.check','policy.check.read','policy.review.record','policy.review.list']
    payload: dict=Field(default_factory=dict)
    peer_id: str | None=Field(default=None,max_length=128)

class RetrievalResult(StudyResult):
    contract_version: Literal['companion.capability.v4']='companion.capability.v4'

class IndexBuild(Strict):
    chunk_size: int=Field(default=700,ge=160,le=2000)
    overlap: int=Field(default=100,ge=0,le=400)
    @model_validator(mode='after')
    def overlap_valid(self):
        if self.overlap>=self.chunk_size:raise ValueError('overlap must be smaller than chunk size')
        return self

class IndexRead(Strict):
    index_id: str=Field(min_length=1,max_length=80)

class IndexSearch(IndexRead):
    query: str=Field(min_length=1,max_length=400)
    method: Literal['literal.v1','bm25.v1']='bm25.v1'
    k: int=Field(default=5,ge=1,le=10)
    @model_validator(mode='after')
    def query_valid(self):
        if not self.query.strip():raise ValueError('query cannot be blank')
        return self

class Expected(Strict):
    source: Source
    quote: str=Field(default='',max_length=1000)

class BenchmarkCase(Strict):
    case_id: str=Field(min_length=1,max_length=64)
    query: str=Field(min_length=1,max_length=400)
    expected: list[Expected]=Field(default_factory=list,max_length=5)
    note: str=Field(default='',max_length=1000)
    @model_validator(mode='after')
    def query_valid(self):
        if not self.query.strip():raise ValueError('query cannot be blank')
        return self

class BenchmarkSave(Strict):
    title: str=Field(min_length=1,max_length=160)
    cases: list[BenchmarkCase]=Field(min_length=1,max_length=50)
    label_origin: Literal['synthetic','user_labelled']='user_labelled'
    benchmark_id: str | None=Field(default=None,max_length=80)
    expected_revision: int | None=Field(default=None,ge=1)
    @model_validator(mode='after')
    def unique_cases(self):
        if len({c.case_id for c in self.cases})!=len(self.cases):raise ValueError('case ids must be unique')
        return self

class BenchmarkRead(Strict):
    benchmark_id: str=Field(min_length=1,max_length=80)
    revision: int | None=Field(default=None,ge=1)

class BenchmarkRun(BenchmarkRead):
    index_ids: list[str]=Field(min_length=1,max_length=3)
    methods: list[Literal['literal.v1','bm25.v1']]=Field(default_factory=lambda:['literal.v1','bm25.v1'],min_length=1,max_length=2)
    k: int=Field(default=3,ge=1,le=10)
    @model_validator(mode='after')
    def unique_versions(self):
        if len(set(self.index_ids))!=len(self.index_ids) or len(set(self.methods))!=len(self.methods):raise ValueError('versions must be distinct')
        return self

class RunRead(Strict):
    run_id: str=Field(min_length=1,max_length=80)

class CaseRead(Strict):
    pack: str | None=Field(default=None,pattern=r'^P(?:0[1-9]|10)$')

class CaseObservation(Strict):
    case_id: str=Field(min_length=1,max_length=80)
    verdict: Literal['appropriate','needs_revision','uncertain']
    reason: str=Field(min_length=3,max_length=1500)

class PolicyReview(Strict):
    check_id: str=Field(min_length=1,max_length=80)
    pack: str=Field(pattern=r'^P(?:0[1-9]|10)$')
    reviewer_name: str=Field(min_length=1,max_length=100)
    expertise_statement: str=Field(min_length=3,max_length=600)
    intended_scope: str=Field(min_length=3,max_length=1000)
    conclusion: Literal['needs_revision','approved_for_pilot','rejected']
    observations: list[CaseObservation]=Field(min_length=1,max_length=20)
    human_confirmed: bool=False
    @model_validator(mode='after')
    def real_review(self):
        if not self.human_confirmed:raise ValueError('actual human review must be confirmed')
        if len({o.case_id for o in self.observations})!=len(self.observations):raise ValueError('duplicate case observation')
        if any(not x.strip() for x in [self.reviewer_name,self.expertise_statement,self.intended_scope]):raise ValueError('reviewer and scope cannot be blank')
        return self

PAYLOADS={'index.build':IndexBuild,'index.read':IndexRead,'index.search':IndexSearch,'benchmark.save':BenchmarkSave,
    'benchmark.read':BenchmarkRead,'benchmark.runs':BenchmarkRead,'benchmark.run':BenchmarkRun,'benchmark.result':RunRead,'policy.cases':CaseRead,
    'policy.check':CaseRead,'policy.check.read':RunRead,'policy.review.record':PolicyReview,'policy.review.list':CaseRead}

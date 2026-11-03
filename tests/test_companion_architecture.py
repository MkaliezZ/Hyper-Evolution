"""Check fixed layer dependencies; this is not professional or pedagogical validation."""
import ast
import json
from pathlib import Path
from base.app.companion.functional.service import describe_architecture
from base.app.companion.functional.contracts import CapabilityRequest, CapabilityResult
from base.app.companion.functional.study_contracts import StudyRequest,StudyResult
from base.app.companion.functional.continuity_contracts import ContinuityRequest,ContinuityResult
from base.app.companion.functional.retrieval_contracts import RetrievalRequest,RetrievalResult
from base.app.companion.functional.evolution_contracts import EvolutionRequest,EvolutionResult
from base.app.companion.functional.review_contracts import ReviewRequest,ReviewResult
from base.app.companion.functional.academic_contracts import AcademicRequest,AcademicResult
from base.app.companion.functional.workspace_contracts import WorkspaceRequest,WorkspaceResult

ROOT = Path(__file__).resolve().parents[1] / 'src/base/app/companion'


def test_three_layers_and_six_object_contract():
    assert {p.name for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith('_')} == {'aesthetic','functional','assets'}
    description = describe_architecture()
    assert len(description['objects']) == 6
    assert set(description['layers']) == {'aesthetic','functional','assets'}
    assert description['policy']['professional_validation'] == 'NOT_REVIEWED'


def test_versioned_contracts_match_reviewable_schema_snapshots():
    folder=Path(__file__).resolve().parents[1]/'docs/contracts'
    for kind,model in [('request',CapabilityRequest),('result',CapabilityResult)]:
        assert json.loads((folder/f'companion.capability.v1.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    for kind,model in [('request',StudyRequest),('result',StudyResult)]:
        assert json.loads((folder/f'companion.capability.v2.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    for kind,model in [('request',ContinuityRequest),('result',ContinuityResult)]:
        assert json.loads((folder/f'companion.capability.v3.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    for kind,model in [('request',RetrievalRequest),('result',RetrievalResult)]:
        assert json.loads((folder/f'companion.capability.v4.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    for kind,model in [('request',EvolutionRequest),('result',EvolutionResult)]:
        assert json.loads((folder/f'companion.capability.v5.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    for kind,model in [('request',ReviewRequest),('result',ReviewResult)]:
        assert json.loads((folder/f'companion.capability.v6.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    for kind,model in [('request',AcademicRequest),('result',AcademicResult)]:
        assert json.loads((folder/f'companion.capability.v7.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()
    for kind,model in [('request',WorkspaceRequest),('result',WorkspaceResult)]:
        assert json.loads((folder/f'companion.capability.v8.{kind}.schema.json').read_text(encoding='utf8'))==model.model_json_schema()


def test_layer_imports_cannot_reverse_or_access_runtime_from_lower_layers():
    forbidden = {
        'aesthetic': ('base.app.companion.functional','base.app.companion.assets','base.app.local_runtime',
                      'base.core','growth_local','sqlite3','requests','httpx','pydantic_ai','fastapi','mcp','socket','subprocess'),
        'assets': ('base.app.companion.functional','base.app.companion.aesthetic','base.app.local_runtime',
                   'base.core','growth_local','sqlite3','requests','httpx','pydantic_ai','fastapi','mcp','socket','subprocess'),
        'functional': ('base.app.local_runtime','growth_local','fastapi','mcp'),
    }
    for layer, banned in forbidden.items():
        for file in (ROOT/layer).rglob('*.py'):
            for node in ast.walk(ast.parse(file.read_text(encoding='utf8'))):
                if isinstance(node, ast.Import):
                    names = [n.name for n in node.names]
                elif isinstance(node, ast.ImportFrom):
                    assert not node.level, f'Use explicit layer imports: {file}'
                    names = [node.module or '']
                else:
                    continue
                assert not any(n == prefix or n.startswith(prefix+'.') for n in names for prefix in banned), file

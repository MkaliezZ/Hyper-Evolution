"""One read capability dispatcher used by both transports and the internal Agent."""
from pydantic import ValidationError
from base.app.companion.assets.references import resolve
from base.app.companion.aesthetic.policy import policy_descriptor
from base.app.companion.functional.contracts import CapabilityRequest, CapabilityResult
from base.app.companion.functional.evidence import authorized_tasks, evidence_view, project


def describe_architecture():
    from base.app.companion.functional.experience_contracts import ExperienceRequest,ExperienceResult,PAYLOADS as EXPERIENCE_PAYLOADS
    from base.app.companion.functional.teaching_contracts import TeachingRequest,TeachingResult,PAYLOADS as TEACHING_PAYLOADS
    from base.app.companion.functional.planning_contracts import PlanningRequest,PlanningResult,PAYLOADS as PLANNING_PAYLOADS
    from base.app.companion.functional.workspace_contracts import WorkspaceRequest,WorkspaceResult,PAYLOADS as WORKSPACE_PAYLOADS
    from base.app.companion.functional.academic_contracts import AcademicRequest,AcademicResult,PAYLOADS as ACADEMIC_PAYLOADS
    from base.app.companion.functional.study_contracts import StudyRequest,StudyResult,PAYLOADS
    from base.app.companion.functional.continuity_contracts import ContinuityRequest,ContinuityResult,PAYLOADS as CONTINUITY_PAYLOADS
    from base.app.companion.functional.retrieval_contracts import RetrievalRequest,RetrievalResult,PAYLOADS as RETRIEVAL_PAYLOADS
    from base.app.companion.functional.evolution_contracts import EvolutionRequest,EvolutionResult,PAYLOADS as EVOLUTION_PAYLOADS
    from base.app.companion.functional.review_contracts import ReviewRequest,ReviewResult,PAYLOADS as REVIEW_PAYLOADS
    return {'version': 'three-layer.v1', 'objects': {
        'Scenario': '具体人群、问题、目标、约束与预期结果',
        'Module': '独立维护的职责边界', 'Capability': '外部行为承诺与质量 / 失败约定',
        'Agent_Skill_Workflow': '功能层内部可替换实现，普通代码和人工也可',
        'Policy_Pack': '审美层的专业判断与选择标准', 'Asset': '内容 / 个人记录 / 方法 / 证据及其治理'},
        'layers': {'aesthetic': '判断与规则；不直接访问数据库、网络或执行工具',
                   'functional': '公开契约、授权、装配、执行、检查和记录；Harness 在此层',
                   'assets': '来源、版本、定位、派生关系、用途、访问与质量状态'},
        'implemented': ['授权证据视图', 'v1—v10版本化能力契约', '投石问路成长梳理、版本与明确签名分享', '学科独立数据库、资料目录及签名任务路由', '学科与路线入口、K12教学契约', '文字和PNG/JPEG原图引用',
                        'P01—P10运行条件、六类方法装配及评价检查', '有来源的可修订教学札记', '个人可调复习与事件记录',
                        '不可变文字索引与固定题集检索对照','20个规则案例、工程检查和限定范围本机审阅记录',
                        '可选学习安排的预览确认与签名同步','写作首稿、候选建议、修订归因和显式提交历史',
                        '方法候选、声明式专业审阅、负责人本机发布与显式导出','教师AI预审、人工修改草稿、明确发布与可选自动预审',
                        'v10预登记、教材目录与抽取、扩展词表检查、局部审校、教师题库、目标复测、学习报告及逐人范围映射'],
        'pending': ['PDF/OCR与XLSX适配','规则包专业审定与真实案例验证','Embedding/语义检索适配','跨组织公共方法分发及身份认证','真实学生效果验证'],
        'experience_extension':{'version':'companion.capability.v11','request_schema':ExperienceRequest.model_json_schema(),
            'result_schema':ExperienceResult.model_json_schema(),'payload_schemas':{k:v.model_json_schema() for k,v in EXPERIENCE_PAYLOADS.items()}},
        'teaching_extension':{'version':'companion.capability.v10','request_schema':TeachingRequest.model_json_schema(),
            'result_schema':TeachingResult.model_json_schema(),'payload_schemas':{k:v.model_json_schema() for k,v in TEACHING_PAYLOADS.items()}},
        'retrieval_extension':{'version':'companion.capability.v4','request_schema':RetrievalRequest.model_json_schema(),
            'result_schema':RetrievalResult.model_json_schema(),'payload_schemas':{k:v.model_json_schema() for k,v in RETRIEVAL_PAYLOADS.items()}},
        'evolution_extension':{'version':'companion.capability.v5','request_schema':EvolutionRequest.model_json_schema(),
            'result_schema':EvolutionResult.model_json_schema(),'payload_schemas':{k:v.model_json_schema() for k,v in EVOLUTION_PAYLOADS.items()}},
        'review_extension':{'version':'companion.capability.v6','request_schema':ReviewRequest.model_json_schema(),
            'result_schema':ReviewResult.model_json_schema(),'payload_schemas':{k:v.model_json_schema() for k,v in REVIEW_PAYLOADS.items()}},
        'planning_extension':{'version':'companion.capability.v9','request_schema':PlanningRequest.model_json_schema(),
            'result_schema':PlanningResult.model_json_schema(),'payload_schemas':{k:v.model_json_schema() for k,v in PLANNING_PAYLOADS.items()}},
        'workspace_extension':{'version':'companion.capability.v8','request_schema':WorkspaceRequest.model_json_schema(),
            'result_schema':WorkspaceResult.model_json_schema(),'payload_schemas':{k:v.model_json_schema() for k,v in WORKSPACE_PAYLOADS.items()}},
        'academic_extension':{'version':'companion.capability.v7','request_schema':AcademicRequest.model_json_schema(),
            'result_schema':AcademicResult.model_json_schema(),'payload_schemas':{k:v.model_json_schema() for k,v in ACADEMIC_PAYLOADS.items()}},
        'study_extension':{'version':'companion.capability.v2','request_schema':StudyRequest.model_json_schema(),
                           'result_schema':StudyResult.model_json_schema(),
                           'payload_schemas':{k:v.model_json_schema() for k,v in PAYLOADS.items()}},
        'continuity_extension':{'version':'companion.capability.v3','request_schema':ContinuityRequest.model_json_schema(),'result_schema':ContinuityResult.model_json_schema(),
            'payload_schemas':{k:v.model_json_schema() for k,v in CONTINUITY_PAYLOADS.items()}},
        'storage': 'existing_local_data', 'policy': policy_descriptor(),
        'capability_operations': ['evidence.read', 'asset.resolve', 'architecture.describe'],
        'request_schema': CapabilityRequest.model_json_schema(),
        'result_schema': CapabilityResult.model_json_schema()}


def invoke(runtime, raw):
    if runtime.role not in ['student','teacher']:
        raise PermissionError('请先完成本机身份设置')
    try:
        request = CapabilityRequest.model_validate(raw)
    except ValidationError:
        # Never reflect raw request input (possibly a credential) in HTTP or MCP errors.
        raise ValueError('能力请求格式无效，请按 companion.capability.v1 契约填写；身份由本机确定。') from None
    policy = policy_descriptor()
    trace = {'policy_refs': [{'id': policy['id'], 'version': policy['version']}],
             'policy_requirements': [rule['requires'] for rule in policy['rules']],
             'professional_validation': policy['professional_validation'], 'actor_role': runtime.role,
             'purpose': 'authorized_learning_evidence', 'read_only': True}
    if request.operation == 'architecture.describe':
        result = {'status': 'completed', 'data': describe_architecture()}
    elif request.operation == 'evidence.read':
        if request.input_refs:
            raise ValueError('读取证据请用 task_id；input_refs 仅用于 asset.resolve')
        data = evidence_view(runtime, request.peer_id, request.task_id, request.limits.tasks, request.limits.attempts)
        result = {'status': 'partial' if data['coverage']['truncated'] else 'completed', 'data': data,
                  'missing': ['historical_conditions_not_recorded'] if data['tasks'] else []}
    else:
        if len(request.input_refs) != 1:
            raise ValueError('asset.resolve 须提供一个版本化资产引用')
        ref = request.input_refs[0]
        if request.task_id is not None and request.task_id != ref.task_id:
            raise ValueError('任务与资产引用不一致')
        _, tasks, _ = authorized_tasks(runtime, request.peer_id, ref.task_id)
        # Resolve all historical attempts without altering or re-evaluating stored records.
        task = tasks[0]
        _, records = project(runtime, task, max(1, len(task.get('attempts', [])), len(runtime.pending_submissions(task['id']))))
        if ref.asset_id not in records:
            result = {'status': 'needs_input', 'data': None, 'missing': ['asset_not_present_in_authorized_task']}
        else:
            current, value = records[ref.asset_id]
            result = {**resolve(ref, current, value), 'evidence_refs': [current]}
    return CapabilityResult(request_id=request.request_id, operation=request.operation,
                            decision_trace=trace, **result).model_dump(mode='json', exclude_none=True)

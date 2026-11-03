"""Optional administrator-configured chat provider. Secrets never leave server configuration."""

import json, os
from uuid import uuid4
import httpx
from base.app.content import BLUEPRINTS


def model_status():
    return {
        "configured": bool(
            os.environ.get("GROWTH_MODEL_URL") and os.environ.get("GROWTH_MODEL_NAME")
        ),
        "default": "local_semantic_template",
        "model": os.environ.get("GROWTH_MODEL_NAME") or None,
        "note": "没有配置模型时，本地练习可用；不会假装调用语言模型。",
    }


def generate_draft(service, learner_id, client=None):
    if not model_status()["configured"]:
        raise ValueError(
            "尚未配置模型服务。可先使用本地出题，或让Agent通过MCP生成待审题包。"
        )
    d = service.dashboard(learner_id)
    exam = d["person"]["exam"]
    status = BLUEPRINTS[exam]
    # No student name, capability, files or unrelated private records are sent.
    context = {
        "exam": status,
        "stage": d["person"]["stage"],
        "weak_skills": d["weak_skills"],
        "required_task_type": "true_false_not_given" if exam == "ielts" else "daily_life",
    }
    instruction = "Create one original English micro-drill targeting the supplied weak skills and exam construct. Return JSON only: id (unique), family_id(unique), title, exam (ielts or toefl), blueprint (exact supplied version), task_type (one allowed reading id), instructions, stimulus, source {kind:original,title:model-created draft}, items. 5 items, each with id(string),kind(mcq/gap/tfng),prompt,key(list of strings),evidence(exact quote or explicit absence rationale for NOT GIVEN),explanation(in Chinese),skill (detail/purpose/contradiction/inference). mcq has 4 options with a single A-D key. No copied official questions, band scores or claims of human review. Preserve answer uniqueness; FALSE requires contradiction. Do not invent audio."
    instruction += (
        " Use exactly required_task_type. For IELTS, all five items must be tfng with keys TRUE/FALSE/NOT GIVEN; include all three answer categories, and do not treat a merely absent statement as FALSE. For TOEFL daily_life, all five items must be mcq with options as a list of four plain strings; use a realistic campus notice, email or message, test purpose, detail and supported inference, and explain plausible distractors. Stage-specific content must suit the supplied stage. Use an original 180-260 word stimulus, not a full exam or calibrated score. Before returning, verify every answer against the stimulus. Example item schema (not content to reuse): {\"id\":\"1\",\"kind\":\"mcq\",\"prompt\":\"Why did the writer send this email?\",\"options\":[\"...\",\"...\",\"...\",\"...\"],\"key\":[\"B\"],\"evidence\":\"exact sentence from stimulus\",\"explanation\":\"Chinese explanation\",\"skill\":\"purpose\"}."
    )
    headers = {"Content-Type": "application/json"}
    if os.environ.get("GROWTH_MODEL_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["GROWTH_MODEL_KEY"]
    payload = {
        "model": os.environ["GROWTH_MODEL_NAME"],
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        "temperature": 0.4,
    }
    if os.environ.get("GROWTH_MODEL_JSON_MODE") == "1":
        payload["response_format"] = {"type": "json_object"}
    if os.environ.get("GROWTH_MODEL_THINKING") in ["enabled", "disabled"]:
        payload["thinking"] = {"type": os.environ["GROWTH_MODEL_THINKING"]}
        if payload["thinking"]["type"] == "enabled":
            payload.pop("temperature")
            payload["reasoning_effort"] = "high"
            payload["max_tokens"] = 16384
    try:
        transport = client or httpx.Client(timeout=httpx.Timeout(240, connect=10), follow_redirects=False)
        try:
            r = transport.post(
                os.environ["GROWTH_MODEL_URL"],
                headers=headers,
                json=payload,
            )
            if not r.is_success:
                raise ValueError(
                    "模型请求未成功，请管理员检查服务配置；未保存或发布任何题目。"
                )
            choice = r.json()["choices"][0]
            if choice.get("finish_reason") not in [None, "stop"]:
                raise ValueError("模型输出未完整结束，未保存题包。")
            raw = choice["message"]["content"]
            raw = (
                raw.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            p = json.loads(raw)
        finally:
            if client is None:
                transport.close()
    except (
        httpx.HTTPError,
        KeyError,
        IndexError,
        TypeError,
        AttributeError,
        json.JSONDecodeError,
    ):
        raise ValueError(
            "模型暂未返回合格题包，请稍后重试或使用本地练习；没有把失败当作已生成。"
        ) from None
    if not isinstance(p, dict):
        raise ValueError("模型返回的题包不是对象，未保存。")
    if p.get("exam") != exam or p.get("blueprint") != status["version"]:
        raise ValueError("模型返回了不匹配的考试版本，未保存题包。")
    p["source"] = {
        "kind": "model_original_draft",
        "title": "模型生成原创草稿，待教师逐题审校",
    }
    # An untrusted model must never overwrite an existing teacher resource by ID.
    p["id"] = "model-" + uuid4().hex
    p["family_id"] = p["id"]
    p["stage"] = d["person"]["stage"]
    if not isinstance(p.get("items"), list) or len(p["items"]) != 5:
        raise ValueError("模型草稿须包含五道完整题目，未保存。")
    if p.get("task_type") != context["required_task_type"] or any(
        not isinstance(i, dict) or i.get("kind") != ("tfng" if exam == "ielts" else "mcq")
        for i in p["items"]
    ):
        raise ValueError("模型草稿未遵循本次指定的考试题型，未保存。")
    if p.get("audio") or p.get("media_path"):
        raise ValueError("本次模型只能生成阅读草稿，不能附加录音或本机文件。")
    service.import_pack(p)
    return {
        "id": p["id"],
        "status": "pending_review",
        "note": "已保存待审草稿，未向学生发布。",
    }

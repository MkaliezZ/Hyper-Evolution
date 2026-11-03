import hashlib, json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from base.app.content import make_drill, grade, BLUEPRINTS
from base.app.growth import GrowthService
from growth.web import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / "instance")


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def enroll(c, name="合成学生", **extra):
    person = c.post(
        "/api/enroll",
        json={"name": name, "exam": "ielts", "stage": "application", **extra},
    ).json()
    # These legacy workflow cases exercise an already paired teacher/student relationship.
    admin={"X-Owner-Token":c.app.state.service.base.owner_token}
    code=c.post('/api/teacher/pair-codes',headers=admin,json={}).json()['code']
    paired=c.post('/api/pairing/redeem',headers=headers(person),json={'code':code})
    assert paired.status_code==200
    return paired.json()


def headers(p):
    return {"Authorization": "Bearer " + p["access"]}


def answers(service, id):
    return {
        i["id"]: i["key"][0] for i in service._task(id)["snapshot"]["growth"]["items"]
    }


def start(c, p, purpose, key):
    r = c.post(
        "/api/activities",
        json={"purpose": purpose, "request_key": key},
        headers=headers(p),
    )
    assert r.status_code == 200, r.text
    return r.json()


def submit(c, p, service, t, key="answer"):
    r = c.post(
        "/api/activities/" + t["id"] + "/submit",
        headers=headers(p),
        json={"answers": answers(service, t["id"]), "request_key": key},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("exam", ["ielts", "toefl"])
@pytest.mark.parametrize("stage", ["application", "predeparture", "enrolled"])
def test_full_diagnostic_personalized_retest_versions(client, app, exam, stage):
    p = enroll(client, exam=exam, stage=stage)
    s = app.state.service
    d = start(client, p, "diagnostic", "diagnostic")
    assert all("key" not in q and "evidence" not in q for q in d["pack"]["items"])
    assert "transcript" not in d["pack"]
    result = submit(client, p, s, d)
    assert result["attempts"][0]["automatic"]["score"] == 5
    practice = start(client, p, "practice", "practice")
    submit(client, p, s, practice)
    retest = start(client, p, "retest", "retest")
    assert retest["pack"]["stimulus"] != d["pack"]["stimulus"]
    assert retest["pack"]["family_id"] != d["pack"]["family_id"]
    submit(client, p, s, retest)
    assert (
        client.get("/api/me", headers=headers(p)).json()["evidence"]["completed"] == 3
    )
    assert (
        client.get("/api/me", headers=headers(p)).json()["evidence"][
            "independent_transfer"
        ]
        == 0
    )
    assert (
        GrowthService(s.folder).dashboard(p["person"]["id"])["evidence"]["completed"]
        == 3
    )


def test_roles_cross_learner_and_revoked_link(client, app):
    a = enroll(client, "同名")
    b = enroll(client, "同名")
    assert a["person"]["id"] != b["person"]["id"]
    t = start(client, a, "diagnostic", "a")
    assert client.get("/api/teacher", headers=headers(a)).status_code == 403
    assert (
        client.get("/api/activities/" + t["id"], headers=headers(b)).status_code == 403
    )
    assert client.get("/api/me").status_code == 403
    owner = {"X-Owner-Token": app.state.service.base.owner_token}
    link = client.post(
        "/api/teacher/students/" + a["person"]["id"] + "/link", headers=owner
    ).json()
    assert client.get("/api/me", headers=headers(a)).status_code == 403
    assert (
        client.get(
            "/api/me",
            headers={
                "Authorization": "Bearer " + link["student_path"].split("#learn=")[1]
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/activities",
            headers={**headers(b), "Origin": "https://other.example"},
            json={},
        ).status_code
        == 403
    )


def test_retry_conflict_pause_feedback_revision_and_transfer(client, app):
    p = enroll(client)
    s = app.state.service
    t = start(client, p, "diagnostic", "same")
    assert start(client, p, "diagnostic", "same")["id"] == t["id"]
    assert (
        client.post(
            "/api/activities",
            headers=headers(p),
            json={"purpose": "writing", "request_key": "same"},
        ).status_code
        == 400
    )
    first = submit(client, p, s, t)
    assert submit(client, p, s, t)["attempts"][0]["id"] == first["attempts"][0]["id"]
    bad = client.post(
        "/api/activities/" + t["id"] + "/submit",
        headers=headers(p),
        json={
            "answers": {i: "wrong" for i in answers(s, t["id"])},
            "request_key": "answer",
        },
    )
    assert bad.status_code == 400
    admin = {"X-Owner-Token": s.base.owner_token}
    sid = first["attempts"][0]["id"]
    r = client.post(
        "/api/teacher/feedback/" + sid,
        headers=admin,
        json={
            "comment": "原文依据明确，下一次换情境",
            "next_step": "换材料独立完成",
            "judgement": "meets_criteria",
            "request_key": "review",
        },
    )
    assert r.status_code == 200
    assert (
        client.get("/api/activities/" + t["id"], headers=headers(p))
        .json()["attempts"][0]["evaluation"]["comment"]
        .startswith("原文")
    )
    second = submit(client, p, s, t, "revision")
    assert len(second["attempts"]) == 2
    client.post(
        "/api/teacher/state/" + t["id"], headers=admin, json={"state": "paused"}
    )
    assert (
        client.post(
            "/api/activities/" + t["id"] + "/submit",
            headers=headers(p),
            json={"answers": answers(s, t["id"]), "request_key": "paused"},
        ).status_code
        == 400
    )
    assert (
        client.get("/api/activities/" + t["id"], headers=headers(p)).status_code == 200
    )


def audio_candidate(service):
    p = make_drill("ielts", "application", seed="audio")
    p["id"] = "audio-source"
    p["family_id"] = "same-recording"
    data = b"ID3" + bytes(100)
    folder = service.folder / "media"
    folder.mkdir(exist_ok=True)
    file = folder / "sample.mp3"
    file.write_bytes(data)
    p.update(
        audio=hashlib.sha256(data).hexdigest(),
        audio_sha256=hashlib.sha256(data).hexdigest(),
        media_path=str(file),
    )
    return p


def test_listening_gate_retry_exposure_and_integrity(client, app):
    s = app.state.service
    pack = audio_candidate(s)
    s.import_pack(pack)
    p = enroll(client)
    assert (
        client.post(
            "/api/activities",
            headers=headers(p),
            json={"purpose": "listening", "request_key": "first"},
        ).status_code
        == 400
    )
    demo = enroll(client, demo=True)
    t = start(client, demo, "listening", "demo")
    assert start(client, demo, "listening", "demo")["id"] == t["id"]
    assert (
        client.get("/api/audio/" + pack["audio"], headers=headers(p)).status_code == 403
    )
    assert (
        client.get("/api/audio/" + pack["audio"], headers=headers(demo)).status_code
        == 200
    )
    with pytest.raises(ValueError):
        s.review_pack(pack["id"], "合成核验者", "仅用于测试接口", False, True)
    s.review_pack(
        pack["id"], "合成核验者", "测试放行门禁，不代表真实人声审核", True, True
    )
    real = start(client, p, "listening", "first")
    assert real["pack"]["audio"] == pack["audio"]
    assert "transcript" not in real["pack"]
    renamed = {**pack, "id": "renamed-source", "family_id": "renamed-family"}
    s.import_pack(renamed)
    s.review_pack(renamed["id"], "合成测试", "同一录音换名不应绕过已见排除", True, True)
    assert (
        client.post(
            "/api/activities",
            headers=headers(p),
            json={"purpose": "listening", "request_key": "second"},
        ).status_code
        == 400
    )
    Path(pack["media_path"]).write_bytes(b"changed")
    assert (
        client.get("/api/audio/" + pack["audio"], headers=headers(p)).status_code == 400
    )


def test_upload_ownership_formats_and_subjective_not_auto_pass(client, app):
    p = enroll(client)
    other = enroll(client)
    s = app.state.service
    file = client.post(
        "/api/uploads",
        headers=headers(p),
        files={"file": ("notes.txt", b"Original English evidence", "text/plain")},
    )
    assert file.status_code == 200
    id = file.json()["id"]
    assert client.get("/api/files/" + id, headers=headers(other)).status_code == 403
    assert (
        client.get("/api/files/" + id, headers=headers(p)).content
        == b"Original English evidence"
    )
    assert (
        client.post(
            "/api/uploads",
            headers=headers(p),
            files={"file": ("fake.mp3", b"<script>", "audio/mpeg")},
        ).status_code
        == 400
    )
    w = start(client, p, "writing", "w")
    r = client.post(
        "/api/activities/" + w["id"] + "/submit",
        headers=headers(p),
        json={
            "text": "Dear coordinator, I need help.",
            "files": [id],
            "request_key": "w1",
        },
    )
    assert r.status_code == 200
    assert r.json()["attempts"][0]["evaluation"]["status"] == "pending"
    assert r.json()["attempts"][0]["evaluation"].get("judgement") is None
    wo = start(client, other, "writing", "wo")
    assert (
        client.post(
            "/api/activities/" + wo["id"] + "/submit",
            headers=headers(other),
            json={"files": [id], "request_key": "steal"},
        ).status_code
        == 403
    )


def test_pack_quality_version_import_resets_review_and_path_escape(tmp_path):
    s = GrowthService(tmp_path)
    p = make_drill("ielts", "application", seed="draft")
    s.import_pack(p)
    s.review_pack(p["id"], "合成测试", "仅用于测试内容状态", content_checked=True)
    assert s.resources()[0]["status"] == "ready"
    s.import_pack(p)
    assert s.resources()[0]["status"] == "pending_review"
    with pytest.raises(ValueError):
        s.import_pack({**p, "blueprint": "old-exam"})
    with pytest.raises(ValueError):
        s.import_pack({**p, "media_path": str(tmp_path.parent / "secret")})
    bad = json.loads(json.dumps(p))
    bad["items"][1]["id"] = bad["items"][0]["id"]
    with pytest.raises(ValueError):
        s.import_pack(bad)


def test_goal_is_plan_not_achievement_and_not_probability(client, app):
    p = enroll(client)
    r = client.post(
        "/api/goals",
        headers=headers(p),
        json={"target": "参与导师学术讨论", "url": "https://example.edu/opportunity"},
    )
    assert r.status_code == 200
    assert len(r.json()["gaps"]) == 3
    assert r.json()["value_assessment"] == "未评估"
    assert (
        client.get("/api/me", headers=headers(p)).json()["evidence"]["meets_criteria"]
        == 0
    )
    s = app.state.service
    t = start(client, p, "writing", "write")
    work = client.post(
        "/api/activities/" + t["id"] + "/submit",
        headers=headers(p),
        json={
            "text": "Dear coordinator, could you explain the next step?",
            "request_key": "work",
        },
    ).json()
    plan = client.get("/api/me", headers=headers(p)).json()["person"]["goal_plan"]
    gap = next(g for g in plan["gaps"] if g["activity"] == "writing")
    assert len(gap["evidence_refs"]) == 1 and "尚待教师" in gap["evidence_status"]


def test_mcp_requires_teacher_credential_and_ui_security(client):
    assert client.post("/mcp/", json={}).status_code == 401
    assert client.get("/").status_code == 200
    assert "frame-ancestors" in client.get("/").headers["Content-Security-Policy"]
    assert client.get("/assets/app.js").status_code == 200


def test_latest_evidence_updates_focus_and_reviewed_agent_pack_is_assignable(tmp_path):
    s = GrowthService(tmp_path)
    p = s.create_learner("合成动态诊断", "ielts", "application")
    id = p["person"]["id"]
    t = s.start(id, "diagnostic", "diag")
    pack = s._task(t["id"])["snapshot"]["growth"]
    wrong = {i["id"]: "incorrect" for i in pack["items"]}
    s.submit(t["id"], answers=wrong, request_key="wrong")
    assert "contradiction" in s.dashboard(id)["weak_skills"]
    practice = s.start(id, "practice", "practice")
    raw = s._task(practice["id"])["snapshot"]["growth"]
    assert raw["items"][0]["skill"] == "contradiction"
    s.submit(
        practice["id"],
        answers={i["id"]: i["key"][0] for i in raw["items"]},
        request_key="correct",
    )
    assert "contradiction" not in s.dashboard(id)["weak_skills"]
    agent = make_drill("ielts", "application", seed="agent-draft")
    s.import_pack(agent)
    with pytest.raises(ValueError):
        s.start(id, "practice", "before-review", agent["id"])
    s.review_pack(
        agent["id"],
        "合成审核测试",
        "只验证门禁；不代表人工学习效果",
        content_checked=True,
    )
    assigned = s.start(id, "practice", "after-review", agent["id"])
    assert assigned["pack"]["id"] == agent["id"]
    with pytest.raises(ValueError):
        s.start(id, "retest", "reuse", agent["id"])
    with pytest.raises(ValueError):
        s.validate_pack({**agent, "task_type": "old_integrated_writing"})


def test_optional_model_failure_and_success_stay_pending(tmp_path, monkeypatch):
    import httpx
    from base.app.provider import generate_draft

    s = GrowthService(tmp_path)
    p = s.create_learner("合成模型接口测试", "toefl", "enrolled")
    monkeypatch.delenv("GROWTH_MODEL_URL", raising=False)
    with pytest.raises(ValueError):
        generate_draft(s, p["person"]["id"])
    monkeypatch.setenv("GROWTH_MODEL_URL", "https://model.example/chat")
    monkeypatch.setenv("GROWTH_MODEL_NAME", "mock-test")
    draft = make_drill("toefl", "enrolled", seed="model")
    draft["task_type"] = "daily_life"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(draft)}}]}
            )
        )
    ) as c:
        result = generate_draft(s, p["person"]["id"], c)
    assert result["status"] == "pending_review"
    assert result["id"] != draft["id"]
    assert s.resources()[0]["status"] == "pending_review"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200, json={"choices": [{"message": {"content": "not json"}}]}
            )
        )
    ) as c:
        with pytest.raises(ValueError):
            generate_draft(s, p["person"]["id"], c)


def test_teacher_private_notes_are_not_sent_to_student(client, app):
    p = enroll(client)
    s = app.state.service
    id = p["person"]["id"]
    s.update_person(
        id,
        "合成学生",
        "阅读有依据",
        "ielts",
        "application",
        "只供教师制定教学安排的备注",
    )
    assert client.get("/api/me", headers=headers(p)).json()["person"]["notes"] == ""
    result = client.get(
        "/api/teacher", headers={"X-Owner-Token": s.base.owner_token}
    ).json()
    assert result["learners"][0]["person"]["notes"].startswith("只供教师")

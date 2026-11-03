"""Trusted teacher MCP adapter. Same GrowthService/database as both web portals."""

import os
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from base.app.growth import GrowthService
from base.app.content import BLUEPRINTS, SKILLS


def create_mcp(service):
    server = FastMCP(
        "超维成长",
        instructions="先读get_context，按明确授权操作对应学生。学生提交与教师评阅分开。没有完成实际试听/内容核验时不得声称审校通过；练习分数不是正式考试等级。",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"]
            + [x.strip() for x in os.environ.get("GROWTH_MCP_HOSTS", "").split(",") if x.strip()],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*"]
            + [x.strip() for x in os.environ.get("GROWTH_MCP_ORIGINS", "").split(",") if x.strip()],
        ),
    )

    @server.tool()
    def get_context() -> dict:
        """Exam blueprints and quality gates; no learner information."""
        return service.catalog()

    @server.tool()
    def list_students() -> dict:
        """Teacher-private learner profiles and submitted evidence; do not expose across learners."""
        data = service.teacher_overview()
        return {
            "students": [
                {
                    "person": p["person"],
                    "next": p["next"],
                    "weak_skills": p["weak_skills"],
                }
                for p in data["learners"]
            ],
            "stats": data["stats"],
        }

    @server.tool()
    def create_student(
        name: str, exam: str, stage: str, goal: str = "", request_key: str = ""
    ) -> dict:
        """Create an explicitly requested learner; returns private student link. Same names remain distinct."""
        return service.create_learner(
            name, exam, stage, goal, request_key=request_key or None
        )

    @server.tool()
    def get_student(learner_id: str) -> dict:
        """Read this learner's assignments, submissions, feedback, plan and evidence."""
        return service.dashboard(learner_id, teacher=True)

    @server.tool()
    def issue_student_link(learner_id: str) -> dict:
        """Teacher-requested link replacement. Revokes the previous student portal link, preserves records."""
        return service.issue_link(learner_id)

    @server.tool()
    def create_pair_code(learner_id: str | None = None) -> dict:
        """Generate a single-use 24-hour teacher pairing code. Omit learner_id to invite a student's own existing profile; specify it to recover the teacher-created profile. Share only with the intended student."""
        return service.create_pair_code(learner_id)

    @server.tool()
    def revoke_pair_code(code_id: str) -> dict:
        """Revoke a teacher-issued unused pairing code on explicit teacher request."""
        return service.revoke_pair_code(code_id)

    @server.tool()
    def remove_student_pairing(learner_id: str) -> dict:
        """Only on explicit teacher request: revoke teacher access while keeping the student's work and access intact."""
        service.require_paired(learner_id)
        return service.unpair(learner_id)

    @server.tool()
    def start_activity(
        learner_id: str, purpose: str, request_key: str, resource_id: str | None = None
    ) -> dict:
        """Assign diagnostic, practice, listening, retest, writing or speaking. Use same key on retries."""
        service.require_paired(learner_id)
        return service.start(learner_id, purpose, request_key, resource_id)

    @server.tool()
    def get_activity(activity_id: str) -> dict:
        """Read activity and submitted attempts. Answers hidden until submission."""
        service.require_task_pair(activity_id)
        return service.session(activity_id)

    @server.tool()
    def submit_answers(
        activity_id: str,
        answers: dict | None = None,
        text: str = "",
        files: list[str] | None = None,
        request_key: str = "",
        independent: bool = False,
    ) -> dict:
        """Record actual learner-provided answers only; never answer a diagnostic on their behalf silently."""
        service.require_task_pair(activity_id)
        return service.submit(
            activity_id, answers, text, files, request_key, independent
        )

    @server.tool()
    def record_feedback(
        submission_id: str,
        comment: str,
        next_step: str,
        judgement: str | None = None,
        scores: list[dict] | None = None,
        request_key: str | None = None,
    ) -> dict:
        """Save evidence-grounded teacher feedback; scores must match published rubric. Never fabricate human review."""
        return service.feedback(
            submission_id, comment, next_step, judgement, scores, request_key
        )

    @server.tool()
    def prepare_generation(learner_id: str) -> dict:
        """Read current weak skills and blueprint before agent-authored generation; does not call an LLM."""
        service.require_paired(learner_id)
        d = service.dashboard(learner_id)
        exam = d["person"]["exam"]
        return {
            "person": d["person"],
            "weak_skills": d["weak_skills"],
            "blueprint": BLUEPRINTS[exam],
            "requirements": [
                "Provide id, family_id, title, exam, blueprint, task_type, instructions, stimulus, source, items",
                "Each item: id, kind(mcq/gap/tfng), prompt, key(list), evidence, explanation, skill; MCQ options required",
                "Original work must preserve exam construct and valid evidence, not just change the title",
                "Import creates pending_review; a teacher must verify content and fully listen to audio before release",
            ],
        }

    @server.tool()
    def validate_pack(pack: dict) -> dict:
        """Structural check only. Does not assert semantic validity or audio listening review."""
        return service.validate_pack(pack)

    @server.tool()
    def save_draft_pack(pack: dict) -> dict:
        """Save an agent-authored original pack as pending review. Never auto-publish generated content."""
        return service.import_pack(pack)

    @server.tool()
    def list_packs() -> dict:
        """Read teacher inventory, provenance and review state."""
        return {"packs": service.resources()}

    @server.tool()
    def release_reviewed_pack(
        pack_id: str,
        reviewer: str,
        note: str,
        content_checked: bool = False,
        audio_listened: bool = False,
    ) -> dict:
        """Only after explicit actual teacher content review/listening. Records attestation and a version hash."""
        return service.review_pack(
            pack_id, reviewer, note, audio_listened, content_checked
        )

    @server.tool()
    def set_activity_state(activity_id: str, state: str) -> dict:
        """Teacher requested active/paused/archived state; immediately enforced on student submissions."""
        service.require_task_pair(activity_id)
        return service.base.set_state(activity_id, state)

    @server.tool()
    def verify_transfer(submission_id: str, context: str, independent: bool) -> dict:
        """Record actual teacher confirmation of new-context independent work after meets_criteria review."""
        service.require_submission_pair(submission_id)
        return service.base.verify_transfer(submission_id, context, independent)

    @server.tool()
    def save_opportunity_goal(
        learner_id: str, target: str, url: str = "", gaps: list[dict] | None = None
    ) -> dict:
        """投石问路 bridge: requirement→evidence gap→activities→completion standards; unknown is not zero."""
        service.require_paired(learner_id)
        return service.save_goal(learner_id, target, url, gaps)

    return server


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(override=False)
    create_mcp(GrowthService(os.environ.get("BASE_DATA", "data/growth"))).run(
        transport="stdio"
    )

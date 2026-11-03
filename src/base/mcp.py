"""Local stdio tools run as the instance maintainer. Never give this to learners."""
import os
from mcp.server.fastmcp import FastMCP
from base.core import Store
from base.app.activities import generation_context
from base.teaching import check_activity as review_activity

server = FastMCP('base')


def store():
    return Store(os.environ.get('BASE_DATA', 'data/base'))


@server.tool()
def get_context() -> dict:
    """Read the editable business context, material and generation prompt."""
    return generation_context()


@server.tool()
def check_activity(draft: dict) -> dict:
    """Check a draft without publishing. Errors do not mean semantic review passed."""
    try:
        return review_activity(draft)
    except ValueError as error:
        return {'valid': False, 'error': str(error)}


@server.tool()
def create_activity(learner: str, draft: dict, request_key: str, learner_id: str | None = None) -> dict:
    """Explicit maintainer action: publish a checked activity and return its relative learning URL. Confirm content before calling."""
    result = store().create(learner, draft, request_key, learner_id)
    return {**result, 'student_path': '/learn/' + result['token']}


@server.tool()
def list_records() -> dict:
    """Private maintainer records. Do not disclose other learners' data."""
    service = store()
    return {'instance_id': service.instance_id, 'learners': service.learners(), 'tasks': service.tasks(), 'submissions': service.submissions()}


@server.tool()
def record_feedback(submission_id: str, comment: str, next_step: str, scores: list[dict] | None = None, judgement: str | None = None, request_key: str | None = None) -> dict:
    """Save maintainer-authorized feedback and next action."""
    return store().feedback(submission_id, comment, next_step, scores, judgement, request_key)


@server.tool()
def save_learner(name: str, profile: dict | None = None, learner_id: str | None = None, request_key: str | None = None) -> dict:
    """Create a new identity, or explicitly update an existing one. Never match by name."""
    return store().save_learner(name, profile, learner_id, request_key)


@server.tool()
def get_growth(learner_id: str) -> dict:
    """Read private evidence counts and history, not an inferred mastery score."""
    return store().growth(learner_id)


@server.tool()
def plan_next(learner_id: str) -> dict:
    """Use the ordinary editable app/strategy.py function to suggest a next step."""
    return store().next_plan(learner_id)


@server.tool()
def set_activity_state(task_id: str, state: str) -> dict:
    """Pause, resume or archive. Archive is read-only; it cannot be reopened."""
    return store().set_state(task_id, state)


@server.tool()
def verify_transfer(submission_id: str, context: str, independent: bool) -> dict:
    """Maintainer attestation of a reviewed new-context independent work; never infer from scores."""
    return store().verify_transfer(submission_id, context, independent)


if __name__ == '__main__':
    server.run(transport='stdio')

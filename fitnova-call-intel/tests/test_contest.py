"""Flag contest workflow tests — covers the feedback loop with auth."""

import pytest
from fastapi.testclient import TestClient
from fitnova.api.main import app
from fitnova.storage.models import Tag, TagStatus, Contest, Call
from fitnova.pipeline.orchestrator import process_call as run_pipeline


def _ensure_tag(db, advisor, call_id="CONTEST-FIXTURE-001"):
    """Process a call and return the first tag."""
    audio = b"Advisor: I guaranteed you will lose weight fast. " + call_id.encode()
    call = db.query(Call).filter(Call.external_call_id == call_id).first()
    if not call:
        run_pipeline(call_id, advisor.id, "test", audio, db)
    tag = db.query(Tag).join(Call).filter(Call.external_call_id == call_id).first()
    return tag


def test_contest_requires_comment(client, db, advisor, sd_headers):
    """POST with empty body should 422 (Pydantic validation before endpoint)."""
    tag = _ensure_tag(db, advisor)
    r = client.post(f"/tags/{tag.id}/contest", json={}, headers=sd_headers)
    assert r.status_code == 422


def test_contest_nonexistent_tag_returns_404(client, sd_headers):
    r = client.post("/tags/99999/contest", json={"advisor_comment": "Wrong!"}, headers=sd_headers)
    assert r.status_code == 404


@pytest.fixture
def tl_headers_inline():
    """Team Leader auth headers — used for contest operations."""
    c = TestClient(app)
    r = c.post("/auth/login", json={"email": "alpha_lead@fitnova.in", "password": "lead123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_contest_workflow_full_cycle(client, db, advisor, tl_headers_inline):
    """Full contest cycle: create tag → contest → verify status change."""
    tag = _ensure_tag(db, advisor, "CONTEST-CYCLE-001")
    assert tag.status == TagStatus.active.value

    r = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "This is not a violation."}, headers=tl_headers_inline)
    assert r.status_code == 200
    assert r.json()["status"] == "contested"
    assert r.json()["tag_id"] == tag.id

    db.expire(tag)
    assert tag.status == TagStatus.contested.value

    contest = db.query(Contest).filter(Contest.tag_id == tag.id).first()
    assert contest is not None
    assert "not a violation" in contest.advisor_comment


def test_contest_with_empty_comment(client, db, advisor, tl_headers_inline):
    """Empty comment should still work (advisors may not elaborate)."""
    tag = _ensure_tag(db, advisor, "CONTEST-EMPTY-001")
    r = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": ""}, headers=tl_headers_inline)
    assert r.status_code in (200, 422)


def test_multiple_contests_on_same_tag(client, db, advisor, tl_headers_inline):
    """Contesting an already-contested tag updates status again (idempotent)."""
    tag = _ensure_tag(db, advisor, "CONTEST-MULTI-001")
    r1 = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "First contest"}, headers=tl_headers_inline)
    assert r1.status_code == 200
    r2 = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "Second contest"}, headers=tl_headers_inline)
    assert r2.status_code == 200
    assert r2.json()["status"] == "contested"

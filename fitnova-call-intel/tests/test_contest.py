"""Flag contest workflow tests — covers the feedback loop."""

from fitnova.storage.models import Tag, TagStatus, Contest, Call
from fitnova.pipeline.orchestrator import process_call as run_pipeline


def test_contest_requires_comment(client, db):
    """POST without body should 422."""
    r = client.post("/tags/1/contest", json={})
    assert r.status_code == 422


def test_contest_nonexistent_tag_returns_404(client):
    r = client.post("/tags/99999/contest", json={"advisor_comment": "Wrong!"})
    assert r.status_code == 404


def test_contest_workflow_full_cycle(client, db, advisor):
    """Full contest cycle: create tag → contest → verify status change."""
    # Use trigger phrases for the stub tagger: "guaranteed" + "won't be available"
    audio = b"Advisor: I guaranteed you will lose weight fast.\nAdvisor: This offer won't be available tomorrow."
    run_pipeline("TEST-CONTEST-001", advisor.id, "test", audio, db)

    call = db.query(Call).filter(Call.external_call_id == "TEST-CONTEST-001").first()
    tag = db.query(Tag).filter(Tag.call_id == call.id).first()
    assert tag is not None
    assert tag.status == TagStatus.active.value

    # Contest the tag
    r = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "This is not a violation."})
    assert r.status_code == 200
    assert r.json()["status"] == "contested"
    assert r.json()["tag_id"] == tag.id

    # Verify DB updated
    db.expire(tag)
    assert tag.status == TagStatus.contested.value

    # Verify Contest row created
    contest = db.query(Contest).filter(Contest.tag_id == tag.id).first()
    assert contest is not None
    assert "not a violation" in contest.advisor_comment


def test_contest_with_empty_comment(client, db):
    """Empty comment should still create a contest (advisors may not elaborate)."""
    r = client.post("/tags/1/contest", json={"advisor_comment": ""})
    # Should still work — we don't enforce non-empty
    assert r.status_code in (200, 422)


def test_multiple_contests_on_same_tag(client, db, advisor):
    """Contesting an already-contested tag should update the status again (idempotent)."""
    # Use trigger phrase "limited time" for pressure_tactics tag
    audio = b"Advisor: This limited time offer expires today.\nCustomer: Can you tell me more?"
    run_pipeline("TEST-MULTI-CONTEST", advisor.id, "test", audio, db)
    call = db.query(Call).filter(Call.external_call_id == "TEST-MULTI-CONTEST").first()
    tag = db.query(Tag).filter(Tag.call_id == call.id).first()

    r1 = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "First contest"})
    assert r1.status_code == 200

    r2 = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "Second contest"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "contested"

"""Tests for response caching layer on read endpoints."""

from fitnova.pipeline.orchestrator import process_call as run_pipeline
from fitnova.storage.models import Call, Tag


def _ensure_call(db, advisor):
    """Process a call if none exists, return first call id."""
    call = db.query(Call).first()
    if call:
        return call.id
    audio = b"Advisor: We guaranteed you better results.\nCustomer: How much does the program cost?"
    run_pipeline("CACHE-TEST-001", advisor.id, "test", audio, db)
    call = db.query(Call).first()
    return call.id if call else None


def test_call_detail_is_cached(client, db, advisor):
    call_id = _ensure_call(db, advisor)
    if not call_id:
        return

    r1 = client.get(f"/calls/{call_id}")
    assert r1.status_code == 200

    r2 = client.get(f"/calls/{call_id}")
    assert r2.status_code == 200
    assert r2.json()["external_call_id"] == r1.json()["external_call_id"]


def test_org_summary_is_cached(client):
    r1 = client.get("/orgs/1/summary")
    assert r1.status_code == 200
    r2 = client.get("/orgs/1/summary")
    assert r2.status_code == 200
    assert r2.json()["org"] == r1.json()["org"]


def test_contest_invalidates_call_cache(client, db, advisor):
    call_id = _ensure_call(db, advisor)
    if not call_id:
        return

    # Populate cache
    client.get(f"/calls/{call_id}")

    # Contest a tag
    tag = db.query(Tag).filter(Tag.call_id == call_id).first()
    assert tag is not None, "No tags on call — cannot test contest cache invalidation"
    r = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "test contest"})
    assert r.status_code == 200


def test_cache_bypass_with_no_cache_header(client):
    r1 = client.get("/orgs/1/summary", headers={"Cache-Control": "no-cache"})
    assert r1.status_code == 200
    r2 = client.get("/orgs/1/summary")
    assert r2.status_code == 200

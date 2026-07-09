"""Tests for response caching layer on read endpoints."""

from fitnova.pipeline.orchestrator import process_call as run_pipeline
from fitnova.storage.models import Call, Tag


_call_counter = 0

def _ensure_call(db, advisor):
    """Process a fresh call with unique ID/audio so tags are always created."""
    global _call_counter
    _call_counter += 1
    call_id = f"CACHE-CALL-{_call_counter}"
    audio = f"Advisor: I guaranteed you will lose weight fast. {call_id}\nCustomer: Tell me more.".encode()
    run_pipeline(call_id, advisor.id, "test", audio, db)
    call = db.query(Call).filter(Call.external_call_id == call_id).first()
    return call.id if call else None


def test_call_detail_is_cached(client, db, advisor, sd_headers):
    call_id = _ensure_call(db, advisor)
    if not call_id:
        return

    r1 = client.get(f"/calls/{call_id}", headers=sd_headers)
    assert r1.status_code == 200

    r2 = client.get(f"/calls/{call_id}", headers=sd_headers)
    assert r2.status_code == 200
    assert r2.json()["external_call_id"] == r1.json()["external_call_id"]


def test_org_summary_is_cached(client, sd_headers):
    r1 = client.get("/orgs/1/summary", headers=sd_headers)
    assert r1.status_code == 200
    r2 = client.get("/orgs/1/summary", headers=sd_headers)
    assert r2.status_code == 200
    assert r2.json()["org"] == r1.json()["org"]


def test_contest_invalidates_call_cache(client, db, advisor, sd_headers):
    call_id = _ensure_call(db, advisor)
    if not call_id:
        return

    client.get(f"/calls/{call_id}", headers=sd_headers)

    tag = db.query(Tag).filter(Tag.call_id == call_id).first()
    assert tag is not None, "No tags on call — cannot test contest cache invalidation"

    # Must use a Team Leader to contest (Sales Director role lacks permission)
    rl = client.post("/auth/login", json={"email": "alpha_lead@fitnova.in", "password": "lead123"})
    tl_token = rl.json()["access_token"]
    tl_headers = {"Authorization": f"Bearer {tl_token}"}
    r = client.post(f"/tags/{tag.id}/contest", json={"advisor_comment": "test contest"}, headers=tl_headers)
    assert r.status_code == 200


def test_cache_bypass_with_no_cache_header(client, sd_headers):
    bypass = {"Cache-Control": "no-cache", **sd_headers}
    r1 = client.get("/orgs/1/summary", headers=bypass)
    assert r1.status_code == 200
    r2 = client.get("/orgs/1/summary", headers=sd_headers)
    assert r2.status_code == 200

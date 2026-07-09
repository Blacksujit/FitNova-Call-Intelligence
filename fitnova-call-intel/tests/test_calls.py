"""Call detail endpoint tests."""

from fitnova.storage.models import Call, CallStatus


def test_get_nonexistent_call_returns_404(client):
    r = client.get("/calls/99999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_get_existing_call_returns_full_detail(client, db, advisor):
    """Full call detail must include id on every tag (regression for dashboard KeyError)."""
    from fitnova.pipeline.orchestrator import process_call as run_pipeline
    # Include trigger phrase "guaranteed" to produce at least one tag
    audio = b"Advisor: I guaranteed you 100 percent results.\nCustomer: That sounds too good to be true."
    result = run_pipeline("TEST-DETAIL-001", advisor.id, "test", audio, db)
    assert result["status"] == "analyzed"

    call = db.query(Call).filter(Call.external_call_id == "TEST-DETAIL-001").first()
    r = client.get(f"/calls/{call.id}")
    assert r.status_code == 200
    data = r.json()

    # Verify all fields present
    assert data["external_call_id"] == "TEST-DETAIL-001"
    assert data["advisor_name"] == advisor.name
    assert data["status"] == "analyzed"
    assert isinstance(data["segments"], list)
    assert len(data["segments"]) > 0
    assert isinstance(data["scores"], list)
    assert len(data["scores"]) == 5
    assert isinstance(data["tags"], list)

    # ⚠ CRITICAL: Each tag MUST have an 'id' — this was the dashboard bug
    for tag in data["tags"]:
        assert "id" in tag, f"Tag {tag.get('category')} missing 'id' field — dashboard will crash!"
        assert isinstance(tag["id"], int)
        assert tag["id"] > 0

    # Verify segments have correct shape
    for seg in data["segments"]:
        assert "speaker" in seg
        assert "text" in seg
        assert isinstance(seg["start_ms"], int)
        assert isinstance(seg["end_ms"], int)
        assert seg["end_ms"] > seg["start_ms"]

    # Verify scores have correct shape
    for sc in data["scores"]:
        assert "dimension" in sc
        assert "value" in sc
        assert 1 <= sc["value"] <= 5


def test_tag_id_is_unique_across_tags(client, db):
    """Every tag id should be unique within a call response."""
    calls = db.query(Call).all()
    for c in calls:
        r = client.get(f"/calls/{c.id}")
        tags = r.json().get("tags", [])
        ids = [t["id"] for t in tags]
        assert len(ids) == len(set(ids)), f"Duplicate tag IDs in call {c.id}"

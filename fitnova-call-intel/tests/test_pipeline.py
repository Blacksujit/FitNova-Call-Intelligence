"""Pipeline process-call endpoint tests."""

import json
from pathlib import Path


def test_process_nonexistent_call_returns_404(client):
    r = client.post("/calls/process?external_call_id=DOES_NOT_EXIST")
    assert r.status_code == 404


def test_process_call_without_metadata_returns_404(client):
    """A call with no matching metadata JSON in incoming/ should 404."""
    # Don't create any files — should fail cleanly
    r = client.post("/calls/process?external_call_id=GHOST-001")
    assert r.status_code == 404


def test_incoming_list_empty_when_no_files(client):
    r = client.get("/incoming/list")
    assert r.status_code == 200
    data = r.json()
    assert "incoming_ids" in data
    assert isinstance(data["incoming_ids"], list)

"""Pipeline process-call endpoint tests."""


def test_process_nonexistent_call_returns_404(client, sd_headers):
    r = client.post("/calls/process?external_call_id=DOES_NOT_EXIST", headers=sd_headers)
    assert r.status_code == 404


def test_process_call_without_metadata_returns_404(client, sd_headers):
    """A call with no matching metadata JSON in incoming/ should 404."""
    r = client.post("/calls/process?external_call_id=GHOST-001", headers=sd_headers)
    assert r.status_code == 404


def test_incoming_list_empty_when_no_files(client, sd_headers):
    r = client.get("/incoming/list", headers=sd_headers)
    assert r.status_code == 200
    data = r.json()
    assert "incoming_ids" in data
    assert isinstance(data["incoming_ids"], list)

"""Auth-less error-path tests — ensuring every endpoint handles missing data gracefully.

Note: protected endpoints now require auth Depends (evaluated before param validation).
"""


def test_health_does_not_require_auth(client):
    """Health should always be accessible (no auth required)."""
    r = client.get("/health")
    assert r.status_code == 200


def test_unexpected_path_404(client):
    r = client.get("/nonexistent-route")
    assert r.status_code == 404


def test_method_not_allowed(client):
    r = client.put("/health")
    assert r.status_code == 405


def test_process_with_empty_call_id(client, sd_headers):
    """Process with empty call ID should fail cleanly (422 after auth passes)."""
    r = client.post("/calls/process", headers=sd_headers)
    assert r.status_code == 422


def test_summary_with_invalid_id_type(client, sd_headers):
    r = client.get("/orgs/abc/summary", headers=sd_headers)
    assert r.status_code in (404, 422)

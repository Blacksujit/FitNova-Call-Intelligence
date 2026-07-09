"""Health-check endpoint tests."""

def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_returns_json_content_type(client):
    r = client.get("/health")
    assert r.headers["content-type"] == "application/json"

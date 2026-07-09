"""Tests for rate limiter queue fallback (202 vs 429)."""

from unittest.mock import patch

from fitnova.api import queue as tq


def test_process_rate_limit_queues_instead_of_429(client):
    """When process limit is hit, the middleware should return 202 with a task_id.
    Middleware intercepts before auth Depends, so no auth headers needed."""
    from fitnova.api.ratelimit import RATE_LIMITS

    with patch.dict(RATE_LIMITS, {"process": (0, 60)}):
        r = client.post("/calls/process?external_call_id=DEMO-001")
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "queued"
        assert "task_id" in body
        assert len(body["task_id"]) > 0
        assert "Location" in r.headers
        assert r.headers["Location"] == f"/tasks/{body['task_id']}"
        assert "X-Task-Id" in r.headers
        assert r.headers["X-Task-Id"] == body["task_id"]


def test_queued_task_can_be_polled(client, sd_headers):
    """After queuing, the task status endpoint should return the task details."""
    task = tq.enqueue("process_call", '{"external_call_id": "QUEUE-TEST"}')
    r = client.get(f"/tasks/{task.id}", headers=sd_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == task.id
    assert data["status"] in ("pending", "running", "done", "failed")


def test_nonprocess_rate_limit_still_returns_429(client):
    """Non-process endpoints should still hard-reject with 429."""
    from fitnova.api.ratelimit import RATE_LIMITS

    with patch.dict(RATE_LIMITS, {"global": (0, 60)}):
        r = client.get("/health")
        assert r.status_code == 429
        assert "rate limit" in r.json()["detail"].lower()

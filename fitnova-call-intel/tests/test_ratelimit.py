"""Rate-limit middleware tests."""

import time

from fitnova.api.ratelimit import SlidingWindowCounter, RATE_LIMITS


class TestSlidingWindowCounter:
    def test_allows_within_limit(self):
        c = SlidingWindowCounter()
        allowed, remaining, _ = c.hit("ip:a", 5, 10)
        assert allowed is True
        assert remaining == 4

    def test_blocks_after_limit(self):
        c = SlidingWindowCounter()
        key = "ip:block-test"
        for _ in range(3):
            allowed, _, _ = c.hit(key, 3, 60)
            assert allowed is True
        allowed, remaining, retry = c.hit(key, 3, 60)
        assert allowed is False
        assert remaining == 0
        assert retry > 0

    def test_resets_after_window(self):
        c = SlidingWindowCounter()
        key = "ip:window-test"
        for _ in range(2):
            c.hit(key, 2, 1)  # 1-second window
        allowed, _, _ = c.hit(key, 2, 1)
        assert allowed is False
        time.sleep(1.1)
        allowed, _, _ = c.hit(key, 2, 1)
        assert allowed is True

    def test_different_keys_independent(self):
        c = SlidingWindowCounter()
        c.hit("ip:a", 1, 60)
        allowed, _, _ = c.hit("ip:b", 1, 60)
        assert allowed is True


def test_rate_limit_headers_on_regular_request(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers


def test_rate_limit_429_returns_proper_body(client):
    """Hammer the health endpoint to trigger a 429 under low limits."""
    from fitnova.api.ratelimit import RATE_LIMITS
    from unittest.mock import patch

    # Temporarily drop global limit so we hit it
    with patch.dict(RATE_LIMITS, {"global": (3, 60)}):
        for _ in range(3):
            client.get("/health")
        r = client.get("/health")
        assert r.status_code == 429
        body = r.json()
        assert "rate limit" in body["detail"].lower()
        assert "retry_after_seconds" in body

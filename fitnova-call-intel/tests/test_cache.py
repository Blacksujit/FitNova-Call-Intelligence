"""Tests for in-memory TTL cache."""

import time
from fitnova.api.cache import TTLCache


class TestTTLCache:
    def test_set_and_get(self):
        c = TTLCache()
        c.set("a", {"value": 1}, ttl=60)
        assert c.get("a") == {"value": 1}

    def test_expiry(self):
        c = TTLCache()
        c.set("b", {"value": 2}, ttl=1)
        assert c.get("b") == {"value": 2}
        time.sleep(1.1)
        assert c.get("b") is None

    def test_missing_key(self):
        c = TTLCache()
        assert c.get("nonexistent") is None

    def test_invalidate_prefix(self):
        c = TTLCache()
        c.set("call_detail:1", {"id": 1}, ttl=60)
        c.set("call_detail:2", {"id": 2}, ttl=60)
        c.set("org_summary:1", {"org": "x"}, ttl=60)
        c.invalidate("call_detail")
        assert c.get("call_detail:1") is None
        assert c.get("call_detail:2") is None
        assert c.get("org_summary:1") == {"org": "x"}

    def test_clear(self):
        c = TTLCache()
        c.set("x", {}, ttl=60)
        c.clear()
        assert c.size == 0

    def test_overwrite(self):
        c = TTLCache()
        c.set("k", {"v": 1}, ttl=60)
        c.set("k", {"v": 2}, ttl=60)
        assert c.get("k") == {"v": 2}

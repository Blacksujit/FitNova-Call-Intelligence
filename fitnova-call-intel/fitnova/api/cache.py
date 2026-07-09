"""
In-memory TTL response cache for read-heavy endpoints.

Stores API response dicts with configurable per-endpoint TTLs.
Thread-safe via a single RLock.
"""

import time
import threading
import logging

logger = logging.getLogger(__name__)

DEFAULT_TTL: dict[str, int] = {
    "call_detail": 60,
    "org_summary": 30,
    "team_summary": 30,
    "advisor_summary": 30,
}


class TTLCache:
    def __init__(self):
        self._lock = threading.RLock()
        self._store: dict[str, tuple[float, dict]] = {}

    def get(self, key: str) -> dict | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: dict, ttl: int):
        with self._lock:
            self._store[key] = (time.time() + ttl, value)

    def invalidate(self, prefix: str):
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]
            if keys:
                logger.debug("Invalidated %d cache keys with prefix '%s'", len(keys), prefix)

    def clear(self):
        with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


_cache = TTLCache()


def cache_get(key: str) -> dict | None:
    return _cache.get(key)


def cache_set(key: str, value: dict, ttl: int | None = None):
    _cache.set(key, value, ttl or DEFAULT_TTL.get(key.split(":")[0], 60))


def cache_invalidate(prefix: str):
    _cache.invalidate(prefix)


def cache_clear():
    _cache.clear()

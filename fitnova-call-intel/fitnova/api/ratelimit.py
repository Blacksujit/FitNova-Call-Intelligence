"""
In-memory rate limiter for FastAPI endpoints.
Sliding-window count per client IP with configurable limits.

When the process bucket is exceeded, returns 202 Accepted with
a task-location header instead of 429, so the client can poll.
"""

import time
import logging
import json
from collections import defaultdict
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from . import queue as task_queue

logger = logging.getLogger(__name__)


class SlidingWindowCounter:
    def __init__(self):
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def _prune(self, key: str, window_s: int):
        now = time.monotonic()
        self._buckets[key] = [t for t in self._buckets[key] if now - t < window_s]

    def hit(self, key: str, max_count: int, window_s: int) -> tuple[bool, int, int]:
        self._prune(key, window_s)
        hits = len(self._buckets[key])
        if hits >= max_count:
            oldest = self._buckets[key][0] if self._buckets[key] else time.monotonic()
            retry_after = int(window_s - (time.monotonic() - oldest))
            return False, 0, max(1, retry_after)
        self._buckets[key].append(time.monotonic())
        return True, max_count - hits - 1, 0


_counter = SlidingWindowCounter()


RATE_LIMITS: dict[str, tuple[int, int]] = {
    "global":  (100,  60),
    "process": (10,   60),
    "contest": (20,   60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        if path.startswith("/calls/process"):
            limit_key = "process"
        elif path.startswith("/tags/") and request.method == "POST":
            limit_key = "contest"
        else:
            limit_key = "global"

        max_count, window_s = RATE_LIMITS.get(limit_key, RATE_LIMITS["global"])
        global_key = f"{client_ip}:{limit_key}"
        allowed, remaining, retry_after = _counter.hit(global_key, max_count, window_s)

        if not allowed:
            logger.warning("Rate limit exceeded for %s on %s — queuing request", client_ip, path)
            # For process calls, accept via queue instead of hard-rejecting
            if path.startswith("/calls/process"):
                params = {"external_call_id": request.query_params.get("external_call_id", "")}
                task = task_queue.enqueue("process_call", json.dumps(params))
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "queued",
                        "task_id": task.id,
                        "message": "Rate limited — call queued for processing. Poll GET /tasks/{task_id} for status.",
                    },
                    headers={
                        "X-Task-Id": task.id,
                        "Location": f"/tasks/{task.id}",
                        "X-RateLimit-Limit": str(max_count),
                        "X-RateLimit-Remaining": "0",
                        "Retry-After": str(retry_after),
                    },
                )
            # For other endpoints, return 429
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Try again shortly.",
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "X-RateLimit-Limit": str(max_count),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(retry_after),
                    "Retry-After": str(retry_after),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_count)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

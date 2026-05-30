"""In-memory request rate limiting for the local web API."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
import time
from typing import Deque


@dataclass(frozen=True)
class RateLimitPolicy:
    window_seconds: int = 60
    read_requests: int = 180
    write_requests: int = 60
    submit_requests: int = 12


class RequestRateLimiter:
    def __init__(self, policy: RateLimitPolicy | None = None) -> None:
        self.policy = policy or RateLimitPolicy()
        self._buckets: dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, *, key: str, method: str, path: str, now: float | None = None) -> dict:
        current = time.monotonic() if now is None else float(now)
        limit = self._limit_for(method=method, path=path)
        window = max(1, int(self.policy.window_seconds))
        bucket_key = f"{key or 'anonymous'}:{self._scope_for(method=method, path=path)}"
        with self._lock:
            bucket = self._buckets.setdefault(bucket_key, deque())
            cutoff = current - window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry_after = max(1, int(round(window - (current - bucket[0]))))
                return {
                    "ok": False,
                    "error_code": "RATE_LIMITED",
                    "error": "too many requests; retry later",
                    "retry_after": retry_after,
                    "limit": limit,
                    "window_seconds": window,
                }
            bucket.append(current)
        return {"ok": True}

    def _limit_for(self, *, method: str, path: str) -> int:
        if path in {"/api/submit", "/api/submit_batch"}:
            return max(1, int(self.policy.submit_requests))
        if str(method).upper() not in {"GET", "HEAD", "OPTIONS"}:
            return max(1, int(self.policy.write_requests))
        return max(1, int(self.policy.read_requests))

    def _scope_for(self, *, method: str, path: str) -> str:
        if path in {"/api/submit", "/api/submit_batch"}:
            return "submit"
        if str(method).upper() not in {"GET", "HEAD", "OPTIONS"}:
            return "write"
        return "read"

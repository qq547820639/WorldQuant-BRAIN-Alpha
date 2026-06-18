"""Request rate limiter for the web console."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque


@dataclass(frozen=True)
class RateLimitPolicy:
    """Separate sliding-window quotas for read, write, and submit routes."""

    window_seconds: float = 1.0
    read_requests: int = 60
    write_requests: int = 20
    submit_requests: int = 5


class RequestRateLimiter:
    """Thread-safe sliding-window rate limiter with per-client buckets."""

    def __init__(
        self,
        policy: RateLimitPolicy | None = None,
        *,
        window_seconds: float | None = None,
        max_requests: int | None = None,
    ) -> None:
        if policy is None:
            limit = int(max_requests if max_requests is not None else 10)
            policy = RateLimitPolicy(
                window_seconds=float(window_seconds if window_seconds is not None else 1.0),
                read_requests=limit,
                write_requests=limit,
                submit_requests=limit,
            )
        self.policy = policy
        self._timestamps: dict[tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(
        self,
        *,
        key: str = "",
        client_addr: str = "",
        method: str = "",
        path: str = "",
        now: float | None = None,
    ) -> dict[str, object]:
        """Return a structured allow/deny decision for a request."""
        current = time.monotonic() if now is None else float(now)
        bucket = self._bucket_for(method, path)
        limit = self._limit_for(bucket)
        identity = str(key or "").strip() or f"client:{str(client_addr or '').strip() or 'anonymous'}"
        cache_key = (identity, bucket)
        window = max(0.001, float(self.policy.window_seconds))

        with self._lock:
            timestamps = self._timestamps[cache_key]
            cutoff = current - window
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(0.001, window - (current - timestamps[0]))
                return {
                    "ok": False,
                    "error_code": "RATE_LIMITED",
                    "error": f"Too many {bucket} requests; retry after {retry_after:.2f}s.",
                    "bucket": bucket,
                    "limit": limit,
                    "window_seconds": window,
                    "retry_after": retry_after,
                }
            timestamps.append(current)
            return {
                "ok": True,
                "bucket": bucket,
                "limit": limit,
                "window_seconds": window,
                "retry_after": 0.0,
            }

    @staticmethod
    def _bucket_for(method: str, path: str) -> str:
        method_upper = str(method or "GET").upper()
        path_value = str(path or "")
        if method_upper == "POST" and "submit" in path_value:
            return "submit"
        if method_upper in {"GET", "HEAD", "OPTIONS"}:
            return "read"
        return "write"

    def _limit_for(self, bucket: str) -> int:
        if bucket == "submit":
            return max(1, int(self.policy.submit_requests))
        if bucket == "write":
            return max(1, int(self.policy.write_requests))
        return max(1, int(self.policy.read_requests))

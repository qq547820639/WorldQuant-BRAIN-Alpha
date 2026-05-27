"""Adaptive task executor with intelligent thread/process pool selection.

Selects executor backend based on task characteristics:
- I/O-bound tasks (API calls, file I/O) → ThreadPoolExecutor
- CPU-bound tasks (scoring, expression parsing) → ProcessPoolExecutor
- Unknown / mixed → ThreadPoolExecutor (safer default)

Provides:
- AdaptiveExecutor: auto-selects pool type per task.
- CachedAPIRateLimiter: TTL-based cache for API responses with retry.
"""

from __future__ import annotations

from concurrent.futures import (
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    TimeoutError,
)
from dataclasses import dataclass, field
import logging
import os
import threading
import time
from typing import Any, Callable

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.tasks import JobStore

logger = logging.getLogger(__name__)


# ── Task type classification ──

class TaskCategory:
    IO_BOUND = "io"
    CPU_BOUND = "cpu"
    DEFAULT = "default"


def _classify_task(fn: Callable[..., Any]) -> str:
    """Heuristic classification of task function based on module name.

    Uses whole-word / boundary matching to avoid false positives
    (e.g. 'io' matching inside 'classification').
    """
    import re
    mod = getattr(fn, "__module__", "") or ""
    qualname = getattr(fn, "__qualname__", "") or ""
    combined = f"{mod}.{qualname}".lower()
    # Split into tokens at module path boundaries
    tokens = set(re.split(r"[._]", combined))

    io_keywords = {"api", "http", "request", "fetch", "web", "io", "network",
                   "upload", "download", "read", "write", "jsonl", "sqlite"}
    cpu_keywords = {"score", "compute", "calculate", "expression", "parse",
                    "validate", "matrix", "vector", "generate", "evaluate",
                    "scoring", "fitness"}

    if tokens & cpu_keywords:
        return TaskCategory.CPU_BOUND
    if tokens & io_keywords:
        return TaskCategory.IO_BOUND
    return TaskCategory.DEFAULT


# ── Adaptive Executor ──

class AdaptiveExecutor:
    """Executor that auto-selects thread/process pool per task.

    On Windows, ProcessPoolExecutor requires picklable tasks and the
    __main__ guard pattern.  When a ProcessPoolExecutor submission fails
    due to pickling errors, the executor automatically falls back to the
    thread pool so that callers do not have to handle platform differences.

    Usage:
        executor = AdaptiveExecutor()
        future = executor.submit(my_io_task, arg1, arg2)
        future = executor.submit(my_cpu_task, arg1, arg2)
        executor.shutdown()
    """

    def __init__(
        self,
        *,
        io_workers: int | None = None,
        cpu_workers: int | None = None,
    ):
        self._io_workers = io_workers or int(
            os.environ.get("BRAIN_ALPHA_IO_WORKERS", "8")
        )
        self._cpu_workers = cpu_workers or int(
            os.environ.get("BRAIN_ALPHA_CPU_WORKERS", str(max(1, min(os.cpu_count() or 1, 4))))
        )
        self._io_pool: ThreadPoolExecutor | None = None
        self._cpu_pool: ProcessPoolExecutor | None = None
        self._cpu_fallback_warned = False
        self._lock = threading.Lock()

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        category: str | None = None,
        **kwargs: Any,
    ) -> Future:
        """Submit a task; pool is auto-selected unless *category* is explicit."""
        cat = category or _classify_task(fn)
        if cat == TaskCategory.CPU_BOUND:
            return self._submit_cpu(fn, *args, **kwargs)
        else:
            return self._get_io_pool().submit(fn, *args, **kwargs)

    def _submit_cpu(
        self, fn: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Future:
        """Submit to cpu pool, falling back to io pool on pickling errors."""
        try:
            return self._get_cpu_pool().submit(fn, *args, **kwargs)
        except (TypeError, AttributeError, RuntimeError) as exc:
            if not self._cpu_fallback_warned:
                self._cpu_fallback_warned = True
                logger.warning(
                    "AdaptiveExecutor: CPU pool submission failed (%s), "
                    "falling back to thread pool for this task. "
                    "On Windows this is normal for non-picklable functions.",
                    exc,
                )
            return self._get_io_pool().submit(fn, *args, **kwargs)

    def shutdown(self) -> None:
        with self._lock:
            if self._io_pool is not None:
                self._io_pool.shutdown(wait=False, cancel_futures=True)
                self._io_pool = None
            if self._cpu_pool is not None:
                self._cpu_pool.shutdown(wait=False, cancel_futures=True)
                self._cpu_pool = None

    def _get_io_pool(self) -> ThreadPoolExecutor:
        with self._lock:
            if self._io_pool is None:
                self._io_pool = ThreadPoolExecutor(max_workers=self._io_workers)
            return self._io_pool

    def _get_cpu_pool(self) -> ProcessPoolExecutor:
        with self._lock:
            if self._cpu_pool is None:
                self._cpu_pool = ProcessPoolExecutor(max_workers=self._cpu_workers)
            return self._cpu_pool


# ── API Cache with TTL + Retry ──

@dataclass
class CacheEntry:
    value: Any
    created_at: float
    ttl_seconds: float

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl_seconds


class CachedAPIRateLimiter:
    """TTL cache for BRAIN API responses with retry backoff.

    Compatible with the OfficialBrainAPI request layer.

    Usage:
        cache = CachedAPIRateLimiter(ttl=3600)
        items = cache.get_or_fetch("fields:v1", lambda: api.list_fields())
    """

    def __init__(
        self,
        *,
        ttl: float = 86400.0,
        max_size: int = 200,
        max_retries: int = 3,
        base_retry_delay: float = 2.0,
        retry_backoff: float = 2.0,
    ):
        self.ttl = max(1.0, float(ttl))
        self.max_size = max(1, int(max_size))
        self.max_retries = max(0, int(max_retries))
        self.base_retry_delay = max(0.1, float(base_retry_delay))
        self.retry_backoff = max(1.0, float(retry_backoff))
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._hits: int = 0
        self._misses: int = 0

    def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Any],
        *,
        ttl: float | None = None,
    ) -> Any:
        """Return cached value if fresh, otherwise fetch and cache.

        Args:
            key: Cache key (e.g. "fields:USA:TOP3000").
            fetcher: Callable that returns the data when cache miss.
            ttl: Optional per-call TTL override.
        """
        effective_ttl = ttl if ttl is not None else self.ttl

        # Fast path: cache hit
        with self._lock:
            entry = self._cache.get(key)
        if entry is not None and not entry.expired:
            self._hits += 1
            return entry.value

        # Slow path: fetch with retry
        self._misses += 1
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                value = fetcher()
                with self._lock:
                    self._cache[key] = CacheEntry(
                        value=value,
                        created_at=time.monotonic(),
                        ttl_seconds=effective_ttl,
                    )
                    self._prune()
                return value
            except Exception as exc:
                last_error = exc
                if self._is_retryable(exc) and attempt < self.max_retries:
                    delay = self.base_retry_delay * (self.retry_backoff ** attempt)
                    logger.debug(
                        "CachedAPIRateLimiter: attempt %d/%d for %s failed (%s), "
                        "retrying in %.1fs",
                        attempt + 1, self.max_retries + 1, key,
                        redact_error_message(exc, max_length=100), delay,
                    )
                    time.sleep(delay)
                else:
                    break

        # All retries exhausted — serve stale if available
        if entry is not None:
            logger.warning(
                "CachedAPIRateLimiter: serving stale cache for %s (fetch failed: %s)",
                key, redact_error_message(last_error, max_length=120),
            )
            return entry.value
        raise last_error or RuntimeError(f"fetch failed for {key}")

    def invalidate(self, key: str | None = None) -> None:
        """Remove a key from cache, or clear all if key is None."""
        with self._lock:
            if key is None:
                self._cache.clear()
            else:
                self._cache.pop(key, None)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(
                    self._hits / max(self._hits + self._misses, 1), 4
                ),
            }

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        text = str(exc).lower()
        retryable = {"timed out", "timeout", "connection", "temporarily",
                     "rate limit", "too many requests", "500", "502", "503", "504"}
        return any(token in text for token in retryable)

    def _prune(self) -> None:
        if len(self._cache) <= self.max_size:
            return
        # Remove expired first, then oldest
        expired = [k for k, v in self._cache.items() if v.expired]
        for key in expired:
            self._cache.pop(key, None)
        if len(self._cache) > self.max_size:
            oldest = sorted(
                self._cache.items(), key=lambda kv: kv[1].created_at
            )[: len(self._cache) - self.max_size]
            for key, _ in oldest:
                self._cache.pop(key, None)


# ── Convenience: run job through adaptive executor ──

@dataclass
class JobExecutionResult:
    job_id: str
    status: str
    result: Any = None
    error: str = ""
    duration_seconds: float = 0.0


def run_adaptive_job(
    store: JobStore,
    executor: AdaptiveExecutor,
    fn: Callable[..., Any],
    *args: Any,
    timeout: float | None = None,
    job_id: str | None = None,
    category: str | None = None,
    **kwargs: Any,
) -> JobExecutionResult:
    """Run one function through the adaptive executor with lifecycle tracking."""
    active_job_id = job_id or store.create({"status": "queued"})
    started = time.perf_counter()

    if store.is_cancelled(active_job_id):
        msg = "task cancelled"
        store.update(active_job_id, status="cancelled", error=msg,
                     progress={"phase": "cancelled", "percent": 100, "message": msg})
        return JobExecutionResult(active_job_id, "cancelled", error=msg)

    store.update(active_job_id, status="running",
                 progress={"phase": "running", "percent": 5})
    future = executor.submit(fn, *args, category=category, **kwargs)

    try:
        result = future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        msg = "task timed out"
        logger.warning("adaptive_executor: job %s timed out after %.1fs",
                       active_job_id, timeout)
        store.update(active_job_id, status="failed", error=msg,
                     progress={"phase": "timeout", "percent": 100, "message": msg})
        return JobExecutionResult(active_job_id, "failed", error=msg,
                                  duration_seconds=round(time.perf_counter() - started, 3))
    except Exception as exc:
        msg = redact_error_message(exc)
        store.update(active_job_id, status="failed", error=msg,
                     progress={"phase": "failed", "percent": 100, "message": msg})
        return JobExecutionResult(active_job_id, "failed", error=msg,
                                  duration_seconds=round(time.perf_counter() - started, 3))

    if store.is_cancelled(active_job_id):
        msg = "task cancelled"
        store.update(active_job_id, status="cancelled", error=msg,
                     progress={"phase": "cancelled", "percent": 100, "message": msg})
        return JobExecutionResult(active_job_id, "cancelled", error=msg,
                                  duration_seconds=round(time.perf_counter() - started, 3))

    store.update(active_job_id, status="completed", result=result,
                 progress={"phase": "completed", "percent": 100})
    return JobExecutionResult(active_job_id, "completed", result=result,
                              duration_seconds=round(time.perf_counter() - started, 3))

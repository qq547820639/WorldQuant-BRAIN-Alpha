"""Small task execution abstraction shared by long-running operations."""

from __future__ import annotations

from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
import logging
import os
import time
from typing import Any, Callable

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.tasks import JobStore


logger = logging.getLogger(__name__)


class TaskExecutor:
    """Submit work to an execution backend."""

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        raise NotImplementedError

    def shutdown(self) -> None:
        raise NotImplementedError


class ThreadTaskExecutor(TaskExecutor):
    def __init__(self, max_workers: int | None = None):
        self.pool = ThreadPoolExecutor(max_workers=max_workers or int(os.environ.get("BRAIN_ALPHA_THREAD_WORKERS", "4")))

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        return self.pool.submit(fn, *args, **kwargs)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)


class ProcessTaskExecutor(TaskExecutor):
    def __init__(self, max_workers: int | None = None):
        self.pool = ProcessPoolExecutor(max_workers=max_workers or max(1, min(os.cpu_count() or 1, 4)))

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        return self.pool.submit(fn, *args, **kwargs)

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)


@dataclass
class JobExecutionResult:
    job_id: str
    status: str
    result: Any = None
    error: str = ""
    duration_seconds: float = 0.0


def run_job(
    store: JobStore,
    executor: TaskExecutor,
    fn: Callable[..., Any],
    *args: Any,
    timeout: float | None = None,
    job_id: str | None = None,
    **kwargs: Any,
) -> JobExecutionResult:
    """Run one function through an executor and persist lifecycle state."""
    active_job_id = job_id or store.create({"status": "queued"})
    started = time.perf_counter()
    if store.is_cancelled(active_job_id):
        message = "task cancelled"
        store.update(active_job_id, status="cancelled", error=message, progress={"phase": "cancelled", "percent": 100, "message": message})
        return JobExecutionResult(active_job_id, "cancelled", error=message, duration_seconds=0.0)
    store.update(active_job_id, status="running", progress={"phase": "running", "percent": 5})
    future = executor.submit(fn, *args, **kwargs)
    try:
        result = future.result(timeout=timeout)
    except TimeoutError:
        # Only catch the executor-level TimeoutError — business logic
        # TimeoutErrors (builtin) do NOT inherit from concurrent.futures
        # .TimeoutError and will NOT be caught here.
        future.cancel()
        # NOTE: ThreadPoolExecutor.cancel() cannot interrupt a thread that is
        # already running; the task *will* continue in the background.  We
        # log a warning so operators can detect resource leaks.
        message = "task timed out"
        logger.warning(
            "task_executor: job %s timed out after %.1fs — the background "
            "thread may still be running and will be leaked",
            active_job_id, timeout,
        )
        store.update(active_job_id, status="failed", error=message, progress={"phase": "timeout", "percent": 100, "message": message})
        return JobExecutionResult(active_job_id, "failed", error=message, duration_seconds=round(time.perf_counter() - started, 3))
    except Exception as exc:
        message = redact_error_message(exc)
        store.update(active_job_id, status="failed", error=message, progress={"phase": "failed", "percent": 100, "message": message})
        return JobExecutionResult(active_job_id, "failed", error=message, duration_seconds=round(time.perf_counter() - started, 3))
    if store.is_cancelled(active_job_id):
        message = "task cancelled"
        store.update(active_job_id, status="cancelled", error=message, progress={"phase": "cancelled", "percent": 100, "message": message})
        return JobExecutionResult(active_job_id, "cancelled", error=message, duration_seconds=round(time.perf_counter() - started, 3))
    store.update(active_job_id, status="completed", result=result, progress={"phase": "completed", "percent": 100})
    return JobExecutionResult(active_job_id, "completed", result=result, duration_seconds=round(time.perf_counter() - started, 3))

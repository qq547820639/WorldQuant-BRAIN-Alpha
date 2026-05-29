"""Generic async job services for Web API operations."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol


logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


Worker = Callable[[dict[str, Any]], dict[str, Any]]
ErrorPayload = Callable[..., dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]


def _timing(started_at: float, *, done: int = 0, total: int = 0) -> dict[str, Any]:
    now = time.time()
    elapsed = max(0.0, now - started_at)
    payload: dict[str, Any] = {
        "started_at_ms": int(started_at * 1000),
        "updated_at_ms": int(now * 1000),
        "elapsed_seconds": round(elapsed, 1),
    }
    if total > 0 and done > 0 and done < total and elapsed > 0:
        rate = done / elapsed
        eta = max(1, int(round((total - done) / rate))) if rate > 0 else 0
        payload["eta_seconds"] = eta
        payload["eta_deadline_at_ms"] = int((now + eta) * 1000)
    elif total > 0 and done >= total:
        payload["eta_seconds"] = 0
    return payload


def run_simple_async_job_service(
    job_id: str,
    payload: dict[str, Any],
    *,
    store: JobStoreLike,
    operation: str,
    start_phase: str,
    start_message: str,
    worker: Worker,
    safe_error_message: SafeErrorMessage,
    error_payload: ErrorPayload,
) -> None:
    started_at = time.time()
    store.update(
        job_id,
        status="running",
        progress={
            "task_id": job_id,
            "job_id": job_id,
            "operation": operation,
            "phase": start_phase,
            "status_code": "RUNNING",
            "status_message": start_message,
            "message": start_message,
            **_timing(started_at),
        },
    )
    try:
        result = worker(payload)
        ok = not isinstance(result, dict) or result.get("ok", True) is not False
        status = "completed" if ok else "failed"
        message = _result_message(result, fallback="Task completed." if ok else "Task failed.")
        store.update(
            job_id,
            status=status,
            result=result,
            error="" if ok else message,
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": operation,
                "phase": "completed" if ok else "failed",
                "status_code": "COMPLETED" if ok else "FAILED",
                "percent": 100,
                "percent_complete": 100,
                "status_message": message,
                "message": message,
                **_timing(started_at, done=1, total=1),
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        context = error_payload(exc, error_code=f"{operation.upper()}_JOB_FAILED", job_id=job_id, phase=operation)
        logger.error("%s job failed: %s", operation, context, exc_info=True)
        store.update(
            job_id,
            status="failed",
            error=message,
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": operation,
                "phase": "failed",
                "status_code": "FAILED",
                "percent": 100,
                "percent_complete": 100,
                "status_message": message,
                "message": message,
                "error_context": context,
                **_timing(started_at, done=1, total=1),
            },
        )


def progress_update(
    store: JobStoreLike,
    job_id: str,
    started_at: float,
    *,
    operation: str,
    phase: str,
    message: str,
    done: int = 0,
    total: int = 0,
    percent: float | None = None,
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "task_id": job_id,
        "job_id": job_id,
        "operation": operation,
        "phase": phase,
        "status_code": "RUNNING",
        "status_message": message,
        "message": message,
        "done": done,
        "total": total,
        **extra,
        **_timing(started_at, done=done, total=total),
    }
    if percent is not None:
        bounded_percent = max(0.0, min(100.0, float(percent)))
        payload["percent"] = bounded_percent
        payload["percent_complete"] = bounded_percent
    store.update(job_id, status="running", progress=payload)


def _result_message(result: Any, *, fallback: str) -> str:
    if isinstance(result, dict):
        for key in ("status_message", "message", "error"):
            value = result.get(key)
            if value:
                return str(value)
        summary = result.get("summary")
        if isinstance(summary, dict):
            if "generated_count" in summary:
                return f"Generated {summary.get('generated_count')} candidate(s)."
            if "submitted" in summary:
                return f"Submitted {summary.get('submitted')} alpha(s)."
    return fallback

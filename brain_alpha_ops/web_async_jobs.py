"""Generic async job services for Web API operations."""

from __future__ import annotations

import logging
import inspect
import threading
import time
from typing import Any, Callable, Protocol

from brain_alpha_ops.web_post_handlers import background_job_start_payload


logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


CancelCallback = Callable[[], bool]
Worker = Callable[..., dict[str, Any]]
ErrorPayload = Callable[..., dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]
DEFAULT_ASYNC_HEARTBEAT_SECONDS = 30.0


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
    heartbeat_interval_seconds: float = DEFAULT_ASYNC_HEARTBEAT_SECONDS,
) -> None:
    started_at = time.time()
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
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
    heartbeat_thread = _start_async_heartbeat(
        job_id,
        store=store,
        operation=operation,
        stop_event=heartbeat_stop,
        interval_seconds=heartbeat_interval_seconds,
    )
    try:
        if _store_is_cancelled(store, job_id):
            _mark_stopped(store, job_id, started_at, operation=operation, phase=start_phase, message="Task was cancelled before it started.")
            return
        result = _call_worker(worker, payload, lambda: _store_is_cancelled(store, job_id))
        if _store_is_cancelled(store, job_id):
            _mark_stopped(store, job_id, started_at, operation=operation, phase="stopped", message="Task stopped after cancellation request.")
            return
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
        if _store_is_cancelled(store, job_id):
            _mark_stopped(store, job_id, started_at, operation=operation, phase="stopped", message=message or "Task stopped after cancellation request.")
            return
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
    finally:
        _stop_async_heartbeat(heartbeat_stop, heartbeat_thread)


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


def _start_async_heartbeat(
    job_id: str,
    *,
    store: JobStoreLike,
    operation: str,
    stop_event: threading.Event,
    interval_seconds: float,
) -> threading.Thread | None:
    interval = max(0.0, float(interval_seconds or 0.0))
    if interval <= 0:
        return None

    def _heartbeat_loop() -> None:
        count = 0
        while not stop_event.wait(interval):
            try:
                if _store_is_cancelled(store, job_id):
                    return
                count += 1
                heartbeat_result = _store_heartbeat(
                    store,
                    job_id,
                    operation=operation,
                    heartbeat_count=count,
                )
                if heartbeat_result is True:
                    continue
                if heartbeat_result is False:
                    return
                row = _store_get(store, job_id)
                status = str(row.get("status") or "").strip().lower()
                if status not in {"queued", "running", "stopping"}:
                    return
                progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
                message = str(
                    progress.get("status_message")
                    or progress.get("message")
                    or "Async operation is still running."
                )
                next_progress = dict(progress)
                next_progress.update({
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": operation,
                    "phase": str(progress.get("phase") or operation),
                    "status_code": "RUNNING",
                    "status_message": f"{message} Backend operation is still running.",
                    "message": f"{message} Backend operation is still running.",
                    "heartbeat": {
                        "count": count,
                        "source": "web_async_jobs",
                        "updated_at": time.time(),
                    },
                })
                update: dict[str, Any] = {
                    "status": "stopping" if status == "stopping" else "running",
                    "progress": next_progress,
                }
                progress_updated_at = row.get("updated_at")
                if progress_updated_at not in ("", None):
                    update["updated_at"] = progress_updated_at
                store.update(job_id, **update)
            except Exception:
                logger.warning("%s async heartbeat failed", operation, exc_info=True)
                return

    thread = threading.Thread(target=_heartbeat_loop, name=f"brain-alpha-async-heartbeat-{job_id}", daemon=True)
    thread.start()
    return thread


def _store_heartbeat(
    store: JobStoreLike,
    job_id: str,
    *,
    operation: str,
    heartbeat_count: int,
) -> bool | None:
    heartbeat = getattr(store, "heartbeat", None)
    if not callable(heartbeat):
        return None
    return bool(
        heartbeat(
            job_id,
            operation=operation,
            heartbeat_count=heartbeat_count,
            source="web_async_jobs",
        )
    )


def _call_worker(worker: Worker, payload: dict[str, Any], cancel_callback: CancelCallback) -> dict[str, Any]:
    try:
        signature = inspect.signature(worker)
    except (TypeError, ValueError):
        return worker(payload)
    parameters = signature.parameters
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    if "cancel_callback" in parameters or accepts_kwargs:
        return worker(payload, cancel_callback=cancel_callback)
    if "is_cancelled" in parameters:
        return worker(payload, is_cancelled=cancel_callback)
    return worker(payload)


def _stop_async_heartbeat(stop_event: threading.Event, thread: threading.Thread | None) -> None:
    stop_event.set()
    if thread is not None:
        thread.join(timeout=1.0)


def _store_get(store: JobStoreLike, job_id: str) -> dict[str, Any]:
    getter = getattr(store, "get", None)
    if callable(getter):
        row = getter(job_id)
        return row if isinstance(row, dict) else {}
    rows = getattr(store, "rows", None)
    if isinstance(rows, dict):
        row = rows.get(job_id)
        return row if isinstance(row, dict) else {}
    jobs = getattr(store, "jobs", None)
    if isinstance(jobs, dict):
        row = jobs.get(job_id)
        return row if isinstance(row, dict) else {}
    return {}


def _store_is_cancelled(store: JobStoreLike, job_id: str) -> bool:
    checker = getattr(store, "is_cancelled", None)
    if callable(checker):
        return bool(checker(job_id))
    return bool(_store_get(store, job_id).get("cancel"))


def _mark_stopped(
    store: JobStoreLike,
    job_id: str,
    started_at: float,
    *,
    operation: str,
    phase: str,
    message: str,
) -> None:
    store.update(
        job_id,
        status="stopped",
        error="",
        progress={
            "task_id": job_id,
            "job_id": job_id,
            "operation": operation,
            "phase": phase,
            "status_code": "STOPPED",
            "percent": 100,
            "percent_complete": 100,
            "status_message": message,
            "message": message,
            **_timing(started_at, done=1, total=1),
        },
    )


def _result_message(result: Any, *, fallback: str) -> str:
    if isinstance(result, dict):
        for key in ("status_message", "message", "error"):
            value = result.get(key)
            if value:
                return str(value)
        summary = result.get("summary")
        if isinstance(summary, dict):
            if "generated_count" in summary:
                from brain_alpha_ops.web_candidate_generation_summary import candidate_generation_status_message

                return candidate_generation_status_message(result)
            if "submitted" in summary:
                return f"Submitted {summary.get('submitted')} alpha(s)."
    return fallback

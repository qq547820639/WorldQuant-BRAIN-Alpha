from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_payload_validation import (
    validate_alpha_action_payload,
    validate_job_cancel_payload,
    validate_json_object_payload,
    validate_submit_batch_payload,
    validate_sync_alphas_payload,
)

from ..web_handler_dispatch import (
    _TERMINAL_STATUSES,
    _error_response,
    _job_response,
    _reject_auxiliary_conflict,
    _validated_post_route,
    _with_session_credentials,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (formerly helpers.py)
# ---------------------------------------------------------------------------


def _non_submit_run_payload(
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    safe_payload = dict(payload or {})
    safe_payload["autoSubmit"] = False
    safe_payload["auto_submit"] = False
    return safe_payload


def _create_non_submit_run_job(store: Any) -> str:
    initial = {
        "operation": "production_run",
        "safe_mode": {
            "autoSubmit": False,
            "auto_submit": False,
            "submit_endpoint_required": True,
        },
        "result": {
            "summary": {
                "submitted_this_run": 0,
                "auto_submitted": 0,
            },
        },
        "progress": {
            "phase": "queued",
            "current": 0,
            "total": 1,
            "percent": 0,
            "percent_complete": 0,
            "message": "Non-submit production run queued.",
            "status_message": "\u975e\u63d0\u4ea4\u6d41\u6c34\u7ebf\u5df2\u6392\u961f\u3002",
            "alpha_id": "",
        },
    }
    return store.create(initial)


def _start_sync_job(
    handler: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    active = ctx.sync_jobs.latest_active()
    if active:
        active_job_id, _job = active
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "CONFLICT_RUNNING",
                    "error": "\u5df2\u6709\u4e91\u7aef\u540c\u6b65\u4efb\u52a1\u6b63\u5728\u8fd0\u884c\u3002",
                    "job_id": active_job_id,
                    "task_id": active_job_id,
                    "status_url": f"/api/sync_status?job_id={active_job_id}",
                },
                fallback_kind="queue_blocked",
            ),
            status=409,
        )
        return
    if _reject_auxiliary_conflict(handler, ctx, exclude="sync"):
        return
    payload = _with_session_credentials(handler, ctx, payload)
    response, status = ctx.background_job_start_payload(
        ctx.sync_jobs,
        payload,
        ctx.start_sync_job,
        conflict_error="\u5df2\u6709\u4e91\u7aef\u540c\u6b65\u4efb\u52a1\u8fd0\u884c\u4e2d",
    )
    job_id = str(
        response.get("job_id") or response.get("task_id") or ""
    )
    if job_id:
        response = {
            **response,
            "status_url": f"/api/sync_status?job_id={job_id}",
        }
    if response.get("ok") is False or status >= 400:
        response = _error_response(
            {
                **response,
                "error_code": response.get("error_code")
                or "CONFLICT_RUNNING",
            },
            fallback_kind="queue_blocked",
        )
    handler._json(response, status=status)


def _start_optimize_candidates_job(
    ctx: WebHandlerDispatchContext, job_id: str, payload: dict[str, Any]
) -> None:

    def worker(body: dict[str, Any]) -> dict[str, Any]:
        from brain_alpha_ops.web_candidates.optimization import (
            optimize_candidates_payload,
            persist_optimized_candidates,
        )

        result = optimize_candidates_payload(
            body, run_config_from_payload=ctx.run_config_from_payload
        )
        if not result.get("ok"):
            return result
        run_config = ctx.run_config_from_payload(body)
        persistence = persist_optimized_candidates(
            job_id, run_config, result
        )
        summary = result.setdefault("summary", {})
        if isinstance(summary, dict):
            summary["persistence"] = persistence
        return result

    def run() -> None:
        ctx.run_simple_async_job_service(
            job_id,
            payload,
            store=ctx.async_jobs,
            operation="candidate_optimization",
            start_phase="candidate_optimization",
            start_message="\u6b63\u5728\u8fdb\u884c\u672c\u5730\u5019\u9009\u4f18\u5316\uff0c\u4e0d\u4f1a\u8c03\u7528\u5b98\u65b9\u6a21\u62df\u6216\u63d0\u4ea4\u63a5\u53e3\u3002",
            worker=worker,
            safe_error_message=ctx.safe_error_message,
            error_payload=ctx.error_payload,
        )

    threading.Thread(target=run, daemon=True).start()


def _submit_with_lock(
    handler: Any,
    ctx: WebHandlerDispatchContext,
    submitter: Callable[[dict[str, Any]], dict[str, Any]],
    error_code: str,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    if _reject_auxiliary_conflict(
        handler, ctx, exclude="submit", allow_production=True
    ):
        return
    if not ctx.submit_lock.acquire(blocking=False):
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "CONFLICT_RUNNING",
                    "error": "\u5df2\u6709\u63d0\u4ea4\u4efb\u52a1\u6b63\u5728\u8fd0\u884c\uff0c\u8bf7\u5b8c\u6210\u540e\u518d\u64cd\u4f5c\u3002",
                },
                fallback_kind="queue_blocked",
            ),
            status=409,
        )
        return
    try:
        payload = handler._read_json() if payload is None else payload
        handler._json(submitter(payload))
    except Exception as exc:
        logger.error(
            "web submit route failed: %s", error_code, exc_info=True
        )
        handler._json(
            _error_response(ctx.web_error(exc, error_code)), status=400
        )
    finally:
        ctx.submit_lock.release()


# ---------------------------------------------------------------------------
# Job management routes (formerly job_management.py)
# ---------------------------------------------------------------------------


def _stop_or_cancel_job(
    handler: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    """Shared implementation for /api/stop and /api/cancel.

    Searches all job stores (run, sync, check, async) and stops/cancels
    the matching job. Both endpoints use the same underlying stop mechanism.
    """
    job_id = str((payload or {}).get("job_id") or "")
    # Phase 5 tech-debt cleanup: consume optional cancel telemetry (reason/
    # message/source) sent by the web UI's auto-cancel flow so it is not
    # silently dropped. Does not alter stop/cancel response behavior.
    cancel_reason = str((payload or {}).get("reason") or "").strip()
    if cancel_reason:
        cancel_source = str((payload or {}).get("source") or "").strip()
        cancel_message = str((payload or {}).get("message") or "").strip()
        logger.info(
            "job cancel telemetry: job_id=%s reason=%s source=%s message=%s",
            job_id,
            cancel_reason,
            cancel_source,
            cancel_message[:200],
        )
    for store, job_type in (
        (ctx.jobs, "run"),
        (ctx.sync_jobs, "sync"),
        (ctx.check_jobs, "check"),
        (ctx.async_jobs, "async"),
    ):
        row = store.get(job_id)
        if row is not None:
            status = str(row.get("status", ""))
            if status in _TERMINAL_STATUSES:
                handler._json(
                    _job_response(
                        {
                            "ok": True,
                            "job_id": job_id,
                            "task_id": job_id,
                            "job_type": job_type,
                            "status": status,
                            "already_terminal": True,
                        },
                        job_type=job_type,
                    )
                )
                return
            result = ctx.stop_job_payload(store, payload)
            handler._json(
                _job_response(
                    {
                        **result,
                        "job_id": job_id,
                        "task_id": job_id,
                        "job_type": job_type,
                        "status": "stopping",
                    },
                    job_type=job_type,
                )
            )
            return
    handler._json(
        _error_response(
            {
                "ok": False,
                "error_code": "JOB_NOT_FOUND",
                "error": "\u672a\u627e\u5230\u53ef\u505c\u6b62\u7684\u4efb\u52a1\u3002",
                "job_id": job_id,
            },
            fallback_kind="job_not_found",
        ),
        status=404,
    )


@_validated_post_route(validate_json_object_payload, "RUN_ERROR")
def _post_run(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    safe_payload = _with_session_credentials(
        handler, ctx, _non_submit_run_payload(payload)
    )
    ctx.validate_run_payload(safe_payload)
    active = ctx.jobs.latest_active()
    if active:
        active_job_id, _job = active
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "CONFLICT_RUNNING",
                    "error": "\u5df2\u6709\u751f\u4ea7\u4efb\u52a1\u6b63\u5728\u8fd0\u884c\uff0c\u8bf7\u5148\u505c\u6b62\u5f53\u524d\u4efb\u52a1\u3002",
                    "job_id": active_job_id,
                },
                fallback_kind="queue_blocked",
            ),
            status=409,
        )
        return
    job_id = _create_non_submit_run_job(ctx.jobs)
    ctx.start_run_job(job_id, safe_payload)
    handler._json(
        {
            "ok": True,
            "job_id": job_id,
            "task_id": job_id,
            "auto_submit": False,
            "submitted": False,
            "sse_url": f"/sse?job_id={job_id}",
            "status_url": f"/api/production-validation/status?job_id={job_id}",
        }
    )


@_validated_post_route(validate_job_cancel_payload, "STOP_ERROR")
def _post_stop(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    _stop_or_cancel_job(handler, ctx, payload)


@_validated_post_route(validate_job_cancel_payload, "CANCEL_ERROR")
def _post_cancel(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    _stop_or_cancel_job(handler, ctx, payload)


# ---------------------------------------------------------------------------
# Sync routes (formerly sync.py)
# ---------------------------------------------------------------------------


@_validated_post_route(validate_sync_alphas_payload, "SYNC_ERROR")
def _post_sync_alphas(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    _start_sync_job(handler, ctx, payload)


@_validated_post_route(validate_sync_alphas_payload, "SYNC_CONTEXT_ERROR")
def _post_sync_context_only(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    context_payload = {
        **payload,
        "contextOnly": True,
        "refreshOfficialContext": True,
        "userFacingOperation": "official_operations_context_only_retry",
    }
    _start_sync_job(handler, ctx, context_payload)


@_validated_post_route(validate_job_cancel_payload, "SYNC_CANCEL_ERROR")
def _post_sync_cancel(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    job_id = str((payload or {}).get("job_id") or "")
    row = ctx.sync_jobs.get(job_id)
    if row is not None:
        status = str(row.get("status", ""))
        if status in _TERMINAL_STATUSES:
            handler._json(
                _job_response(
                    {
                        "ok": True,
                        "job_id": job_id,
                        "task_id": job_id,
                        "job_type": "sync",
                        "status": status,
                        "already_terminal": True,
                    },
                    job_type="sync",
                )
            )
            return
    result = ctx.stop_job_payload(ctx.sync_jobs, payload)
    if result.get("ok"):
        stopping_message = "\u4e91\u7aef\u540c\u6b65\u505c\u6b62\u8bf7\u6c42\u5df2\u53d1\u9001\uff0c\u540e\u53f0\u4f1a\u5728\u5f53\u524d\u5b98\u65b9\u63a5\u53e3\u8fd4\u56de\u540e\u7ed3\u675f\u3002"
        stopping_since_ms = int(time.time() * 1000)
        row = (
            ctx.sync_jobs.get(job_id)
            if hasattr(ctx.sync_jobs, "get")
            else None
        )
        progress = (
            dict(row.get("progress") or {})
            if isinstance(row, dict)
            else {}
        )
        progress.update(
            {
                "job_id": job_id,
                "task_id": job_id,
                "phase": "stopping",
                "status_code": "STOPPING",
                "status_message": stopping_message,
                "message": stopping_message,
                "stopping_since_ms": stopping_since_ms,
            }
        )
        updater = getattr(ctx.sync_jobs, "update", None)
        if callable(updater):
            updater(job_id, status="stopping", progress=progress)
        handler._json(
            _job_response(
                {
                    **result,
                    "job_id": job_id,
                    "task_id": job_id,
                    "job_type": "sync",
                    "status": "stopping",
                    "message": stopping_message,
                    "stopping_since_ms": stopping_since_ms,
                },
                job_type="sync",
            )
        )
        return
    handler._json(
        _error_response(
            {
                **result,
                "job_id": job_id,
                "error_code": "SYNC_JOB_NOT_FOUND",
                "error": "\u672a\u627e\u5230\u53ef\u505c\u6b62\u7684\u4e91\u7aef\u540c\u6b65\u4efb\u52a1\u3002",
            },
            fallback_kind="job_not_found",
        ),
        status=404,
    )


# ---------------------------------------------------------------------------
# Submit routes (formerly submit.py)
# ---------------------------------------------------------------------------

# Configurable HTTP status returned when the Web-flow real-submit kill-switch
# is active. Defaults to 403 (Forbidden) per HTTP semantics for policy
# denials; exposed as a module constant so tests or operators can override
# (e.g. 409 Conflict / 423 Locked) without editing the route body.
_SUBMIT_DISABLED_HTTP_STATUS: int = 403


@_validated_post_route(validate_alpha_action_payload, "SUBMIT_ERROR")
def _post_submit(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        _error_response(
            {
                "ok": False,
                "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW",
                "error": "Web \u6d41\u7a0b\u9700\u663e\u5f0f\u5c31\u7eea\u590d\u6838\u540e\u624d\u5141\u8bb8\u771f\u5b9e\u63d0\u4ea4\u3002",
                "submitted": False,
                "state_navigation": {
                    "exit_paths": [
                        {
                            "label": "\u524d\u5f80 BRAIN \u5e73\u53f0\u624b\u52a8\u63d0\u4ea4",
                            "url": "https://platform.worldquantbrain.com/alphas",
                            "type": "external",
                        }
                    ],
                    "all_gates_passed": True,
                },
            }
        ),
        status=_SUBMIT_DISABLED_HTTP_STATUS,
    )


@_validated_post_route(
    validate_submit_batch_payload, "SUBMIT_BATCH_ERROR"
)
def _post_submit_batch(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        _error_response(
            {
                "ok": False,
                "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW",
                "error": "Web \u6d41\u7a0b\u9700\u663e\u5f0f\u5c31\u7eea\u590d\u6838\u540e\u624d\u5141\u8bb8\u771f\u5b9e\u63d0\u4ea4\u3002",
                "submitted": False,
                "state_navigation": {
                    "exit_paths": [
                        {
                            "label": "\u524d\u5f80 BRAIN \u5e73\u53f0\u624b\u52a8\u63d0\u4ea4",
                            "url": "https://platform.worldquantbrain.com/alphas",
                            "type": "external",
                        }
                    ],
                    "all_gates_passed": True,
                },
            }
        ),
        status=_SUBMIT_DISABLED_HTTP_STATUS,
    )

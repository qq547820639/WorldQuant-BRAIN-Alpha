from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_payload_validation import (
    validate_job_cancel_payload,
    validate_json_object_payload,
)

from ..web_handler_dispatch import (
    _TERMINAL_STATUSES,
    _error_response,
    _job_response,
    _reject_auxiliary_conflict,
    _validated_post_route,
    _with_session_credentials,
)

from .helpers import _create_non_submit_run_job, _non_submit_run_payload


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

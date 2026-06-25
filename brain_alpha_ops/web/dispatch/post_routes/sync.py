from __future__ import annotations

import time
from typing import Any

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_payload_validation import (
    validate_job_cancel_payload,
    validate_sync_alphas_payload,
)

from ..web_handler_dispatch import (
    _TERMINAL_STATUSES,
    _error_response,
    _job_response,
    _validated_post_route,
)

from .helpers import _start_sync_job


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

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext

from ..web_handler_dispatch import (
    _error_response,
    _reject_auxiliary_conflict,
    _with_session_credentials,
)

logger = logging.getLogger(__name__)


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

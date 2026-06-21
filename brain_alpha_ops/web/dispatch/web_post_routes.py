"""POST route handlers for the web console.

Contains all ``_post_*`` handler functions (25 routes) plus supporting helpers
(``_start_sync_job``, ``_start_optimize_candidates_job``, ``_submit_with_lock``,
``_non_submit_run_payload``, ``_create_non_submit_run_job``).

These handlers are imported by ``web_handler_dispatch.py`` and registered in
``_POST_DISPATCH_HANDLERS``.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.runtime_constants import HILDefaults as _HILDefaults
from brain_alpha_ops.web_payload_validation import (
    validate_alpha_action_payload,
    validate_assistant_cross_review_payload,
    validate_assistant_guidance_save_payload,
    validate_assistant_text_payload,
    validate_check_batch_payload,
    validate_generate_candidates_payload,
    validate_job_cancel_payload,
    validate_json_object_payload,
    validate_simulation_payload,
    validate_submit_batch_payload,
    validate_sync_alphas_payload,
)
from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext

from .web_handler_dispatch import (
    _TERMINAL_STATUSES,
    _error_response,
    _job_response,
    _reject_auxiliary_conflict,
    _validated_post_route,
    _with_session_credentials,
)

logger = logging.getLogger(__name__)


# ── POST Handler Helpers ──────────────────────────────────────────────────


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


# ── POST Handlers ─────────────────────────────────────────────────────────


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
    # M-SEC-02: latest_active() releases lock before _create_non_submit_run_job().
    # Low risk for single-user local app; lock held per-operation by JobStore internally.
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


@_validated_post_route(validate_json_object_payload, "CONNECTION_ERROR")
def _post_test_connection(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    payload = _with_session_credentials(handler, ctx, payload)
    result = ctx.connection_test_post_payload(
        payload, ctx.test_connection
    )
    session_id = handler._session_id_from_cookie()
    if isinstance(result, dict) and result.get("ok"):
        session = ctx.mark_brain_connection_verified(
            session_id, result, payload
        )
    else:
        session = ctx.clear_brain_connection_verified(session_id)
    response = (
        result
        if isinstance(result, dict)
        else {
            "ok": False,
            "error_code": "CONNECTION_ERROR",
            "error": "\u8fde\u63a5\u6d4b\u8bd5\u5931\u8d25",
        }
    )
    if not response.get("ok"):
        response = _error_response(response)
    handler._json({**response, "session": session})


@_validated_post_route(validate_json_object_payload, "CONFIG_SAVE_ERROR")
def _post_config_save(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(ctx.save_run_config_payload(payload))


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


@_validated_post_route(validate_job_cancel_payload, "STOP_ERROR")
def _post_stop(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    _stop_or_cancel_job(handler, ctx, payload)


# /api/cancel is an alias for /api/stop
@_validated_post_route(validate_job_cancel_payload, "CANCEL_ERROR")
def _post_cancel(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    _stop_or_cancel_job(handler, ctx, payload)


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


@_validated_post_route(validate_alpha_action_payload, "CHECK_ERROR")
def _post_check(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    if _reject_auxiliary_conflict(handler, ctx, allow_production=True):
        return
    payload = _with_session_credentials(handler, ctx, payload)
    handler._json(ctx.check_candidate(payload))


@_validated_post_route(
    validate_generate_candidates_payload,
    "GENERATE_CANDIDATES_ERROR",
    assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR",
)
def _post_generate_candidates(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    response, status = ctx.background_job_start_payload(
        ctx.async_jobs,
        payload,
        ctx.start_generate_candidates_job,
        conflict_error="\u5df2\u6709\u5f02\u6b65\u4efb\u52a1\u8fd0\u884c\u4e2d",
    )
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


@_validated_post_route(
    validate_json_object_payload, "OPTIMIZE_CANDIDATES_ERROR"
)
def _post_optimize_candidates(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    if _reject_auxiliary_conflict(handler, ctx):
        return
    response, status = ctx.background_job_start_payload(
        ctx.async_jobs,
        payload,
        lambda job_id, body: _start_optimize_candidates_job(
            ctx, job_id, body
        ),
        conflict_error="\u5df2\u6709\u5f02\u6b65\u4efb\u52a1\u8fd0\u884c\u4e2d",
    )
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


@_validated_post_route(validate_check_batch_payload, "CHECK_BATCH_ERROR")
def _post_check_batch(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    active = ctx.check_jobs.latest_active()
    if active:
        active_job_id, _job = active
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "CONFLICT_RUNNING",
                    "error": "\u5df2\u6709\u6279\u91cf\u68c0\u67e5\u4efb\u52a1\u6b63\u5728\u8fd0\u884c\u3002",
                    "job_id": active_job_id,
                },
                fallback_kind="queue_blocked",
            ),
            status=409,
        )
        return
    if _reject_auxiliary_conflict(
        handler, ctx, exclude="check", allow_production=True
    ):
        return
    payload = _with_session_credentials(handler, ctx, payload)
    response, status = ctx.background_job_start_payload(
        ctx.check_jobs,
        payload,
        ctx.start_check_batch_job,
        conflict_error="\u5df2\u6709\u6279\u91cf\u68c0\u67e5\u4efb\u52a1\u8fd0\u884c\u4e2d",
    )
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


@_validated_post_route(validate_alpha_action_payload, "SUBMIT_ERROR")
def _post_submit(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    # Web flow unconditionally blocks real BRAIN submits as a safety gate
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
        status=403,
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
    # Web flow unconditionally blocks real BRAIN batch submits as a safety gate
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
        status=403,
    )


@_validated_post_route(
    validate_assistant_text_payload,
    "ASSISTANT_RESPONSE_PARSE_ERROR",
    assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR",
)
def _post_assistant_response_parse(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        ctx.assistant_response_parse_post_payload(
            payload, ctx.assistant_response_parse_payload
        )
    )


@_validated_post_route(
    validate_assistant_text_payload,
    "ASSISTANT_RESPONSE_GUIDANCE_ERROR",
    assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR",
)
def _post_assistant_response_guidance(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        ctx.assistant_response_guidance_post_payload(
            payload, ctx.assistant_response_guidance_payload
        )
    )


@_validated_post_route(
    validate_assistant_cross_review_payload,
    "ASSISTANT_CROSS_REVIEW_ERROR",
    assistant_error_code="ASSISTANT_CROSS_REVIEW_PARSE_ERROR",
)
def _post_assistant_cross_review(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(ctx.assistant_cross_review_payload(payload))


@_validated_post_route(
    validate_assistant_guidance_save_payload,
    "ASSISTANT_GUIDANCE_SAVE_ERROR",
    assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR",
)
def _post_assistant_guidance(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        ctx.save_assistant_guidance_post_payload(
            payload, ctx.save_assistant_guidance_payload
        )
    )


def _post_session(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    """Create a new web session and return a usable CSRF token."""
    if ctx.remote_admin_required() and not ctx.has_valid_admin_token(
        getattr(handler, "headers", {})
    ):
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "ADMIN_AUTH_REQUIRED",
                    "error": "\u8fdc\u7a0b Web \u8bbf\u95ee\u9700\u8981\u7ba1\u7406\u5458\u8ba4\u8bc1",
                }
            ),
            status=401,
        )
        return
    session_id, csrf_token = ctx.get_or_create_session(
        handler._session_id_from_cookie()
    )
    stream_token = ctx.stream_token_for_session(session_id)
    session = ctx.session_status(session_id)
    ttl = int(session.get("ttl_seconds") or 43200)
    handler._json(
        {
            "ok": True,
            "session_id": session_id[:8],
            "csrf_token": csrf_token,
            "stream_token": stream_token,
            "ttl_seconds": ttl,
            "connected": bool(session.get("connected")),
            "brain_connection_verified": bool(
                session.get("brain_connection_verified")
            ),
            "session": session,
        },
        extra_headers=[
            ("Set-Cookie", ctx.session_cookie_header(session_id))
        ],
    )


def _post_logout(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    response, headers = ctx.session_end_payload(
        handler._session_id_from_cookie(),
        ctx.expire_session,
        ctx.expired_session_cookie_header,
    )
    handler._json(response, extra_headers=headers)


def _post_shutdown(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    _post_logout(handler, parsed, ctx)
    ctx.start_shutdown()


@_validated_post_route(validate_alpha_action_payload, "SCORING_ERROR")
def _post_scoring_evaluate(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    response, status = ctx.background_job_start_payload(
        ctx.async_jobs,
        payload,
        ctx.start_scoring_evaluate_job,
        conflict_error="\u5df2\u6709\u5f02\u6b65\u4efb\u52a1\u8fd0\u884c\u4e2d",
    )
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


@_validated_post_route(validate_alpha_action_payload, "SCORING_ERROR")
def _post_scoring_attribution(
    handler: Any,
    _parsed: Any,
    _ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    from brain_alpha_ops.web_redline_scoring import (
        handle_scoring_attribution,
    )

    handler._json(handle_scoring_attribution(payload))


def _post_trends(
    handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    """POST /api/trends — \u8ffd\u52a0\u4e00\u6761\u8d8b\u52bf\u8bb0\u5f55\u3002

    \u8bf7\u6c42\u4f53\u5e94\u5305\u542b ``candidates`` (int)\u3001``submissions`` (int) \u548c\u53ef\u9009\u7684 ``cycles`` (int)\u3002
    """
    from brain_alpha_ops.web.api.trends import (
        record_trend as _record_trend_to_store,
    )

    payload = handler._read_json()
    if not isinstance(payload, dict):
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "VALIDATION_ERROR",
                    "error": "\u8bf7\u6c42\u4f53\u5fc5\u987b\u662f JSON \u5bf9\u8c61",
                }
            ),
            status=400,
        )
        return
    candidates = int(payload.get("candidates", 0))
    submissions = int(payload.get("submissions", 0))
    cycles = int(payload.get("cycles", 0))
    _record_trend_to_store(
        candidates=candidates,
        submissions=submissions,
        completed_cycles=cycles,
    )
    handler._json({"ok": True})


@_validated_post_route(validate_simulation_payload, "SIMULATE_ERROR")
def _post_candidates_simulate(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    """Start BRAIN simulation for eligible candidates."""
    from brain_alpha_ops.web_candidates.simulation import (
        simulate_candidates_job,
        simulation_candidates_payload,
    )

    if payload.get("preview"):
        try:
            handler._json(simulation_candidates_payload(payload))
        except Exception as exc:
            logger.exception("simulation preview failed")
            handler._json(
                _error_response(
                    {
                        "ok": False,
                        "error_code": "SIMULATION_PREVIEW_ERROR",
                        "error": redact_error_message(exc),
                    }
                ),
                status=500,
            )
        return

    if _reject_auxiliary_conflict(handler, ctx):
        return

    # P0-2 fix (2026-06-13): require an explicit confirm_simulation=True
    # in the request body before we actually start a BRAIN simulation job.
    # This protects against accidental clicks / stale browser tabs / scripted
    # callers that previously had one-click remote-effects paths. Tests can
    # bypass the gate by setting HILDefaults.SIMULATION_CONFIRM_REQUIRED=False.
    if _HILDefaults.SIMULATION_CONFIRM_REQUIRED and not bool(
        payload.get(_HILDefaults.SIMULATION_CONFIRM_FIELD)
    ):
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": _HILDefaults.SIMULATION_CONFIRM_ERROR_CODE,
                    "error": _HILDefaults.SIMULATION_CONFIRM_HINT,
                    "required_field": _HILDefaults.SIMULATION_CONFIRM_FIELD,
                    "preview_available": True,
                },
                fallback_kind="queue_blocked",
            ),
            status=409,
        )
        return

    # P0-2 follow-up (2026-06-13): strip the confirm_simulation field
    # from the payload before forwarding it to the simulation worker.
    # Without this, downstream consumers (and the integration tests
    # below) would see the gate flag mixed in with the simulation
    # arguments.  We use ``.pop`` to mutate the dict in place so any
    # subsequent ``payload`` reads also see the cleaned shape.
    payload.pop(_HILDefaults.SIMULATION_CONFIRM_FIELD, None)
    payload = _with_session_credentials(handler, ctx, payload)
    store = ctx.async_jobs
    start_message = "\u6b63\u5728\u542f\u52a8\u5b98\u65b9 BRAIN \u6a21\u62df\u4efb\u52a1\u3002"
    initial_job = {
        "status": "running",
        "progress": {
            "phase": "simulation_starting",
            "message": start_message,
            "status_message": start_message,
            "percent": 0,
            "percent_complete": 0,
        },
    }

    if hasattr(store, "create_if_no_active"):
        job_id, active_async = store.create_if_no_active(initial_job)
    else:
        active_async = store.latest_active()
        job_id = ""

    if active_async:
        active_job_id, active_job = active_async
        phase = (
            (active_job.get("progress") or {}).get("phase")
            or active_job.get("phase")
            or "async"
        )
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error": "\u5df2\u6709\u540e\u53f0\u4efb\u52a1\u6b63\u5728\u8fd0\u884c\uff0c\u8bf7\u5b8c\u6210\u6216\u505c\u6b62\u540e\u518d\u542f\u52a8\u5b98\u65b9\u5019\u9009\u6a21\u62df\u3002",
                    "error_code": "CONFLICT_RUNNING",
                    "job_id": active_job_id,
                    "phase": phase,
                },
                fallback_kind="queue_blocked",
            ),
            status=409,
        )
        return

    if not job_id:
        for jid, job in list(store.jobs.items()):
            if (
                str(job.get("status") or "").lower()
                in {"queued", "running", "stopping"}
            ):
                phase = (job.get("progress") or {}).get("phase", "")
                operation = (
                    str(job.get("operation") or "").lower()
                )
                # P2-24 fix: use the explicit operation field instead of
                # substring-matching on the phase string ("simulat") which
                # would miss abbreviated / renamed phases.
                if "simulat" in operation or "simulat" in str(
                    phase
                ).lower():
                    handler._json(
                        _error_response(
                            {
                                "ok": False,
                                "error": "\u5df2\u6709\u6a21\u62df\u4efb\u52a1\u5728\u8fd0\u884c",
                                "error_code": "CONFLICT_RUNNING",
                                "job_id": jid,
                                "phase": phase,
                            },
                            fallback_kind="queue_blocked",
                        ),
                        status=409,
                    )
                    return

    if not job_id:
        job_id = store.create(initial_job)

    def run_sim() -> None:
        from brain_alpha_ops.web_simulation_job import (
            create_sim_job_store,
        )

        simulate_candidates_job(
            job_id,
            payload,
            job_store=create_sim_job_store(store),
            log=logger,
        )

    threading.Thread(target=run_sim, daemon=True).start()
    handler._json(
        {
            "ok": True,
            "job_id": job_id,
            "task_id": job_id,
            "sse_url": f"/sse?job_id={job_id}",
            "status_url": f"/api/status?job_id={job_id}",
        }
    )


__all__: list[str] = []  # handlers are private (_-prefixed)

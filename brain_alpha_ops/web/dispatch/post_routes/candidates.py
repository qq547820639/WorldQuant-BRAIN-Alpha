from __future__ import annotations

import logging
import threading
from typing import Any

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.runtime_constants import HILDefaults as _HILDefaults
from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_payload_validation import (
    validate_alpha_action_payload,
    validate_check_batch_payload,
    validate_generate_candidates_payload,
    validate_json_object_payload,
    validate_simulation_payload,
)

from ..web_handler_dispatch import (
    _error_response,
    _reject_auxiliary_conflict,
    _validated_post_route,
    _with_session_credentials,
)

from .helpers import _start_optimize_candidates_job

logger = logging.getLogger(__name__)


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

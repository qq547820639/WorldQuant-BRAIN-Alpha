"""Simulation-related GET route handlers.

Handlers for job status, sync/check job status, check results, simulation
candidate eligibility, and phase state.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

from brain_alpha_ops.web_candidates.payloads import (
    compact_job_result as _compact_job_result,
)
from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_sync_status_payload import (
    with_official_context_cache as _with_official_context_cache,
)
from brain_alpha_ops.web_sync_status_payload import (
    with_sync_history as _with_sync_history,
)
from ..web_handler_dispatch import (
    _error_response,
    _job_response,
)
from ._helpers import (
    _active_job_from_any_store,
    _job_status_from_any_store,
)

logger = logging.getLogger("brain_alpha_ops.web.dispatch.web_get_routes")


def _get_status(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    if not job_id:
        handler._json(_active_job_from_any_store(ctx))
        return
    payload, status = _job_status_from_any_store(ctx, job_id)
    handler._json(payload, status=status)


def _get_active_job(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(_active_job_from_any_store(ctx))


def _get_stream(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    handler._handle_sse_stream(parsed.query)


def _get_sync_status(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    job_id = (query.get("job_id") or [""])[0]
    if job_id:
        payload, status = ctx.job_status_payload(
            ctx.sync_jobs,
            job_id,
            ctx.enrich_progress,
            error="\u672a\u77e5\u540c\u6b65\u4efb\u52a1",
        )
    else:
        payload, status = (
            ctx.active_job_payload(ctx.sync_jobs, ctx.enrich_progress),
            200,
        )
    if payload.get("ok") is False or status >= 400:
        payload = _error_response(
            {
                **payload,
                "error_code": payload.get("error_code")
                or "JOB_NOT_FOUND",
            },
            fallback_kind="job_not_found",
        )
    else:
        payload = _job_response(
            {**payload, "job_type": "sync"}, job_type="sync"
        )
    payload = _with_official_context_cache(payload, ctx)
    history_limit = ctx.bounded_query_int(
        (query.get("history_limit") or ["5"])[0], 0, 20
    )
    payload = _with_sync_history(payload, ctx, limit=history_limit)
    if ctx.payload_truthy(
        (query.get("compact") or ["false"])[0]
    ):
        payload = _compact_job_result(payload)
    handler._json(payload, status=status)


def _get_check_status(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    payload, status = ctx.job_status_payload(
        ctx.check_jobs,
        job_id,
        ctx.enrich_progress,
        error="\u672a\u77e5\u68c0\u67e5\u4efb\u52a1",
    )
    if payload.get("ok") is False or status >= 400:
        payload = _error_response(
            {
                **payload,
                "error_code": payload.get("error_code")
                or "JOB_NOT_FOUND",
            },
            fallback_kind="job_not_found",
        )
    else:
        payload = _job_response(
            {**payload, "job_type": "check"}, job_type="check"
        )
    handler._json(payload, status=status)


def _get_check_results(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json({"ok": True, **ctx.load_check_results()})


def _get_candidates_simulate_eligible(
    handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    """Return eligible candidates for BRAIN simulation."""
    from brain_alpha_ops.redaction import redact_error_message
    from brain_alpha_ops.web_candidates.simulation import (
        simulation_candidates_payload,
    )

    try:
        # Use parse_qs to get {key: [val]} then flatten single-element lists.
        _parsed_qs = parse_qs(_parsed.query)
        _flat = {
            k: (v[0] if isinstance(v, list) and len(v) == 1 else v)
            for k, v in _parsed_qs.items()
        }
        handler._json(simulation_candidates_payload(_flat))
    except Exception as exc:
        logger.exception("simulation_candidates_payload failed")
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


def _get_phase_state(
    handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    """Return phase navigation state for the frontend PhaseShell component."""
    from brain_alpha_ops.web.handlers.phase import phase_state_payload
    from brain_alpha_ops.web_handler_candidate_routes import (
        candidate_ledger_summary,
    )

    candidate_summary_probe = (
        getattr(_ctx, "candidate_summary_probe", None)
        or candidate_ledger_summary
    )
    try:
        handler._json(
            phase_state_payload(
                sync_jobs=_ctx.sync_jobs
                if hasattr(_ctx, "sync_jobs")
                else None,
                candidate_repo=getattr(_ctx, "candidate_repo", None),
                connection_tracker=getattr(
                    _ctx, "connection_tracker", None
                ),
                readiness_service=getattr(
                    _ctx, "readiness_service", None
                ),
                session_status=_ctx.session_status(
                    handler._session_id_from_cookie()
                ),
                cloud_alpha_snapshot=getattr(
                    _ctx, "cloud_alpha_snapshot", None
                ),
                cloud_alpha_cache_probe=getattr(
                    _ctx, "cloud_alpha_cache_probe", None
                ),
                official_context_file_counts=getattr(
                    _ctx, "official_context_file_counts", None
                ),
                candidate_summary_probe=candidate_summary_probe,
            )
        )
    except Exception:
        logger.warning(
            "phase_state_payload failed \u2014 returning safe default",
            exc_info=True,
        )
        handler._json(
            {
                "ok": True,
                "current_phase": "connect",
                "operation_mode": "needs_setup",
                "connected": False,
                "context_fresh": False,
                "candidates_count": 0,
                "scored_count": 0,
                "readiness_passed": False,
            }
        )


def _get_trends(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    """GET /api/trends — \u8fd4\u56de\u6700\u8fd1 N \u5929\u7684\u8d8b\u52bf\u6570\u636e\u3002"""
    from brain_alpha_ops.web.api.trends import (
        get_trends as _get_trends_from_store,
    )

    query = parse_qs(parsed.query)
    days_str = (query.get("days") or ["30"])[0]
    try:
        days = max(1, min(int(days_str), 365))
    except (ValueError, TypeError):
        days = 30
    handler._json(
        {"ok": True, "data": _get_trends_from_store(days=days)}
    )

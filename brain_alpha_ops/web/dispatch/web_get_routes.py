"""GET route handlers for the web console.

Contains all ``_get_*`` handler functions (36 routes) plus supporting helpers.
These handlers are imported by ``web_handler_dispatch.py`` and registered in
``_GET_DISPATCH_HANDLERS``.
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

from .web_handler_dispatch import (
    DEFAULT_ALPHA_LIFECYCLE_LIMIT,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_LEDGER_LIMIT,
    MAX_ALPHA_LIFECYCLE_LIMIT,
    MAX_HISTORY_LIMIT,
    MAX_LEDGER_LIMIT,
    MAX_RECORD_LOOKUP_LIMIT,
    _error_response,
    _job_response,
)

logger = logging.getLogger(__name__)


# ── Shared helpers ───────────────────────────────────────────────────────

def _positive_query_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, parsed)


def _active_job_from_any_store(
    ctx: WebHandlerDispatchContext,
) -> dict[str, Any]:
    for store, job_type in (
        (ctx.jobs, "run"),
        (ctx.sync_jobs, "sync"),
        (ctx.check_jobs, "check"),
        (ctx.async_jobs, "async"),
    ):
        payload = ctx.active_job_payload(store, ctx.enrich_progress)
        if payload.get("job_id"):
            return _job_response(
                {**payload, "job_type": job_type}, job_type=job_type
            )
    return _job_response(
        ctx.active_job_payload(ctx.jobs, ctx.enrich_progress)
    )


def _job_status_from_any_store(
    ctx: WebHandlerDispatchContext, job_id: str
) -> tuple[dict[str, Any], int]:
    for store, job_type, error in (
        (ctx.jobs, "run", "\u672a\u77e5\u4efb\u52a1"),
        (ctx.sync_jobs, "sync", "\u672a\u77e5\u540c\u6b65\u4efb\u52a1"),
        (ctx.check_jobs, "check", "\u672a\u77e5\u68c0\u67e5\u4efb\u52a1"),
        (ctx.async_jobs, "async", "\u672a\u77e5\u5f02\u6b65\u4efb\u52a1"),
    ):
        payload, status = ctx.job_status_payload(
            store, job_id, ctx.enrich_progress, error=error
        )
        if status == 200:
            return (
                _job_response(
                    {**payload, "job_type": job_type}, job_type=job_type
                ),
                status,
            )
    return (
        _error_response(
            {
                "ok": False,
                "error_code": "JOB_NOT_FOUND",
                "error": "\u672a\u627e\u5230",
            },
            fallback_kind="job_not_found",
        ),
        404,
    )


# ── GET Handlers ─────────────────────────────────────────────────────────


def _get_root(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
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
    handler._html(
        ctx.render_html(csrf_token, stream_token),
        extra_headers=[
            ("Set-Cookie", ctx.session_cookie_header(session_id))
        ],
    )


def _get_status(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    if not job_id:
        handler._json(_active_job_from_any_store(ctx))
        return
    payload, status = _job_status_from_any_store(ctx, job_id)
    handler._json(payload, status=status)


def _get_config(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    # P3-3: include is_default flag so the frontend can distinguish a
    # user-saved run_config.json from the application defaults.
    from brain_alpha_ops.config._loader import (
        default_run_config_path as _default_run_config_path,
    )

    config_path = _default_run_config_path()
    is_default = not config_path.is_file()
    handler._json(
        {
            "ok": True,
            "config": ctx.public_run_config(),
            "is_default": is_default,
        }
    )


def _get_config_schema(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json({"ok": True, "schema": ctx.public_config_schema()})


def _get_capabilities(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_capability_registry import (
        build_capability_registry,
    )

    handler._json(
        build_capability_registry(
            public_config_schema=ctx.public_config_schema,
            official_context_file_counts=ctx.official_context_file_counts,
        )
    )


def _get_active_job(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(_active_job_from_any_store(ctx))


def _get_latest_result(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(ctx.latest_result_snapshot())


def _get_health(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(ctx.health_payload())


def _get_stream(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    handler._handle_sse_stream(parsed.query)


def _get_lifecycle(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    handler._json(
        ctx.lifecycle_payload(ctx.jobs, job_id, ctx.lifecycle_from_job)
    )


def _get_alpha_lifecycle(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_ALPHA_LIFECYCLE_LIMIT)])[0],
        1,
        MAX_ALPHA_LIFECYCLE_LIMIT,
    )
    handler._json(
        ctx.alpha_lifecycle_history(
            alpha_id=(query.get("alpha_id") or [""])[0],
            query=(query.get("query") or [""])[0],
            stage=(query.get("stage") or [""])[0],
            status=(query.get("status") or [""])[0],
            status_category_filter=(query.get("status_category") or [""])[0],
            limit=limit,
        )
    )


def _get_cloud_alphas(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = _positive_query_int((query.get("limit") or [None])[0])
    handler._json({"ok": True, **ctx.cloud_alpha_snapshot(limit=limit)})


def _get_research_memory(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0],
        1,
        MAX_HISTORY_LIMIT,
    )
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 50
    )
    handler._json(
        ctx.research_memory_snapshot(limit=limit, top_n=top_n)
    )


def _get_research_knowledge(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0],
        1,
        MAX_LEDGER_LIMIT,
    )
    min_confidence = ctx.bounded_query_float(
        (query.get("min_confidence") or ["0.0"])[0], 0.0, 1.0
    )
    handler._json(
        ctx.research_knowledge_snapshot(
            limit=limit, min_confidence=min_confidence
        )
    )


def _get_research_observability(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0],
        1,
        MAX_HISTORY_LIMIT,
    )
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 50
    )
    include_cloud = ctx.payload_truthy(
        (query.get("include_cloud") or ["true"])[0]
    )
    handler._json(
        ctx.research_observability_snapshot(
            limit=limit, top_n=top_n, include_cloud=include_cloud
        )
    )


def _get_prompt_runs(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0],
        1,
        MAX_LEDGER_LIMIT,
    )
    handler._json(ctx.prompt_run_ledger_snapshot(limit=limit))


def _get_sqlite_indexes(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 100
    )
    handler._json(ctx.sqlite_index_snapshot(top_n=top_n))


def _get_sqlite_expression_lookup(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    expression = (query.get("expression") or [""])[0]
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 100
    )
    min_similarity = ctx.bounded_query_float(
        (query.get("min_similarity") or ["0.75"])[0], 0.0, 1.0
    )
    max_scan_rows = ctx.bounded_query_int(
        (query.get("max_scan_rows") or ["2000"])[0], 1, 10000
    )
    handler._json(
        ctx.sqlite_expression_lookup_payload(
            expression=expression,
            top_n=top_n,
            min_similarity=min_similarity,
            max_scan_rows=max_scan_rows,
        )
    )


def _get_sqlite_record_lookup(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    alpha_id = (query.get("alpha_id") or [""])[0]
    limit = ctx.bounded_query_int(
        (query.get("limit") or ["50"])[0], 1, MAX_RECORD_LOOKUP_LIMIT
    )
    handler._json(
        ctx.sqlite_record_lookup_payload(alpha_id=alpha_id, limit=limit)
    )


def _get_assistant_context(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0],
        1,
        MAX_HISTORY_LIMIT,
    )
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 50
    )
    include_prompt = ctx.payload_truthy(
        (query.get("include_prompt") or ["true"])[0]
    )
    include_sensitive = ctx.payload_truthy(
        (query.get("include_sensitive") or ["false"])[0]
    )
    handler._json(
        ctx.assistant_context_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
        )
    )


def _get_assistant_guidance(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0],
        1,
        MAX_LEDGER_LIMIT,
    )
    raw_min_confidence = (query.get("min_confidence") or [None])[0]
    min_confidence: float | None = (
        None
        if raw_min_confidence in (None, "")
        else ctx.bounded_query_float(raw_min_confidence, 0.0, 1.0)
    )
    handler._json(
        ctx.assistant_guidance_snapshot(
            limit=limit, min_confidence=min_confidence
        )
    )


def _get_assistant_request(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0],
        1,
        MAX_HISTORY_LIMIT,
    )
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 50
    )
    include_prompt = ctx.payload_truthy(
        (query.get("include_prompt") or ["true"])[0]
    )
    include_draft = ctx.payload_truthy(
        (query.get("include_draft") or ["true"])[0]
    )
    include_sensitive = ctx.payload_truthy(
        (query.get("include_sensitive") or ["false"])[0]
    )
    handler._json(
        ctx.assistant_request_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_offline_draft=include_draft,
            include_sensitive=include_sensitive,
        )
    )


def _get_anti_overfit(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    candidate_id = (
        parse_qs(parsed.query).get("candidate_id") or [""]
    )[0]
    handler._json(
        ctx.anti_overfit_snapshot(candidate_id=candidate_id)
    )


def _get_rolling_validation(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    candidate_id = (query.get("candidate_id") or [""])[0]
    windows = ctx.bounded_query_int(
        (query.get("windows") or ["4"])[0], 2, 50
    )
    handler._json(
        ctx.rolling_validation_snapshot(
            candidate_id=candidate_id, windows=windows
        )
    )


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


def _get_profile(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(ctx.profile_payload(ctx.user_profile_snapshot))


def _get_presets(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(ctx.presets_payload(ctx.load_presets))


def _get_redline_report(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_redline_scoring import (
        handle_redline_report,
    )

    handler._json(handle_redline_report(parse_qs(parsed.query)))


def _get_scoring_health(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_redline_scoring import (
        handle_scoring_health,
    )

    handler._json(handle_scoring_health(parse_qs(parsed.query)))


def _get_checkpoint_status(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_redline_scoring import (
        handle_checkpoint_status,
    )

    handler._json(handle_checkpoint_status(parse_qs(parsed.query)))


def _get_backtest_slots(
    handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_routes import _backtest_slots_payload

    handler._json(_backtest_slots_payload())


def _get_submit_readiness(
    handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_routes import _submit_readiness_payload

    handler._json(_submit_readiness_payload())


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


__all__: list[str] = []  # handlers are private (_-prefixed)

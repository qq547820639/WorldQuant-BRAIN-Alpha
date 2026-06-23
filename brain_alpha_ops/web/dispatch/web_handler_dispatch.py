"""GET/POST route dispatch for the local web console handler.

P2-12 (2026-06-13): this module is a façade.  All ``_get_*`` handler bodies
live in ``web_get_routes.py`` and all ``_post_*`` handler bodies live in
``web_post_routes.py``.  This file retains the dispatch tables, utility
functions, and the public ``dispatch_get`` / ``dispatch_post`` entry points.
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable

from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.research.assistant import AssistantResponseParseError
from brain_alpha_ops.web_dispatch_context import (
    WebHandlerDispatchContext,
)
from brain_alpha_ops.web_handler_candidate_routes import (
    get_candidates as _get_candidates,
)
from brain_alpha_ops.web_handler_dispatch_core import (
    dispatch_route as _dispatch_route,
)
from brain_alpha_ops.web_state_contract import enrich_error_payload, enrich_job_response

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_LIMIT = 5000
MAX_HISTORY_LIMIT = 10000
DEFAULT_LEDGER_LIMIT = 100
MAX_LEDGER_LIMIT = 5000
MAX_RECORD_LOOKUP_LIMIT = 500
DEFAULT_ALPHA_LIFECYCLE_LIMIT = 250
MAX_ALPHA_LIFECYCLE_LIMIT = 2000
_TERMINAL_STATUSES = frozenset({
    "completed", "completed_with_warnings", "failed", "stopped", "cancelled", "canceled",
})
_LEGACY_FALLBACK_DISABLED_POST_PATHS = frozenset({"/api/pipeline/start"})
RouteDispatcher = Callable[[Any, Any, WebHandlerDispatchContext], None]
PayloadValidator = Callable[[Any], str]
PayloadRouteDispatcher = Callable[[Any, Any, WebHandlerDispatchContext, dict[str, Any]], None]

# ── Utility Functions ──────────────────────────────────────────────────

def _error_response(payload: dict[str, Any], *, fallback_kind: str | None = None) -> dict[str, Any]:
    # P0-1: ensure error_code is always present in the response so the
    # frontend can show a translated message and actionable suggestion.
    if "error_code" not in payload:
        payload["error_code"] = fallback_kind or "UNKNOWN_ERROR"
    return enrich_error_payload(payload, fallback_kind=fallback_kind)

def _job_response(payload: dict[str, Any], *, job_type: str | None = None) -> dict[str, Any]:
    return enrich_job_response(payload, job_type=job_type)

def dispatch_get(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    _dispatch_route("GET", handler, parsed, ctx, _GET_DISPATCH_HANDLERS)

def dispatch_post(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    _dispatch_route("POST", handler, parsed, ctx, _POST_DISPATCH_HANDLERS)

def _reject_invalid_payload(handler: Any, error: str) -> bool:
    if error:
        handler._json(_error_response({"ok": False, "error_code": "VALIDATION_ERROR", "error": error}), status=400)
    return bool(error)

def _read_validated_payload(handler: Any, validator: PayloadValidator) -> dict[str, Any] | None:
    payload = handler._read_json()
    if _reject_invalid_payload(handler, validator(payload)):
        return None
    return payload

def _validated_post_route(
    validator: PayloadValidator,
    error_code: str,
    *,
    assistant_error_code: str | None = None,
) -> Callable[[PayloadRouteDispatcher], RouteDispatcher]:
    def _decorate(route_handler: PayloadRouteDispatcher) -> RouteDispatcher:
        @wraps(route_handler)
        def _wrapper(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
            try:
                payload = _read_validated_payload(handler, validator)
                if payload is None:
                    return
                route_handler(handler, parsed, ctx, payload)
            except AssistantResponseParseError as exc:
                logger.error("web post route failed: %s", redact_text(parsed.path), exc_info=True)
                handler._json(_error_response(ctx.web_error(exc, assistant_error_code or error_code)), status=400)
            except Exception as exc:
                logger.error("web post route failed: %s", redact_text(parsed.path), exc_info=True)
                handler._json(_error_response(ctx.web_error(exc, error_code)), status=400)

        return _wrapper

    return _decorate

def _reject_auxiliary_conflict(handler: Any, ctx: WebHandlerDispatchContext, **kwargs: Any) -> bool:
    conflict = ctx.active_auxiliary_operation(**kwargs)
    if not conflict:
        return False
    _kind, message = conflict
    handler._json(_error_response({"ok": False, "error_code": "CONFLICT_AUX_OP", "error": message}, fallback_kind="queue_blocked"), status=409)
    return True

def _with_session_credentials(handler: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> dict[str, Any]:
    return ctx.payload_with_brain_session_credentials(handler._session_id_from_cookie(), payload)


# ── Import handlers from sub-modules ───────────────────────────────────

from .web_get_routes import (
    _get_active_job,
    _get_alpha_lifecycle,
    _get_anti_overfit,
    _get_assistant_context,
    _get_assistant_guidance,
    _get_assistant_request,
    _get_backtest_slots,
    _get_candidates_simulate_eligible,
    _get_capabilities,
    _get_check_results,
    _get_check_status,
    _get_checkpoint_status,
    _get_cloud_alphas,
    _get_config,
    _get_config_schema,
    _get_health,
    _get_latest_result,
    _get_lifecycle,
    _get_phase_state,
    _get_presets,
    _get_profile,
    _get_prompt_runs,
    _get_redline_report,
    _get_research_knowledge,
    _get_research_memory,
    _get_research_observability,
    _get_rolling_validation,
    _get_root,
    _get_scoring_health,
    _get_sqlite_expression_lookup,
    _get_sqlite_indexes,
    _get_sqlite_record_lookup,
    _get_status,
    _get_stream,
    _get_submit_readiness,
    _get_sync_status,
    _get_trends,
)

from .web_post_routes import (
    _post_assistant_cross_review,
    _post_assistant_guidance,
    _post_assistant_response_guidance,
    _post_assistant_response_parse,
    _post_cancel,
    _post_candidates_simulate,
    _post_check,
    _post_check_batch,
    _post_config_save,
    _post_generate_candidates,
    _post_logout,
    _post_optimize_candidates,
    _post_run,
    _post_scoring_attribution,
    _post_scoring_evaluate,
    _post_session,
    _post_shutdown,
    _post_stop,
    _post_submit,
    _post_submit_batch,
    _post_sync_alphas,
    _post_sync_cancel,
    _post_sync_context_only,
    _post_test_connection,
    _post_trends,
)

# ── Dispatch Tables ────────────────────────────────────────────────────

_GET_DISPATCH_HANDLERS: dict[str, RouteDispatcher] = {
    "root": _get_root,
    "status": _get_status,
    "config": _get_config,
    "config_schema": _get_config_schema,
    "capabilities": _get_capabilities,
    "active_job": _get_active_job,
    "latest_result": _get_latest_result,
    "health": _get_health,
    "stream": _get_stream,
    "lifecycle": _get_lifecycle,
    "alpha_lifecycle": _get_alpha_lifecycle,
    "candidates": _get_candidates,
    "cloud_alphas": _get_cloud_alphas,
    "research_memory": _get_research_memory,
    "research_knowledge": _get_research_knowledge,
    "research_observability": _get_research_observability,
    "prompt_runs": _get_prompt_runs,
    "sqlite_indexes": _get_sqlite_indexes,
    "sqlite_expression_lookup": _get_sqlite_expression_lookup,
    "sqlite_record_lookup": _get_sqlite_record_lookup,
    "assistant_context": _get_assistant_context,
    "assistant_guidance": _get_assistant_guidance,
    "assistant_request": _get_assistant_request,
    "anti_overfit": _get_anti_overfit,
    "rolling_validation": _get_rolling_validation,
    "sync_status": _get_sync_status,
    "check_status": _get_check_status,
    "check_results": _get_check_results,
    "profile": _get_profile,
    "presets": _get_presets,
    "redline_report": _get_redline_report,
    "scoring_health": _get_scoring_health,
    "checkpoint_status": _get_checkpoint_status,
    "backtest_slots": _get_backtest_slots,
    "submit_readiness": _get_submit_readiness,
    "trends": _get_trends,
    "candidates_simulate_eligible": _get_candidates_simulate_eligible,
    "phase_state": _get_phase_state,
    # Route aliases for backward compatibility
    "snapshot_cloud": _get_cloud_alphas,
    "snapshot_memory": _get_research_memory,
    "snapshot_observability": _get_research_observability,
    "snapshot_assistant_context": _get_assistant_context,
    "snapshot_assistant_guidance": _get_assistant_guidance,
    "snapshot_assistant_requests": _get_assistant_request,
    "snapshot_anti_overfit": _get_anti_overfit,
    "snapshot_rolling_validation": _get_rolling_validation,
    "snapshot_sqlite_indexes": _get_sqlite_indexes,
    "production_validation_status": _get_status,
}

_POST_DISPATCH_HANDLERS: dict[str, RouteDispatcher] = {
    "run": _post_run,
    "config": _post_config_save,
    "test_connection": _post_test_connection,
    "stop": _post_stop,
    "cancel": _post_cancel,
    "sync_alphas": _post_sync_alphas,
    "sync_context_only": _post_sync_context_only,
    "sync_cancel": _post_sync_cancel,
    "check": _post_check,
    "generate_candidates": _post_generate_candidates,
    "optimize_candidates": _post_optimize_candidates,
    "check_batch": _post_check_batch,
    "submit": _post_submit,
    "submit_batch": _post_submit_batch,
    "session": _post_session,
    "logout": _post_logout,
    "shutdown": _post_shutdown,
    "assistant_cross_review": _post_assistant_cross_review,
    "scoring_evaluate": _post_scoring_evaluate,
    "assistant_response_parse": _post_assistant_response_parse,
    "assistant_response_guidance": _post_assistant_response_guidance,
    "assistant_guidance": _post_assistant_guidance,
    "scoring_attribution": _post_scoring_attribution,
    "candidates_simulate": _post_candidates_simulate,
    "trends": _post_trends,
    # Route aliases for backward compatibility
    "production_validation_stop": _post_stop,
    "pipeline_start": _post_run,
    "pipeline_stop": _post_stop,
    "candidate_check": _post_check,
    "candidate_optimize": _post_optimize_candidates,
    "candidate_submit": _post_submit,
}

__all__ = [
    "dispatch_get",
    "dispatch_post",
    "WebHandlerDispatchContext",
    "RouteDispatcher",
    "PayloadRouteDispatcher",
]

from .web_post_handlers import stop_job_payload  # noqa: F401
from .web_handler_dispatch_core import rate_limit_key as _rate_limit_key  # noqa: F401

# Backward-compat aliases
from .web_post_routes import _start_optimize_candidates_job  # noqa: F401
from .web_post_routes import _submit_with_lock  # noqa: F401

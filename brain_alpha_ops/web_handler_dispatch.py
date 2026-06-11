"""GET/POST route dispatch for the local web console handler."""

from __future__ import annotations

from functools import wraps
import logging
import time
from typing import Any, Callable
from urllib.parse import parse_qs

from brain_alpha_ops.research.assistant import AssistantResponseParseError
from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.web_candidate_payloads import compact_job_result as _compact_job_result
from brain_alpha_ops.web_dispatch_context import (
    WebDispatchActionContext,
    WebDispatchAssistantContext,
    WebDispatchConfigContext,
    WebDispatchCoreContext,
    WebDispatchJobContext,
    WebDispatchResearchContext,
    WebDispatchSessionContext,
    WebHandlerDispatchContext,
)
from brain_alpha_ops.web_handler_candidate_routes import get_candidates as _get_candidates
from brain_alpha_ops.web_payload_validation import (
    validate_alpha_action_payload,
    validate_assistant_cross_review_payload,
    validate_assistant_guidance_save_payload,
    validate_assistant_text_payload,
    validate_check_batch_payload,
    validate_generate_candidates_payload,
    validate_job_cancel_payload,
    validate_json_object_payload,
    validate_submit_batch_payload,
    validate_sync_alphas_payload,
)
from brain_alpha_ops.web_post_handlers import stop_job_payload


logger = logging.getLogger(__name__)

DEFAULT_HISTORY_LIMIT = 5000
MAX_HISTORY_LIMIT = 10000
DEFAULT_LEDGER_LIMIT = 100
MAX_LEDGER_LIMIT = 5000
MAX_RECORD_LOOKUP_LIMIT = 500
_TERMINAL_STATUSES = frozenset({
    "completed", "completed_with_warnings", "failed", "stopped", "cancelled", "canceled",
})
_LEGACY_FALLBACK_DISABLED_POST_PATHS = frozenset({"/api/pipeline/start"})
RouteDispatcher = Callable[[Any, Any, WebHandlerDispatchContext], None]
PayloadValidator = Callable[[Any], str]
PayloadRouteDispatcher = Callable[[Any, Any, WebHandlerDispatchContext, dict[str, Any]], None]


def dispatch_get(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    _dispatch_route("GET", handler, parsed, ctx, _GET_DISPATCH_HANDLERS)


def dispatch_post(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    _dispatch_route("POST", handler, parsed, ctx, _POST_DISPATCH_HANDLERS)


def _dispatch_route(
    method: str,
    handler: Any,
    parsed: Any,
    ctx: WebHandlerDispatchContext,
    handlers: dict[str, RouteDispatcher],
) -> None:
    if not handler._is_allowed_local_request():
        handler._json({"ok": False, "error_code": "ORIGIN_FORBIDDEN", "error": "forbidden local request origin"}, status=403)
        return
    route = ctx.route_for(method, parsed.path)
    if not route:
        if method == "POST" and parsed.path in _LEGACY_FALLBACK_DISABLED_POST_PATHS:
            handler._json({"ok": False, "error_code": "LEGACY_ROUTE_DISABLED", "error": "legacy pipeline route is disabled; use /api/run"}, status=404)
            return
        if method not in {"GET", "HEAD", "OPTIONS"}:
            if not handler._has_valid_session(parsed.query):
                handler._json({"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}, status=403)
                return
            replay_validator = getattr(handler, "_validate_replay_request", None)
            if callable(replay_validator):
                replay_result = replay_validator()
                if not replay_result.get("ok"):
                    status = 409 if replay_result.get("error_code") == "REPLAY_DETECTED" else 400
                    handler._json({"ok": False, **replay_result}, status=status)
                    return
            if not _apply_rate_limit(handler, ctx, method, parsed.path):
                return
        try:
            from brain_alpha_ops.web import dispatch_post as _legacy_dispatch
            body = handler._read_json() if method == "POST" else None
            _legacy_dispatch(handler, parsed.path, body)
            return
        except ImportError:
            logger.debug("Legacy dispatch not available for %s %s", method, redact_text(str(parsed.path)))
        except Exception as _legacy_exc:
            logger.error(
                "Legacy dispatch fallback failed for %s %s: %s",
                method, redact_text(str(parsed.path)), redact_text(str(_legacy_exc)),
                exc_info=True,
            )
        handler._json({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}, status=404)
        return
    if route.requires_session and not handler._has_valid_session(parsed.query):
        handler._json({"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}, status=403)
        return
    if method not in {"GET", "HEAD", "OPTIONS"} and route.requires_session:
        replay_validator = getattr(handler, "_validate_replay_request", None)
        if callable(replay_validator):
            replay_result = replay_validator()
            if not replay_result.get("ok"):
                status = 409 if replay_result.get("error_code") == "REPLAY_DETECTED" else 400
                handler._json({"ok": False, **replay_result}, status=status)
                return
    if getattr(route, "category", "api") == "api" and not _apply_rate_limit(handler, ctx, method, parsed.path):
        return
    route_handler = handlers.get(str(route.handler))
    if route_handler is None:
        handler._json({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}, status=404)
        return
    try:
        route_handler(handler, parsed, ctx)
    except (BrokenPipeError, ConnectionResetError):
        logger.info("web client disconnected before response completed: %s %s", method, redact_text(parsed.path))
        return
    except Exception as exc:
        logger.error("web route dispatch failed: %s %s", method, redact_text(parsed.path), exc_info=True)
        handler._json(ctx.web_error(exc, f"{method}_ROUTE_ERROR"), status=500)


def _rate_limit_key(handler: Any) -> str:
    session_getter = getattr(handler, "_session_id_from_cookie", None)
    if callable(session_getter):
        session_id = str(session_getter() or "").strip()
        if session_id:
            return f"session:{session_id}"
    client_address = getattr(handler, "client_address", ("local", 0))
    if isinstance(client_address, tuple) and client_address:
        return f"client:{client_address[0]}"
    headers = getattr(handler, "headers", {}) or {}
    return f"host:{headers.get('Host', 'local')}"


def _apply_rate_limit(handler: Any, ctx: WebHandlerDispatchContext, method: str, path: str) -> bool:
    rate_result = ctx.rate_limit_request(_rate_limit_key(handler), method, path)
    if rate_result.get("ok"):
        return True
    retry_value = rate_result.get("retry_after") or 1
    try:
        retry_after = str(int(float(retry_value)))
    except (TypeError, ValueError):
        retry_after = "1"
    handler._json({"ok": False, **rate_result}, status=429, extra_headers=[("Retry-After", retry_after)])
    return False


def _reject_invalid_payload(handler: Any, error: str) -> bool:
    if error:
        handler._json({"ok": False, "error_code": "VALIDATION_ERROR", "error": error}, status=400)
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
                handler._json(ctx.web_error(exc, assistant_error_code or error_code), status=400)
            except Exception as exc:
                logger.error("web post route failed: %s", redact_text(parsed.path), exc_info=True)
                handler._json(ctx.web_error(exc, error_code), status=400)

        return _wrapper

    return _decorate


def _reject_auxiliary_conflict(handler: Any, ctx: WebHandlerDispatchContext, **kwargs: Any) -> bool:
    conflict = ctx.active_auxiliary_operation(**kwargs)
    if not conflict:
        return False
    _kind, message = conflict
    handler._json({"ok": False, "error_code": "CONFLICT_AUX_OP", "error": message}, status=409)
    return True


def _with_session_credentials(handler: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> dict[str, Any]:
    return ctx.payload_with_brain_session_credentials(handler._session_id_from_cookie(), payload)


def _get_root(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    if ctx.remote_admin_required() and not ctx.has_valid_admin_token(getattr(handler, "headers", {})):
        handler._json({"ok": False, "error_code": "ADMIN_AUTH_REQUIRED", "error": "remote web access requires admin authentication"}, status=401)
        return
    session_id, csrf_token = ctx.get_or_create_session(handler._session_id_from_cookie())
    stream_token = ctx.stream_token_for_session(session_id)
    handler._html(ctx.render_html(csrf_token, stream_token), extra_headers=[("Set-Cookie", ctx.session_cookie_header(session_id))])


def _get_status(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    if not job_id:
        handler._json(ctx.active_job_payload(ctx.jobs, ctx.enrich_progress))
        return
    payload, status = _job_status_from_any_store(ctx, job_id)
    handler._json(payload, status=status)


def _job_status_from_any_store(ctx: WebHandlerDispatchContext, job_id: str) -> tuple[dict[str, Any], int]:
    for store, error in (
        (ctx.jobs, "unknown job"),
        (ctx.sync_jobs, "unknown sync job"),
        (ctx.check_jobs, "unknown check job"),
        (ctx.async_jobs, "unknown async job"),
    ):
        payload, status = ctx.job_status_payload(store, job_id, ctx.enrich_progress, error=error)
        if status == 200:
            return payload, status
    return {"ok": False, "error_code": "JOB_NOT_FOUND", "error": "unknown job"}, 404


def _get_config(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    handler._json({"ok": True, "config": ctx.public_run_config()})


def _get_config_schema(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    handler._json({"ok": True, "schema": ctx.public_config_schema()})


def _get_active_job(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    handler._json(ctx.active_job_payload(ctx.jobs, ctx.enrich_progress))


def _get_latest_result(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    handler._json(ctx.latest_result_snapshot())


def _get_health(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    handler._json(ctx.health_payload())


def _get_stream(handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext) -> None:
    handler._handle_sse_stream(parsed.query)


def _get_lifecycle(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    handler._json(ctx.lifecycle_payload(ctx.jobs, job_id, ctx.lifecycle_from_job))


def _get_cloud_alphas(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = _positive_query_int((query.get("limit") or [None])[0])
    handler._json({"ok": True, **ctx.cloud_alpha_snapshot(limit=limit)})


def _positive_query_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, parsed)


def _get_research_memory(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int((query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0], 1, MAX_HISTORY_LIMIT)
    top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 50)
    handler._json(ctx.research_memory_snapshot(limit=limit, top_n=top_n))


def _get_research_knowledge(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int((query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0], 1, MAX_LEDGER_LIMIT)
    min_confidence = ctx.bounded_query_float((query.get("min_confidence") or ["0.0"])[0], 0.0, 1.0)
    handler._json(ctx.research_knowledge_snapshot(limit=limit, min_confidence=min_confidence))


def _get_research_observability(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int((query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0], 1, MAX_HISTORY_LIMIT)
    top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 50)
    include_cloud = ctx.payload_truthy((query.get("include_cloud") or ["true"])[0])
    handler._json(ctx.research_observability_snapshot(limit=limit, top_n=top_n, include_cloud=include_cloud))


def _get_prompt_runs(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int((query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0], 1, MAX_LEDGER_LIMIT)
    handler._json(ctx.prompt_run_ledger_snapshot(limit=limit))


def _get_sqlite_indexes(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 100)
    handler._json(ctx.sqlite_index_snapshot(top_n=top_n))


def _get_sqlite_expression_lookup(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    expression = (query.get("expression") or [""])[0]
    top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 100)
    min_similarity = ctx.bounded_query_float((query.get("min_similarity") or ["0.75"])[0], 0.0, 1.0)
    max_scan_rows = ctx.bounded_query_int((query.get("max_scan_rows") or ["2000"])[0], 1, 10000)
    handler._json(ctx.sqlite_expression_lookup_payload(expression=expression, top_n=top_n, min_similarity=min_similarity, max_scan_rows=max_scan_rows))


def _get_sqlite_record_lookup(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    alpha_id = (query.get("alpha_id") or [""])[0]
    limit = ctx.bounded_query_int((query.get("limit") or ["50"])[0], 1, MAX_RECORD_LOOKUP_LIMIT)
    handler._json(ctx.sqlite_record_lookup_payload(alpha_id=alpha_id, limit=limit))


def _get_assistant_context(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int((query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0], 1, MAX_HISTORY_LIMIT)
    top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 50)
    include_prompt = ctx.payload_truthy((query.get("include_prompt") or ["true"])[0])
    include_sensitive = ctx.payload_truthy((query.get("include_sensitive") or ["false"])[0])
    handler._json(ctx.assistant_context_snapshot(limit=limit, top_n=top_n, include_prompt=include_prompt, include_sensitive=include_sensitive))


def _get_assistant_guidance(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int((query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0], 1, MAX_LEDGER_LIMIT)
    raw_min_confidence = (query.get("min_confidence") or [None])[0]
    min_confidence: float | None = None if raw_min_confidence in (None, "") else ctx.bounded_query_float(raw_min_confidence, 0.0, 1.0)
    handler._json(ctx.assistant_guidance_snapshot(limit=limit, min_confidence=min_confidence))


def _get_assistant_request(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int((query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0], 1, MAX_HISTORY_LIMIT)
    top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 50)
    include_prompt = ctx.payload_truthy((query.get("include_prompt") or ["true"])[0])
    include_draft = ctx.payload_truthy((query.get("include_draft") or ["true"])[0])
    include_sensitive = ctx.payload_truthy((query.get("include_sensitive") or ["false"])[0])
    handler._json(ctx.assistant_request_snapshot(limit=limit, top_n=top_n, include_prompt=include_prompt, include_offline_draft=include_draft, include_sensitive=include_sensitive))


def _get_anti_overfit(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    candidate_id = (parse_qs(parsed.query).get("candidate_id") or [""])[0]
    handler._json(ctx.anti_overfit_snapshot(candidate_id=candidate_id))


def _get_rolling_validation(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    candidate_id = (query.get("candidate_id") or [""])[0]
    windows = ctx.bounded_query_int((query.get("windows") or ["4"])[0], 2, 50)
    handler._json(ctx.rolling_validation_snapshot(candidate_id=candidate_id, windows=windows))


def _get_sync_status(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    job_id = (query.get("job_id") or [""])[0]
    if job_id:
        payload, status = ctx.job_status_payload(ctx.sync_jobs, job_id, ctx.enrich_progress, error="unknown sync job")
    else:
        payload, status = ctx.active_job_payload(ctx.sync_jobs, ctx.enrich_progress), 200
    payload = _with_official_context_cache(payload, ctx)
    if ctx.payload_truthy((query.get("compact") or ["false"])[0]):
        payload = _compact_job_result(payload)
    handler._json(payload, status=status)


def _with_official_context_cache(payload: dict[str, Any], ctx: WebHandlerDispatchContext) -> dict[str, Any]:
    try:
        counts = ctx.official_context_file_counts()
    except Exception as exc:
        logger.warning("failed to read official context cache summary for sync status", exc_info=True)
        return {**payload, "official_context_cache": {"ok": False, "error": redact_text(str(exc))}}
    cache = {
        "ok": True,
        "fields_count": int(counts.get("fields_count", 0) or 0),
        "operators_count": int(counts.get("operators_count", 0) or 0),
        "datasets_count": int(counts.get("datasets_count", 0) or 0),
    }
    manifest = counts.get("context_cache_manifest")
    if isinstance(manifest, dict):
        cache["manifest"] = {
            "complete": bool(manifest.get("complete")),
            "is_stale": bool(manifest.get("is_stale")),
            "missing_files": list(manifest.get("missing_files") or []),
            "stale_files": list(manifest.get("stale_files") or manifest.get("expired_files") or []),
            "record_counts": dict(manifest.get("record_counts") or {}),
        }
    return {**payload, "official_context_cache": cache}


def _get_check_status(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    payload, status = ctx.job_status_payload(ctx.check_jobs, job_id, ctx.enrich_progress, error="unknown check job")
    handler._json(payload, status=status)


def _get_check_results(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    handler._json({"ok": True, **ctx.load_check_results()})


def _get_profile(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    handler._json(ctx.profile_payload(ctx.user_profile_snapshot))


def _get_presets(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    handler._json(ctx.presets_payload(ctx.load_presets))


def _get_redline_report(handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext) -> None:
    from brain_alpha_ops.web_redline_scoring import handle_redline_report
    handler._json(handle_redline_report(parse_qs(parsed.query)))


def _get_scoring_health(handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext) -> None:
    from brain_alpha_ops.web_redline_scoring import handle_scoring_health
    handler._json(handle_scoring_health(parse_qs(parsed.query)))


def _get_checkpoint_status(handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext) -> None:
    from brain_alpha_ops.web_redline_scoring import handle_checkpoint_status
    handler._json(handle_checkpoint_status(parse_qs(parsed.query)))


def _get_backtest_slots(handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext) -> None:
    from brain_alpha_ops.web_routes import _backtest_slots_payload

    handler._json(_backtest_slots_payload())


def _get_submit_readiness(handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext) -> None:
    from brain_alpha_ops.web_routes import _submit_readiness_payload

    handler._json(_submit_readiness_payload())


@_validated_post_route(validate_json_object_payload, "RUN_ERROR")
def _post_run(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    safe_payload = _with_session_credentials(handler, ctx, _non_submit_run_payload(payload))
    ctx.validate_run_payload(safe_payload)
    # M-SEC-02: latest_active() releases lock before _create_non_submit_run_job().
    # Low risk for single-user local app; lock held per-operation by JobStore internally.
    active = ctx.jobs.latest_active()
    if active:
        active_job_id, _job = active
        handler._json({"ok": False, "error_code": "CONFLICT_RUNNING", "error": "已有生产任务正在运行，请先停止当前任务。", "job_id": active_job_id}, status=409)
        return
    job_id = _create_non_submit_run_job(ctx.jobs)
    ctx.start_run_job(job_id, safe_payload)
    handler._json({
        "ok": True,
        "job_id": job_id,
        "task_id": job_id,
        "auto_submit": False,
        "submitted": False,
        "sse_url": f"/sse?job_id={job_id}",
        "status_url": f"/api/production-validation/status?job_id={job_id}",
    })


def _non_submit_run_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
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
            "status_message": "非提交流水线已排队。",
            "alpha_id": "",
        },
    }
    return store.create(initial)


@_validated_post_route(validate_json_object_payload, "CONNECTION_ERROR")
def _post_test_connection(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    payload = _with_session_credentials(handler, ctx, payload)
    result = ctx.connection_test_post_payload(payload, ctx.test_connection)
    session_id = handler._session_id_from_cookie()
    if isinstance(result, dict) and result.get("ok"):
        session = ctx.mark_brain_connection_verified(session_id, result, payload)
    else:
        session = ctx.clear_brain_connection_verified(session_id)
    handler._json({**(result if isinstance(result, dict) else {"ok": False}), "session": session})


@_validated_post_route(validate_json_object_payload, "CONFIG_SAVE_ERROR")
def _post_config_save(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    handler._json(ctx.save_run_config_payload(payload))


@_validated_post_route(validate_job_cancel_payload, "STOP_ERROR")
def _post_stop(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    handler._json(ctx.stop_job_payload(ctx.jobs, payload))


# /api/cancel is an alias for /api/stop
@_validated_post_route(validate_job_cancel_payload, "CANCEL_ERROR")
def _post_cancel(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    job_id = str((payload or {}).get("job_id") or "")
    # Search all stores to find the job and determine its type
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
                handler._json({"ok": True, "status": status, "already_terminal": True})
                return
            result = ctx.stop_job_payload(store, payload)
            handler._json({**result, "job_id": job_id, "task_id": job_id, "job_type": job_type, "status": "stopping"})
            return
    handler._json({"ok": False, "error_code": "JOB_NOT_FOUND", "error": "未找到可停止的任务。", "job_id": job_id}, status=404)


@_validated_post_route(validate_sync_alphas_payload, "SYNC_ERROR")
def _post_sync_alphas(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    _start_sync_job(handler, ctx, payload)


def _start_sync_job(handler: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    active = ctx.sync_jobs.latest_active()
    if active:
        active_job_id, _job = active
        handler._json({
            "ok": False,
            "error": "已有云端同步任务正在运行。",
            "job_id": active_job_id,
            "task_id": active_job_id,
            "status_url": f"/api/sync_status?job_id={active_job_id}",
        }, status=409)
        return
    if _reject_auxiliary_conflict(handler, ctx, exclude="sync"):
        return
    payload = _with_session_credentials(handler, ctx, payload)
    response, status = ctx.background_job_start_payload(ctx.sync_jobs, payload, ctx.start_sync_job, conflict_error="active cloud sync job")
    job_id = str(response.get("job_id") or response.get("task_id") or "")
    if job_id:
        response = {**response, "status_url": f"/api/sync_status?job_id={job_id}"}
    handler._json(response, status=status)


@_validated_post_route(validate_sync_alphas_payload, "SYNC_CONTEXT_ERROR")
def _post_sync_context_only(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    context_payload = {
        **payload,
        "contextOnly": True,
        "refreshOfficialContext": True,
        "userFacingOperation": "official_operations_context_only_retry",
    }
    _start_sync_job(handler, ctx, context_payload)


@_validated_post_route(validate_job_cancel_payload, "SYNC_CANCEL_ERROR")
def _post_sync_cancel(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    job_id = str((payload or {}).get("job_id") or "")
    row = ctx.sync_jobs.get(job_id)
    if row is not None:
        status = str(row.get("status", ""))
        if status in _TERMINAL_STATUSES:
            handler._json({"ok": True, "job_id": job_id, "status": status, "already_terminal": True})
            return
    result = ctx.stop_job_payload(ctx.sync_jobs, payload)
    if result.get("ok"):
        stopping_message = "云端同步停止请求已发送，后台会在当前官方接口返回后结束。"
        stopping_since_ms = int(time.time() * 1000)
        row = ctx.sync_jobs.get(job_id) if hasattr(ctx.sync_jobs, "get") else None
        progress = dict(row.get("progress") or {}) if isinstance(row, dict) else {}
        progress.update({
            "job_id": job_id,
            "task_id": job_id,
            "phase": "stopping",
            "status_code": "STOPPING",
            "status_message": stopping_message,
            "message": stopping_message,
            "stopping_since_ms": stopping_since_ms,
        })
        updater = getattr(ctx.sync_jobs, "update", None)
        if callable(updater):
            updater(job_id, status="stopping", progress=progress)
        handler._json({**result, "job_id": job_id, "status": "stopping", "message": stopping_message, "stopping_since_ms": stopping_since_ms})
        return
    handler._json({**result, "job_id": job_id, "error_code": "SYNC_JOB_NOT_FOUND", "error": "未找到可停止的云端同步任务。"}, status=404)


@_validated_post_route(validate_alpha_action_payload, "CHECK_ERROR")
def _post_check(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    if _reject_auxiliary_conflict(handler, ctx, allow_production=True):
        return
    payload = _with_session_credentials(handler, ctx, payload)
    handler._json(ctx.check_candidate(payload))


@_validated_post_route(validate_generate_candidates_payload, "GENERATE_CANDIDATES_ERROR", assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR")
def _post_generate_candidates(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    response, status = ctx.background_job_start_payload(ctx.async_jobs, payload, ctx.start_generate_candidates_job, conflict_error="active async job")
    handler._json(response, status=status)


@_validated_post_route(validate_check_batch_payload, "CHECK_BATCH_ERROR")
def _post_check_batch(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    active = ctx.check_jobs.latest_active()
    if active:
        active_job_id, _job = active
        handler._json({"ok": False, "error": "已有批量检查任务正在运行。", "job_id": active_job_id}, status=409)
        return
    if _reject_auxiliary_conflict(handler, ctx, exclude="check", allow_production=True):
        return
    payload = _with_session_credentials(handler, ctx, payload)
    response, status = ctx.background_job_start_payload(ctx.check_jobs, payload, ctx.start_check_batch_job, conflict_error="active batch check job")
    handler._json(response, status=status)


@_validated_post_route(validate_alpha_action_payload, "SUBMIT_ERROR")
def _post_submit(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    # Web flow unconditionally blocks real BRAIN submits as a safety gate
    handler._json({"ok": False, "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW", "submitted": False}, status=403)


@_validated_post_route(validate_submit_batch_payload, "SUBMIT_BATCH_ERROR")
def _post_submit_batch(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    # Web flow unconditionally blocks real BRAIN batch submits as a safety gate
    handler._json({"ok": False, "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW", "submitted": False}, status=403)


@_validated_post_route(validate_assistant_text_payload, "ASSISTANT_RESPONSE_PARSE_ERROR", assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR")
def _post_assistant_response_parse(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    handler._json(ctx.assistant_response_parse_post_payload(payload, ctx.assistant_response_parse_payload))


@_validated_post_route(validate_assistant_text_payload, "ASSISTANT_RESPONSE_GUIDANCE_ERROR", assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR")
def _post_assistant_response_guidance(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    handler._json(ctx.assistant_response_guidance_post_payload(payload, ctx.assistant_response_guidance_payload))


@_validated_post_route(validate_assistant_cross_review_payload, "ASSISTANT_CROSS_REVIEW_ERROR", assistant_error_code="ASSISTANT_CROSS_REVIEW_PARSE_ERROR")
def _post_assistant_cross_review(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    handler._json(ctx.assistant_cross_review_payload(payload))


@_validated_post_route(validate_assistant_guidance_save_payload, "ASSISTANT_GUIDANCE_SAVE_ERROR", assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR")
def _post_assistant_guidance(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    handler._json(ctx.save_assistant_guidance_post_payload(payload, ctx.save_assistant_guidance_payload))


def _post_session(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    """Create a new web session and return a usable CSRF token."""
    if ctx.remote_admin_required() and not ctx.has_valid_admin_token(getattr(handler, "headers", {})):
        handler._json({"ok": False, "error_code": "ADMIN_AUTH_REQUIRED", "error": "remote web access requires admin authentication"}, status=401)
        return
    session_id, csrf_token = ctx.get_or_create_session(handler._session_id_from_cookie())
    stream_token = ctx.stream_token_for_session(session_id)
    session = ctx.session_status(session_id)
    ttl = int(session.get("ttl_seconds") or 43200)
    handler._json({
        "ok": True,
        "session_id": session_id[:8],
        "csrf_token": csrf_token,
        "stream_token": stream_token,
        "ttl_seconds": ttl,
        "connected": bool(session.get("connected")),
        "brain_connection_verified": bool(session.get("brain_connection_verified")),
        "session": session,
    }, extra_headers=[("Set-Cookie", ctx.session_cookie_header(session_id))])


def _post_logout(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    response, headers = ctx.session_end_payload(handler._session_id_from_cookie(), ctx.expire_session, ctx.expired_session_cookie_header)
    handler._json(response, extra_headers=headers)


def _post_shutdown(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    _post_logout(handler, parsed, ctx)
    ctx.start_shutdown()


@_validated_post_route(validate_alpha_action_payload, "SCORING_ERROR")
def _post_scoring_evaluate(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    response, status = ctx.background_job_start_payload(ctx.async_jobs, payload, ctx.start_scoring_evaluate_job, conflict_error="active async job")
    handler._json(response, status=status)


@_validated_post_route(validate_alpha_action_payload, "SCORING_ERROR")
def _post_scoring_attribution(handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    from brain_alpha_ops.web_redline_scoring import handle_scoring_attribution
    handler._json(handle_scoring_attribution(payload))


def _get_candidates_simulate_eligible(handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext) -> None:
    """Return eligible candidates for BRAIN simulation."""
    from brain_alpha_ops.web_candidate_simulation import simulation_candidates_payload
    from brain_alpha_ops.redaction import redact_error_message
    try:
        # Use parse_qs to get {key: [val]} then flatten single-element lists.
        _parsed_qs = parse_qs(_parsed.query)
        _flat = {k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in _parsed_qs.items()}
        handler._json(simulation_candidates_payload(_flat))
    except Exception as exc:
        logger.exception("simulation_candidates_payload failed")
        handler._json({"ok": False, "error": redact_error_message(exc)}, status=500)


def _get_phase_state(handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext) -> None:
    """Return phase navigation state for the frontend PhaseShell component."""
    from brain_alpha_ops.web.handlers.phase import phase_state_payload
    try:
        handler._json(phase_state_payload(
            sync_jobs=_ctx.sync_jobs if hasattr(_ctx, "sync_jobs") else None,
            candidate_repo=getattr(_ctx, "candidate_repo", None),
            connection_tracker=getattr(_ctx, "connection_tracker", None),
            readiness_service=getattr(_ctx, "readiness_service", None),
            session_status=_ctx.session_status(handler._session_id_from_cookie()),
            cloud_alpha_snapshot=getattr(_ctx, "cloud_alpha_snapshot", None),
            official_context_file_counts=getattr(_ctx, "official_context_file_counts", None),
        ))
    except Exception:
        logger.warning("phase_state_payload failed — returning safe default", exc_info=True)
        handler._json({"ok": True, "current_phase": "connect", "connected": False, "context_fresh": False, "candidates_count": 0, "scored_count": 0, "readiness_passed": False})


_GET_DISPATCH_HANDLERS: dict[str, RouteDispatcher] = {
    "root": _get_root,
    "status": _get_status,
    "config": _get_config,
    "config_schema": _get_config_schema,
    "active_job": _get_active_job,
    "latest_result": _get_latest_result,
    "health": _get_health,
    "stream": _get_stream,
    "lifecycle": _get_lifecycle,
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
    "candidates_simulate_eligible": _get_candidates_simulate_eligible,
    "phase_state": _get_phase_state,
}

@_validated_post_route(validate_json_object_payload, "SIMULATE_ERROR")
def _post_candidates_simulate(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext, payload: dict[str, Any]) -> None:
    """Start BRAIN simulation for eligible candidates."""
    from brain_alpha_ops.web_candidate_simulation import simulate_candidates_job, simulation_candidates_payload

    import threading
    from brain_alpha_ops.redaction import redact_error_message

    if payload.get("preview"):
        try:
            handler._json(simulation_candidates_payload(payload))
        except Exception as exc:
            logger.exception("simulation preview failed")
            handler._json({"ok": False, "error": redact_error_message(exc)}, status=500)
        return

    if _reject_auxiliary_conflict(handler, ctx):
        return

    payload = _with_session_credentials(handler, ctx, payload)
    store = ctx.async_jobs
    start_message = "正在启动官方 BRAIN 模拟任务。"
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
        phase = (active_job.get("progress") or {}).get("phase") or active_job.get("phase") or "async"
        handler._json({
            "ok": False,
            "error": "已有后台任务正在运行，请完成或停止后再启动官方候选模拟。",
            "error_code": "CONFLICT_RUNNING",
            "job_id": active_job_id,
            "phase": phase,
        }, status=409)
        return

    if not job_id:
        for jid, job in list(store.jobs.items()):
            if str(job.get("status") or "").lower() in {"queued", "running", "stopping"}:
                phase = (job.get("progress") or {}).get("phase", "")
                if "simulat" in str(phase).lower():
                    handler._json({
                        "ok": False,
                        "error": "已有模拟任务在运行",
                        "error_code": "CONFLICT_RUNNING",
                        "job_id": jid,
                    }, status=409)
                    return

    if not job_id:
        job_id = store.create(initial_job)

    def run_sim() -> None:
        from brain_alpha_ops.web_simulation_job import create_sim_job_store
        simulate_candidates_job(job_id, payload, job_store=create_sim_job_store(store), log=logger)

    threading.Thread(target=run_sim, daemon=True).start()
    handler._json({
        "ok": True,
        "job_id": job_id,
        "task_id": job_id,
        "sse_url": f"/sse?job_id={job_id}",
        "status_url": f"/api/status?job_id={job_id}",
    })

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
    "check_batch": _post_check_batch,
    "submit": _post_submit,
    "submit_batch": _post_submit_batch,
    "assistant_response_parse": _post_assistant_response_parse,
    "assistant_response_guidance": _post_assistant_response_guidance,
    "assistant_cross_review": _post_assistant_cross_review,
    "assistant_guidance": _post_assistant_guidance,
    "logout": _post_logout,
    "shutdown": _post_shutdown,
    "session": _post_session,
    "scoring_evaluate": _post_scoring_evaluate,
    "scoring_attribution": _post_scoring_attribution,
    "candidates_simulate": _post_candidates_simulate,
}


def _submit_with_lock(
    handler: Any,
    ctx: WebHandlerDispatchContext,
    submitter: Callable[[dict[str, Any]], dict[str, Any]],
    error_code: str,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    if _reject_auxiliary_conflict(handler, ctx, exclude="submit", allow_production=True):
        return
    if not ctx.submit_lock.acquire(blocking=False):
        handler._json({"ok": False, "error": "已有提交任务正在运行，请完成后再操作。"}, status=409)
        return
    try:
        payload = handler._read_json() if payload is None else payload
        handler._json(submitter(payload))
    except Exception as exc:
        logger.error("web submit route failed: %s", error_code, exc_info=True)
        handler._json(ctx.web_error(exc, error_code), status=400)
    finally:
        ctx.submit_lock.release()

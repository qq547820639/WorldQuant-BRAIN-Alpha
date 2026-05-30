"""GET/POST route dispatch for the local web console handler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs

from brain_alpha_ops.research.assistant import AssistantResponseParseError
from brain_alpha_ops.web_payload_validation import (
    validate_assistant_cross_review_payload,
    validate_assistant_guidance_save_payload,
    validate_assistant_text_payload,
    validate_alpha_action_payload,
    validate_check_batch_payload,
    validate_generate_candidates_payload,
    validate_json_object_payload,
    validate_job_cancel_payload,
    validate_submit_batch_payload,
    validate_sync_alphas_payload,
)


DEFAULT_HISTORY_LIMIT = 5000
MAX_HISTORY_LIMIT = 10000
DEFAULT_LEDGER_LIMIT = 100
MAX_LEDGER_LIMIT = 5000
MAX_RECORD_LOOKUP_LIMIT = 500
DEFAULT_CLOUD_ALPHA_LIMIT = 500
MAX_CLOUD_ALPHA_LIMIT = 2000
@dataclass(frozen=True)
class WebHandlerDispatchContext:
    route_for: Callable[[str, str], Any]
    web_error: Callable[[Exception, str], dict[str, Any]]
    payload_truthy: Callable[[Any], bool]
    bounded_query_int: Callable[[Any, int, int], int]
    bounded_query_float: Callable[[Any, float, float], float]
    remote_admin_required: Callable[[], bool]
    has_valid_admin_token: Callable[[Any], bool]
    get_or_create_session: Callable[[str], tuple[str, str]]
    stream_token_for_session: Callable[[str], str]
    session_cookie_header: Callable[[str], str]
    render_html: Callable[[str, str], str]
    job_status_payload: Callable[..., tuple[dict[str, Any], int]]
    active_job_payload: Callable[..., dict[str, Any]]
    lifecycle_payload: Callable[..., dict[str, Any]]
    health_payload: Callable[[], dict[str, Any]]
    profile_payload: Callable[..., dict[str, Any]]
    presets_payload: Callable[..., dict[str, Any]]
    jobs: Any
    sync_jobs: Any
    check_jobs: Any
    async_jobs: Any
    enrich_progress: Callable[[dict[str, Any]], dict[str, Any]]
    public_run_config: Callable[[], dict[str, Any]]
    public_config_schema: Callable[[], dict[str, Any]]
    save_run_config_payload: Callable[[dict[str, Any]], dict[str, Any]]
    rate_limit_request: Callable[[str, str, str], dict[str, Any]]
    latest_result_snapshot: Callable[[], dict[str, Any]]
    lifecycle_from_job: Callable[[dict[str, Any]], list[dict[str, Any]]]
    cloud_alpha_snapshot: Callable[..., dict[str, Any]]
    research_memory_snapshot: Callable[..., dict[str, Any]]
    research_knowledge_snapshot: Callable[..., dict[str, Any]]
    research_observability_snapshot: Callable[..., dict[str, Any]]
    prompt_run_ledger_snapshot: Callable[..., dict[str, Any]]
    sqlite_index_snapshot: Callable[..., dict[str, Any]]
    sqlite_expression_lookup_payload: Callable[..., dict[str, Any]]
    sqlite_record_lookup_payload: Callable[..., dict[str, Any]]
    assistant_context_snapshot: Callable[..., dict[str, Any]]
    assistant_guidance_snapshot: Callable[..., dict[str, Any]]
    assistant_request_snapshot: Callable[..., dict[str, Any]]
    anti_overfit_snapshot: Callable[..., dict[str, Any]]
    rolling_validation_snapshot: Callable[..., dict[str, Any]]
    load_check_results: Callable[[], dict[str, Any]]
    user_profile_snapshot: Callable[[], dict[str, Any]]
    load_presets: Callable[[], dict[str, Any]]
    connection_test_post_payload: Callable[..., dict[str, Any]]
    test_connection: Callable[[dict[str, Any]], dict[str, Any]]
    validate_run_payload: Callable[[dict[str, Any]], None]
    background_job_start_payload: Callable[..., tuple[dict[str, Any], int]]
    start_run_job: Callable[[str, dict[str, Any]], None]
    stop_job_payload: Callable[..., dict[str, Any]]
    active_auxiliary_operation: Callable[..., tuple[str, str] | None]
    start_sync_job: Callable[[str, dict[str, Any]], None]
    check_candidate: Callable[[dict[str, Any]], dict[str, Any]]
    generate_candidates_payload: Callable[[dict[str, Any]], dict[str, Any]]
    start_generate_candidates_job: Callable[[str, dict[str, Any]], None]
    start_check_batch_job: Callable[[str, dict[str, Any]], None]
    start_scoring_evaluate_job: Callable[[str, dict[str, Any]], None]
    start_submit_batch_job: Callable[[str, dict[str, Any]], None]
    submit_lock: Any
    submit_candidate: Callable[[dict[str, Any]], dict[str, Any]]
    submit_batch: Callable[[dict[str, Any]], dict[str, Any]]
    assistant_response_parse_post_payload: Callable[..., dict[str, Any]]
    assistant_response_parse_payload: Callable[[dict[str, Any]], dict[str, Any]]
    assistant_response_guidance_post_payload: Callable[..., dict[str, Any]]
    assistant_response_guidance_payload: Callable[[dict[str, Any]], dict[str, Any]]
    assistant_cross_review_payload: Callable[[dict[str, Any]], dict[str, Any]]
    save_assistant_guidance_post_payload: Callable[..., dict[str, Any]]
    save_assistant_guidance_payload: Callable[[dict[str, Any]], dict[str, Any]]
    session_end_payload: Callable[..., tuple[dict[str, Any], list[tuple[str, str]]]]
    expire_session: Callable[[str], None]
    expired_session_cookie_header: Callable[[], str]
    start_shutdown: Callable[[], None]


RouteDispatcher = Callable[[Any, Any, WebHandlerDispatchContext], None]


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
    if getattr(route, "category", "api") == "api":
        rate_result = ctx.rate_limit_request(_rate_limit_key(handler), method, parsed.path)
        if not rate_result.get("ok"):
            retry_after = str(rate_result.get("retry_after") or 1)
            handler._json({"ok": False, **rate_result}, status=429, extra_headers=[("Retry-After", retry_after)])
            return
    route_handler = handlers.get(str(route.handler))
    if route_handler is None:
        handler._json({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}, status=404)
        return
    try:
        route_handler(handler, parsed, ctx)
    except Exception as exc:
        handler._json(ctx.web_error(exc, f"{method}_ROUTE_ERROR"), status=500)


def _rate_limit_key(handler: Any) -> str:
    session_getter = getattr(handler, "_session_id_from_cookie", None)
    if callable(session_getter):
        session_id = str(session_getter() or "").strip()
        if session_id:
            return f"session:{session_id}"
    headers = getattr(handler, "headers", {}) or {}
    return f"host:{headers.get('Host', 'local')}"


def _reject_invalid_payload(handler: Any, error: str) -> bool:
    if error:
        handler._json({"ok": False, "error_code": "VALIDATION_ERROR", "error": error}, status=400)
    return bool(error)


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


def _get_candidates(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    """Return lifecycle records wrapped as {candidates: [...]} for the React frontend."""
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    lifecycle = ctx.lifecycle_payload(ctx.jobs, job_id, ctx.lifecycle_from_job)
    rows = lifecycle.get("records") if isinstance(lifecycle.get("records"), list) else []
    if not _has_candidate_like_rows(rows):
        rows = _latest_async_candidates(ctx.async_jobs)
    handler._json({"ok": True, "candidates": rows, "count": len(rows)})


def _has_candidate_like_rows(rows: list[Any]) -> bool:
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else row
        if candidate.get("alpha_id") or candidate.get("official_alpha_id") or candidate.get("expression"):
            return True
    return False


def _latest_async_candidates(async_jobs: Any) -> list[dict[str, Any]]:
    latest_any = getattr(async_jobs, "all", None)
    rows = []
    if callable(latest_any):
        rows = latest_any(limit=25)
    else:
        latest = getattr(async_jobs, "latest_any", None)
        if callable(latest):
            item = latest()
            rows = [item] if item else []
    for _job_id, job in rows:
        result = job.get("result") if isinstance(job, dict) else {}
        if not isinstance(result, dict):
            continue
        candidates = result.get("candidates") or result.get("candidates_preview") or []
        if isinstance(candidates, list) and candidates:
            return [row for row in candidates if isinstance(row, dict)]
    return []


def _compact_job_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload
    compact_result = dict(result)
    for key in ("alphas", "cloud_alphas"):
        rows = compact_result.get(key)
        if isinstance(rows, list):
            compact_result[key + "_count"] = len(rows)
            compact_result.pop(key, None)
    return {**payload, "result": compact_result}


def _get_cloud_alphas(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int((query.get("limit") or [str(DEFAULT_CLOUD_ALPHA_LIMIT)])[0], 1, MAX_CLOUD_ALPHA_LIMIT)
    handler._json({"ok": True, **ctx.cloud_alpha_snapshot(limit=limit)})


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
    handler._json(ctx.sqlite_expression_lookup_payload(
        expression=expression,
        top_n=top_n,
        min_similarity=min_similarity,
        max_scan_rows=max_scan_rows,
    ))


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
    handler._json(ctx.assistant_request_snapshot(
        limit=limit,
        top_n=top_n,
        include_prompt=include_prompt,
        include_offline_draft=include_draft,
        include_sensitive=include_sensitive,
    ))


def _get_anti_overfit(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    candidate_id = (parse_qs(parsed.query).get("candidate_id") or [""])[0]
    handler._json(ctx.anti_overfit_snapshot(candidate_id=candidate_id))


def _get_rolling_validation(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    query = parse_qs(parsed.query)
    candidate_id = (query.get("candidate_id") or [""])[0]
    windows = ctx.bounded_query_int((query.get("windows") or ["4"])[0], 2, 50)
    handler._json(ctx.rolling_validation_snapshot(candidate_id=candidate_id, windows=windows))


def _get_sync_status(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    payload, status = ctx.job_status_payload(ctx.sync_jobs, job_id, ctx.enrich_progress, error="unknown sync job")
    query = parse_qs(parsed.query)
    if ctx.payload_truthy((query.get("compact") or ["false"])[0]):
        payload = _compact_job_result(payload)
    handler._json(payload, status=status)


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


def _post_run(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_json_object_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        ctx.validate_run_payload(payload)
        active = ctx.jobs.latest_active()
        if active:
            active_job_id, _job = active
            handler._json({"ok": False, "error_code": "CONFLICT_RUNNING", "error": "已有生产任务正在运行，请先停止当前任务。", "job_id": active_job_id}, status=409)
            return
        response, status = ctx.background_job_start_payload(ctx.jobs, payload, ctx.start_run_job, conflict_error="active production job")
        handler._json(response, status=status)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "RUN_ERROR"), status=400)


def _post_test_connection(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_json_object_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        handler._json(ctx.connection_test_post_payload(payload, ctx.test_connection))
    except Exception as exc:
        handler._json(ctx.web_error(exc, "CONNECTION_ERROR"), status=400)


def _post_config_save(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_json_object_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        handler._json(ctx.save_run_config_payload(payload))
    except Exception as exc:
        handler._json(ctx.web_error(exc, "CONFIG_SAVE_ERROR"), status=400)


def _post_stop(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_job_cancel_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        handler._json(ctx.stop_job_payload(ctx.jobs, payload))
    except Exception as exc:
        handler._json(ctx.web_error(exc, "STOP_ERROR"), status=400)


def _post_sync_alphas(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_sync_alphas_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        active = ctx.sync_jobs.latest_active()
        if active:
            active_job_id, _job = active
            handler._json({"ok": False, "error": "已有云端同步任务正在运行。", "job_id": active_job_id}, status=409)
            return
        conflict = ctx.active_auxiliary_operation(exclude="sync")
        if conflict:
            _kind, message = conflict
            handler._json({"ok": False, "error_code": "CONFLICT_AUX_OP", "error": message}, status=409)
            return
        response, status = ctx.background_job_start_payload(ctx.sync_jobs, payload, ctx.start_sync_job, conflict_error="active cloud sync job")
        handler._json(response, status=status)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "SYNC_ERROR"), status=400)


def _post_sync_cancel(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_job_cancel_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        result = ctx.stop_job_payload(ctx.sync_jobs, payload)
        job_id = str((payload or {}).get("job_id") or "")
        if result.get("ok"):
            handler._json({
                **result,
                "job_id": job_id,
                "status": "stopping",
                "message": "云端同步停止请求已发送，后台会在当前官方接口返回后结束。",
            })
            return
        handler._json({
            **result,
            "job_id": job_id,
            "error_code": "SYNC_JOB_NOT_FOUND",
            "error": "未找到可停止的云端同步任务。",
        }, status=404)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "SYNC_CANCEL_ERROR"), status=400)


def _post_check(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_alpha_action_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        conflict = ctx.active_auxiliary_operation(allow_production=True)
        if conflict:
            _kind, message = conflict
            handler._json({"ok": False, "error_code": "CONFLICT_AUX_OP", "error": message}, status=409)
            return
        handler._json(ctx.check_candidate(payload))
    except Exception as exc:
        handler._json(ctx.web_error(exc, "CHECK_ERROR"), status=400)


def _post_generate_candidates(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_generate_candidates_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        response, status = ctx.background_job_start_payload(
            ctx.async_jobs,
            payload,
            ctx.start_generate_candidates_job,
            conflict_error="active async job",
        )
        handler._json(response, status=status)
    except AssistantResponseParseError as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "GENERATE_CANDIDATES_ERROR"), status=400)


def _post_check_batch(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_check_batch_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        active = ctx.check_jobs.latest_active()
        if active:
            active_job_id, _job = active
            handler._json({"ok": False, "error": "已有批量检查任务正在运行。", "job_id": active_job_id}, status=409)
            return
        conflict = ctx.active_auxiliary_operation(exclude="check", allow_production=True)
        if conflict:
            _kind, message = conflict
            handler._json({"ok": False, "error_code": "CONFLICT_AUX_OP", "error": message}, status=409)
            return
        response, status = ctx.background_job_start_payload(ctx.check_jobs, payload, ctx.start_check_batch_job, conflict_error="active batch check job")
        handler._json(response, status=status)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "CHECK_BATCH_ERROR"), status=400)


def _post_submit(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_alpha_action_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
    except Exception as exc:
        handler._json(ctx.web_error(exc, "SUBMIT_ERROR"), status=400)
        return
    _submit_with_lock(handler, ctx, ctx.submit_candidate, "SUBMIT_ERROR", payload=payload)


def _post_submit_batch(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_submit_batch_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        conflict = ctx.active_auxiliary_operation(exclude="submit", allow_production=True)
        if conflict:
            _kind, message = conflict
            handler._json({"ok": False, "error_code": "CONFLICT_AUX_OP", "error": message}, status=409)
            return
        if ctx.submit_lock.locked():
            handler._json({"ok": False, "error_code": "CONFLICT_RUNNING", "error": "已有提交任务正在运行，请完成后再操作。"}, status=409)
            return
        response, status = ctx.background_job_start_payload(
            ctx.async_jobs,
            payload,
            ctx.start_submit_batch_job,
            conflict_error="active async job",
        )
        handler._json(response, status=status)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "SUBMIT_BATCH_ERROR"), status=400)


def _post_assistant_response_parse(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_assistant_text_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        handler._json(ctx.assistant_response_parse_post_payload(payload, ctx.assistant_response_parse_payload))
    except AssistantResponseParseError as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)


def _post_assistant_response_guidance(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_assistant_text_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        handler._json(ctx.assistant_response_guidance_post_payload(payload, ctx.assistant_response_guidance_payload))
    except AssistantResponseParseError as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_GUIDANCE_ERROR"), status=400)


def _post_assistant_cross_review(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_assistant_cross_review_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        handler._json(ctx.assistant_cross_review_payload(payload))
    except AssistantResponseParseError as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_CROSS_REVIEW_PARSE_ERROR"), status=400)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_CROSS_REVIEW_ERROR"), status=400)


def _post_assistant_guidance(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_assistant_guidance_save_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        handler._json(ctx.save_assistant_guidance_post_payload(payload, ctx.save_assistant_guidance_payload))
    except AssistantResponseParseError as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "ASSISTANT_GUIDANCE_SAVE_ERROR"), status=400)


def _post_logout(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    response, headers = ctx.session_end_payload(handler._session_id_from_cookie(), ctx.expire_session, ctx.expired_session_cookie_header)
    handler._json(response, extra_headers=headers)


def _post_shutdown(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    _post_logout(handler, parsed, ctx)
    ctx.start_shutdown()


def _post_scoring_evaluate(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_alpha_action_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        response, status = ctx.background_job_start_payload(
            ctx.async_jobs,
            payload,
            ctx.start_scoring_evaluate_job,
            conflict_error="active async job",
        )
        handler._json(response, status=status)
    except Exception as exc:
        handler._json(ctx.web_error(exc, "SCORING_ERROR"), status=400)


def _post_scoring_attribution(handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    try:
        payload = handler._read_json()
        validation_error = validate_alpha_action_payload(payload)
        if _reject_invalid_payload(handler, validation_error):
            return
        from brain_alpha_ops.web_redline_scoring import handle_scoring_attribution
        handler._json(handle_scoring_attribution(payload))
    except Exception as exc:
        handler._json(ctx.web_error(exc, "SCORING_ERROR"), status=400)


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
}


_POST_DISPATCH_HANDLERS: dict[str, RouteDispatcher] = {
    "run": _post_run,
    "config": _post_config_save,
    "test_connection": _post_test_connection,
    "stop": _post_stop,
    "sync_alphas": _post_sync_alphas,
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
    "scoring_evaluate": _post_scoring_evaluate,
    "scoring_attribution": _post_scoring_attribution,
}


def _submit_with_lock(
    handler: Any,
    ctx: WebHandlerDispatchContext,
    submitter: Callable[[dict[str, Any]], dict[str, Any]],
    error_code: str,
    *,
    payload: dict[str, Any] | None = None,
) -> None:
    conflict = ctx.active_auxiliary_operation(exclude="submit", allow_production=True)
    if conflict:
        _kind, message = conflict
        handler._json({"ok": False, "error_code": "CONFLICT_AUX_OP", "error": message}, status=409)
        return
    if not ctx.submit_lock.acquire(blocking=False):
        handler._json({"ok": False, "error": "已有提交任务正在运行，请完成后再操作。"}, status=409)
        return
    try:
        payload = handler._read_json() if payload is None else payload
        handler._json(submitter(payload))
    except Exception as exc:
        handler._json(ctx.web_error(exc, error_code), status=400)
    finally:
        ctx.submit_lock.release()

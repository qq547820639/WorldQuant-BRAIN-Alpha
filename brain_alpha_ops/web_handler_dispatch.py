"""GET/POST route dispatch for the local web console handler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs

from brain_alpha_ops.research.assistant import AssistantResponseParseError


@dataclass(frozen=True)
class WebHandlerDispatchContext:
    route_for: Callable[[str, str], Any]
    web_error: Callable[[Exception, str], dict[str, Any]]
    payload_truthy: Callable[[Any], bool]
    bounded_query_int: Callable[[Any, int, int], int]
    bounded_query_float: Callable[[Any, float, float], float]
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
    enrich_progress: Callable[[dict[str, Any]], dict[str, Any]]
    public_run_config: Callable[[], dict[str, Any]]
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
    background_job_start_payload: Callable[..., tuple[dict[str, Any], int]]
    start_run_job: Callable[[str, dict[str, Any]], None]
    stop_job_payload: Callable[..., dict[str, Any]]
    active_auxiliary_operation: Callable[..., tuple[str, str] | None]
    start_sync_job: Callable[[str, dict[str, Any]], None]
    check_candidate: Callable[[dict[str, Any]], dict[str, Any]]
    generate_candidates_payload: Callable[[dict[str, Any]], dict[str, Any]]
    start_check_batch_job: Callable[[str, dict[str, Any]], None]
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


def dispatch_get(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    if not handler._is_allowed_local_request():
        handler._json({"ok": False, "error_code": "ORIGIN_FORBIDDEN", "error": "forbidden local request origin"}, status=403)
        return
    route = ctx.route_for("GET", parsed.path)
    if not route:
        handler._json({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}, status=404)
        return
    if route.requires_session and not handler._has_valid_session(parsed.query):
        handler._json({"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}, status=403)
        return

    if parsed.path == "/":
        session_id, csrf_token = ctx.get_or_create_session(handler._session_id_from_cookie())
        stream_token = ctx.stream_token_for_session(session_id)
        handler._html(ctx.render_html(csrf_token, stream_token), extra_headers=[("Set-Cookie", ctx.session_cookie_header(session_id))])
    elif parsed.path == "/api/status":
        job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
        payload, status = ctx.job_status_payload(ctx.jobs, job_id, ctx.enrich_progress, error="unknown job")
        handler._json(payload, status=status)
    elif parsed.path == "/api/config":
        handler._json({"ok": True, "config": ctx.public_run_config()})
    elif parsed.path == "/api/active_job":
        handler._json(ctx.active_job_payload(ctx.jobs, ctx.enrich_progress))
    elif parsed.path == "/api/latest_result":
        handler._json(ctx.latest_result_snapshot())
    elif parsed.path == "/api/health":
        handler._json(ctx.health_payload())
    elif parsed.path == "/api/stream":
        handler._handle_sse_stream(parsed.query)
    elif parsed.path == "/api/lifecycle":
        job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
        handler._json(ctx.lifecycle_payload(ctx.jobs, job_id, ctx.lifecycle_from_job))
    elif parsed.path == "/api/cloud_alphas":
        handler._json({"ok": True, **ctx.cloud_alpha_snapshot()})
    elif parsed.path == "/api/research_memory":
        query = parse_qs(parsed.query)
        limit = ctx.bounded_query_int((query.get("limit") or ["5000"])[0], 1, 50000)
        top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 50)
        handler._json(ctx.research_memory_snapshot(limit=limit, top_n=top_n))
    elif parsed.path == "/api/research_knowledge":
        query = parse_qs(parsed.query)
        limit = ctx.bounded_query_int((query.get("limit") or ["100"])[0], 1, 10000)
        min_confidence = ctx.bounded_query_float((query.get("min_confidence") or ["0.0"])[0], 0.0, 1.0)
        handler._json(ctx.research_knowledge_snapshot(limit=limit, min_confidence=min_confidence))
    elif parsed.path == "/api/research_observability":
        query = parse_qs(parsed.query)
        limit = ctx.bounded_query_int((query.get("limit") or ["5000"])[0], 1, 50000)
        top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 50)
        include_cloud = ctx.payload_truthy((query.get("include_cloud") or ["true"])[0])
        handler._json(ctx.research_observability_snapshot(limit=limit, top_n=top_n, include_cloud=include_cloud))
    elif parsed.path == "/api/prompt_runs":
        query = parse_qs(parsed.query)
        limit = ctx.bounded_query_int((query.get("limit") or ["100"])[0], 1, 10000)
        handler._json(ctx.prompt_run_ledger_snapshot(limit=limit))
    elif parsed.path == "/api/sqlite_indexes":
        query = parse_qs(parsed.query)
        top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 100)
        handler._json(ctx.sqlite_index_snapshot(top_n=top_n))
    elif parsed.path == "/api/sqlite_expression_lookup":
        query = parse_qs(parsed.query)
        expression = (query.get("expression") or [""])[0]
        top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 100)
        min_similarity = ctx.bounded_query_float((query.get("min_similarity") or ["0.75"])[0], 0.0, 1.0)
        handler._json(ctx.sqlite_expression_lookup_payload(expression=expression, top_n=top_n, min_similarity=min_similarity))
    elif parsed.path == "/api/sqlite_record_lookup":
        query = parse_qs(parsed.query)
        alpha_id = (query.get("alpha_id") or [""])[0]
        limit = ctx.bounded_query_int((query.get("limit") or ["50"])[0], 1, 1000)
        handler._json(ctx.sqlite_record_lookup_payload(alpha_id=alpha_id, limit=limit))
    elif parsed.path == "/api/assistant_context":
        query = parse_qs(parsed.query)
        limit = ctx.bounded_query_int((query.get("limit") or ["5000"])[0], 1, 50000)
        top_n = ctx.bounded_query_int((query.get("top_n") or ["10"])[0], 1, 50)
        include_prompt = ctx.payload_truthy((query.get("include_prompt") or ["true"])[0])
        include_sensitive = ctx.payload_truthy((query.get("include_sensitive") or ["false"])[0])
        handler._json(ctx.assistant_context_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
        ))
    elif parsed.path == "/api/assistant_guidance":
        query = parse_qs(parsed.query)
        limit = ctx.bounded_query_int((query.get("limit") or ["100"])[0], 1, 10000)
        raw_min_confidence = (query.get("min_confidence") or [None])[0]
        min_confidence = None if raw_min_confidence in (None, "") else ctx.bounded_query_float(raw_min_confidence, 0.0, 1.0)
        handler._json(ctx.assistant_guidance_snapshot(limit=limit, min_confidence=min_confidence))
    elif parsed.path == "/api/assistant_request":
        query = parse_qs(parsed.query)
        limit = ctx.bounded_query_int((query.get("limit") or ["5000"])[0], 1, 50000)
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
    elif parsed.path == "/api/anti_overfit":
        query = parse_qs(parsed.query)
        candidate_id = (query.get("candidate_id") or [""])[0]
        handler._json(ctx.anti_overfit_snapshot(candidate_id=candidate_id))
    elif parsed.path == "/api/rolling_validation":
        query = parse_qs(parsed.query)
        candidate_id = (query.get("candidate_id") or [""])[0]
        windows = ctx.bounded_query_int((query.get("windows") or ["4"])[0], 2, 50)
        handler._json(ctx.rolling_validation_snapshot(candidate_id=candidate_id, windows=windows))
    elif parsed.path == "/api/sync_status":
        job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
        payload, status = ctx.job_status_payload(ctx.sync_jobs, job_id, ctx.enrich_progress, error="unknown sync job")
        handler._json(payload, status=status)
    elif parsed.path == "/api/check_status":
        job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
        payload, status = ctx.job_status_payload(ctx.check_jobs, job_id, ctx.enrich_progress, error="unknown check job")
        handler._json(payload, status=status)
    elif parsed.path == "/api/check_results":
        handler._json({"ok": True, **ctx.load_check_results()})
    elif parsed.path == "/api/profile":
        handler._json(ctx.profile_payload(ctx.user_profile_snapshot))
    elif parsed.path == "/api/presets":
        handler._json(ctx.presets_payload(ctx.load_presets))
    else:
        handler._json({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}, status=404)


def dispatch_post(handler: Any, parsed: Any, ctx: WebHandlerDispatchContext) -> None:
    if not handler._is_allowed_local_request():
        handler._json({"ok": False, "error_code": "ORIGIN_FORBIDDEN", "error": "forbidden local request origin"}, status=403)
        return
    route = ctx.route_for("POST", parsed.path)
    if not route:
        handler._json({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}, status=404)
        return
    if route.requires_session and not handler._has_valid_session(parsed.query):
        handler._json({"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}, status=403)
        return

    if parsed.path == "/api/run":
        try:
            payload = handler._read_json()
            if ctx.payload_truthy(payload.get("dry_run")):
                handler._json(ctx.connection_test_post_payload(payload, ctx.test_connection))
                return
            active = ctx.jobs.latest_active()
            if active:
                active_job_id, _job = active
                handler._json({"ok": False, "error_code": "CONFLICT_RUNNING", "error": "已有生产任务正在运行，请先停止当前任务。", "job_id": active_job_id}, status=409)
                return
            response, status = ctx.background_job_start_payload(
                ctx.jobs,
                payload,
                ctx.start_run_job,
                conflict_error="active production job",
            )
            handler._json(response, status=status)
        except Exception as exc:
            handler._json(ctx.web_error(exc, "RUN_ERROR"), status=400)
    elif parsed.path == "/api/test_connection":
        try:
            payload = handler._read_json()
            handler._json(ctx.connection_test_post_payload(payload, ctx.test_connection))
        except Exception as exc:
            handler._json(ctx.web_error(exc, "CONNECTION_ERROR"), status=400)
    elif parsed.path == "/api/stop":
        try:
            payload = handler._read_json()
            handler._json(ctx.stop_job_payload(ctx.jobs, payload))
        except Exception as exc:
            handler._json(ctx.web_error(exc, "STOP_ERROR"), status=400)
    elif parsed.path == "/api/sync_alphas":
        try:
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
            payload = handler._read_json()
            response, status = ctx.background_job_start_payload(
                ctx.sync_jobs,
                payload,
                ctx.start_sync_job,
                conflict_error="active cloud sync job",
            )
            handler._json(response, status=status)
        except Exception as exc:
            handler._json(ctx.web_error(exc, "SYNC_ERROR"), status=400)
    elif parsed.path == "/api/check":
        try:
            conflict = ctx.active_auxiliary_operation(allow_production=True)
            if conflict:
                _kind, message = conflict
                handler._json({"ok": False, "error_code": "CONFLICT_AUX_OP", "error": message}, status=409)
                return
            payload = handler._read_json()
            handler._json(ctx.check_candidate(payload))
        except Exception as exc:
            handler._json(ctx.web_error(exc, "CHECK_ERROR"), status=400)
    elif parsed.path == "/api/generate_candidates":
        try:
            payload = handler._read_json()
            handler._json(ctx.generate_candidates_payload(payload))
        except AssistantResponseParseError as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
        except Exception as exc:
            handler._json(ctx.web_error(exc, "GENERATE_CANDIDATES_ERROR"), status=400)
    elif parsed.path == "/api/check_batch":
        try:
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
            payload = handler._read_json()
            response, status = ctx.background_job_start_payload(
                ctx.check_jobs,
                payload,
                ctx.start_check_batch_job,
                conflict_error="active batch check job",
            )
            handler._json(response, status=status)
        except Exception as exc:
            handler._json(ctx.web_error(exc, "CHECK_BATCH_ERROR"), status=400)
    elif parsed.path == "/api/submit":
        _submit_with_lock(handler, ctx, ctx.submit_candidate, "SUBMIT_ERROR")
    elif parsed.path == "/api/submit_batch":
        _submit_with_lock(handler, ctx, ctx.submit_batch, "SUBMIT_BATCH_ERROR")
    elif parsed.path == "/api/assistant_response/parse":
        try:
            payload = handler._read_json()
            handler._json(ctx.assistant_response_parse_post_payload(payload, ctx.assistant_response_parse_payload))
        except AssistantResponseParseError as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
        except Exception as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
    elif parsed.path == "/api/assistant_response/guidance":
        try:
            payload = handler._read_json()
            handler._json(ctx.assistant_response_guidance_post_payload(payload, ctx.assistant_response_guidance_payload))
        except AssistantResponseParseError as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
        except Exception as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_GUIDANCE_ERROR"), status=400)
    elif parsed.path == "/api/assistant_cross_review":
        try:
            payload = handler._read_json()
            handler._json(ctx.assistant_cross_review_payload(payload))
        except AssistantResponseParseError as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_CROSS_REVIEW_PARSE_ERROR"), status=400)
        except Exception as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_CROSS_REVIEW_ERROR"), status=400)
    elif parsed.path == "/api/assistant_guidance":
        try:
            payload = handler._read_json()
            handler._json(ctx.save_assistant_guidance_post_payload(payload, ctx.save_assistant_guidance_payload))
        except AssistantResponseParseError as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR"), status=400)
        except Exception as exc:
            handler._json(ctx.web_error(exc, "ASSISTANT_GUIDANCE_SAVE_ERROR"), status=400)
    elif parsed.path == "/api/logout":
        response, headers = ctx.session_end_payload(
            handler._session_id_from_cookie(),
            ctx.expire_session,
            ctx.expired_session_cookie_header,
        )
        handler._json(response, extra_headers=headers)
    elif parsed.path == "/api/shutdown":
        response, headers = ctx.session_end_payload(
            handler._session_id_from_cookie(),
            ctx.expire_session,
            ctx.expired_session_cookie_header,
        )
        handler._json(response, extra_headers=headers)
        ctx.start_shutdown()
    else:
        handler._json({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}, status=404)


def _submit_with_lock(
    handler: Any,
    ctx: WebHandlerDispatchContext,
    submitter: Callable[[dict[str, Any]], dict[str, Any]],
    error_code: str,
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
        payload = handler._read_json()
        handler._json(submitter(payload))
    except Exception as exc:
        handler._json(ctx.web_error(exc, error_code), status=400)
    finally:
        ctx.submit_lock.release()

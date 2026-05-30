from __future__ import annotations

import dataclasses
from urllib.parse import urlparse

from brain_alpha_ops.web_handler_dispatch import (
    _GET_DISPATCH_HANDLERS,
    _POST_DISPATCH_HANDLERS,
    WebHandlerDispatchContext,
    dispatch_get,
    dispatch_post,
)
from brain_alpha_ops.web_rate_limit import RateLimitPolicy, RequestRateLimiter
from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for


class _Store:
    def __init__(self):
        self.active = None
        self.rows = {"job_1": {"status": "running", "progress": {"phase": "run"}}}
        self.created = []

    def latest_active(self):
        return self.active

    def get(self, job_id):
        return self.rows.get(job_id)

    def all(self, *, limit=None):
        rows = list(self.rows.items())
        rows = rows[:limit] if limit is not None else rows
        return rows

    def latest_any(self):
        rows = self.all(limit=1)
        return rows[0] if rows else None

    def create(self):
        job_id = f"job_{len(self.created) + 1}"
        self.created.append(job_id)
        return job_id


class _Lock:
    def __init__(self):
        self.acquired = False
        self.released = False

    def acquire(self, *, blocking):
        self.acquired = True
        return True

    def release(self):
        self.released = True

    def locked(self):
        return False


class _Handler:
    def __init__(self, *, body=None, allowed=True, session=True, headers=None, replay=None):
        self.body = {} if body is None else body
        self.allowed = allowed
        self.session = session
        self.headers = headers or {}
        self.replay = replay or {"ok": True}
        self.json_calls = []
        self.html_calls = []
        self.stream_queries = []

    def _is_allowed_local_request(self):
        return self.allowed

    def _has_valid_session(self, query):
        return self.session

    def _validate_replay_request(self):
        return self.replay

    def _session_id_from_cookie(self):
        return "session_1"

    def _html(self, html, *, extra_headers=None):
        self.html_calls.append((html, extra_headers or []))

    def _json(self, payload, status=200, *, extra_headers=None):
        self.json_calls.append((payload, status, extra_headers or []))

    def _read_json(self):
        return dict(self.body) if isinstance(self.body, dict) else self.body

    def _handle_sse_stream(self, query):
        self.stream_queries.append(query)


def _ctx():
    jobs = _Store()
    sync_jobs = _Store()
    check_jobs = _Store()
    async_jobs = _Store()
    started = []
    submit_lock = _Lock()

    def job_status(store, job_id, enrich, error):
        row = store.get(job_id)
        if not row:
            return {"ok": False, "error": error}, 404
        payload = {"ok": True, "job_id": job_id, **row}
        payload["progress"] = enrich(dict(payload["progress"]))
        return payload, 200

    ctx = WebHandlerDispatchContext(
        route_for=route_for,
        web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
        payload_truthy=lambda value: value not in (False, "false", "0", 0, None),
        bounded_query_int=lambda value, low, high: max(low, min(high, int(value))),
        bounded_query_float=lambda value, low, high: max(low, min(high, float(value))),
        remote_admin_required=lambda: False,
        has_valid_admin_token=lambda headers: headers.get("Authorization") == "Bearer admin-token",
        get_or_create_session=lambda existing: ("session_1", "csrf_1"),
        stream_token_for_session=lambda session_id: "stream_1",
        session_cookie_header=lambda session_id: f"cookie={session_id}",
        render_html=lambda csrf, stream: f"html {csrf} {stream}",
        job_status_payload=job_status,
        active_job_payload=lambda store, enrich: {"ok": True, "active": bool(store.latest_active())},
        lifecycle_payload=lambda store, job_id, lifecycle: {"ok": True, "records": lifecycle(store.get(job_id) or {})},
        health_payload=lambda: {"ok": True, "status": "ready"},
        profile_payload=lambda loader: {"ok": True, "profile": loader()},
        presets_payload=lambda loader: {"ok": True, "presets": loader()},
        jobs=jobs,
        sync_jobs=sync_jobs,
        check_jobs=check_jobs,
        async_jobs=async_jobs,
        enrich_progress=lambda progress: {**progress, "enriched": True},
        public_run_config=lambda: {"environment": "production"},
        public_config_schema=lambda: {"schema_version": "test_schema"},
        save_run_config_payload=lambda payload: {"ok": True, "config": {"environment": payload.get("environment", "production")}, "path": "config/run_config.json"},
        rate_limit_request=lambda _key, _method, _path: {"ok": True},
        latest_result_snapshot=lambda: {"ok": True, "source": "latest"},
        lifecycle_from_job=lambda job: [{"stage": "x"}],
        cloud_alpha_snapshot=lambda **kwargs: {"alphas": [], "summary": {"limit": kwargs.get("limit")}},
        research_memory_snapshot=lambda **kwargs: {"ok": True, "memory": kwargs},
        research_knowledge_snapshot=lambda **kwargs: {"ok": True, "knowledge": kwargs},
        research_observability_snapshot=lambda **kwargs: {"ok": True, "observability": kwargs},
        prompt_run_ledger_snapshot=lambda **kwargs: {"ok": True, "prompt_runs": kwargs},
        sqlite_index_snapshot=lambda **kwargs: {"ok": True, "sqlite": kwargs},
        sqlite_expression_lookup_payload=lambda **kwargs: {"ok": True, "expression_lookup": kwargs},
        sqlite_record_lookup_payload=lambda **kwargs: {"ok": True, "record_lookup": kwargs},
        assistant_context_snapshot=lambda **kwargs: {"ok": True, "context": kwargs},
        assistant_guidance_snapshot=lambda **kwargs: {"ok": True, "guidance": kwargs},
        assistant_request_snapshot=lambda **kwargs: {"ok": True, "request": kwargs},
        anti_overfit_snapshot=lambda **kwargs: {"ok": True, "anti": kwargs},
        rolling_validation_snapshot=lambda **kwargs: {"ok": True, "rolling": kwargs},
        load_check_results=lambda: {"items": [], "count": 0},
        user_profile_snapshot=lambda: {"tier": "mock"},
        load_presets=lambda: {"default": {}},
        connection_test_post_payload=lambda payload, handler: handler(payload),
        test_connection=lambda payload: {"ok": True, "dry_run": payload.get("dry_run")},
        validate_run_payload=lambda payload: None,
        background_job_start_payload=lambda store, payload, starter, conflict_error: (
            starter("job_1", payload) or {
                "ok": True,
                "job_id": "job_1",
                "task_id": "job_1",
                "sse_url": "/sse?job_id=job_1",
                "status_url": "/api/status?job_id=job_1",
            },
            200,
        ),
        start_run_job=lambda job_id, payload: started.append(("run", job_id, payload)),
        stop_job_payload=lambda store, payload: {"ok": True, "stopped": payload.get("job_id", "")},
        active_auxiliary_operation=lambda **kwargs: None,
        start_sync_job=lambda job_id, payload: started.append(("sync", job_id, payload)),
        check_candidate=lambda payload: {"ok": True, "checked": payload},
        generate_candidates_payload=lambda payload: {"ok": True, "generated": payload},
        start_generate_candidates_job=lambda job_id, payload: started.append(("generate_candidates", job_id, payload)),
        start_check_batch_job=lambda job_id, payload: started.append(("check_batch", job_id, payload)),
        start_scoring_evaluate_job=lambda job_id, payload: started.append(("scoring_evaluate", job_id, payload)),
        start_submit_batch_job=lambda job_id, payload: started.append(("submit_batch", job_id, payload)),
        submit_lock=submit_lock,
        submit_candidate=lambda payload: {"ok": True, "submitted": payload},
        submit_batch=lambda payload: {"ok": True, "submitted_batch": payload},
        assistant_response_parse_post_payload=lambda payload, handler: handler(payload),
        assistant_response_parse_payload=lambda payload: {"ok": True, "parsed": payload},
        assistant_response_guidance_post_payload=lambda payload, handler: handler(payload),
        assistant_response_guidance_payload=lambda payload: {"ok": True, "guidance": payload},
        assistant_cross_review_payload=lambda payload: {"ok": True, "review": payload},
        save_assistant_guidance_post_payload=lambda payload, handler: handler(payload),
        save_assistant_guidance_payload=lambda payload: {"ok": True, "saved": payload},
        session_end_payload=lambda session_id, expire, expired_header: (expire(session_id) or {"ok": True}, [("Set-Cookie", expired_header())]),
        expire_session=lambda session_id: started.append(("expire", session_id, {})),
        expired_session_cookie_header=lambda: "expired-cookie",
        start_shutdown=lambda: started.append(("shutdown", "", {})),
    )
    return ctx, started, submit_lock


def test_dispatch_get_handles_root_status_and_query_bounds():
    ctx, _started, _lock = _ctx()

    root = _Handler()
    dispatch_get(root, urlparse("/"), ctx)
    assert root.html_calls == [("html csrf_1 stream_1", [("Set-Cookie", "cookie=session_1")])]

    status = _Handler()
    dispatch_get(status, urlparse("/api/status?job_id=job_1"), ctx)
    assert status.json_calls[0][0]["progress"]["enriched"] is True

    config_schema = _Handler()
    dispatch_get(config_schema, urlparse("/api/config_schema"), ctx)
    assert config_schema.json_calls[0][0]["schema"]["schema_version"] == "test_schema"

    memory = _Handler()
    dispatch_get(memory, urlparse("/api/research_memory?limit=3&top_n=2"), ctx)
    assert memory.json_calls[0][0]["memory"] == {"limit": 3, "top_n": 2}

    cloud = _Handler()
    dispatch_get(cloud, urlparse("/api/cloud_alphas?limit=25"), ctx)
    assert cloud.json_calls[0][0]["summary"]["limit"] == 25

    cloud_alias = _Handler()
    dispatch_get(cloud_alias, urlparse("/api/snapshot/cloud?limit=7"), ctx)
    assert cloud_alias.json_calls[0][0]["summary"]["limit"] == 7

    memory_alias = _Handler()
    dispatch_get(memory_alias, urlparse("/api/snapshot/memory?limit=8&top_n=3"), ctx)
    assert memory_alias.json_calls[0][0]["memory"] == {"limit": 8, "top_n": 3}

    ctx.sync_jobs.rows["sync_1"] = {
        "status": "completed",
        "progress": {"phase": "cloud_sync"},
        "result": {"ok": True, "alphas": [{"id": "a1"}], "count": 1},
    }
    sync_status = _Handler()
    dispatch_get(sync_status, urlparse("/api/sync_status?job_id=sync_1&compact=1"), ctx)
    assert "alphas" not in sync_status.json_calls[0][0]["result"]
    assert sync_status.json_calls[0][0]["result"]["alphas_count"] == 1

    knowledge = _Handler()
    dispatch_get(knowledge, urlparse("/api/research_knowledge?limit=4&min_confidence=0.7"), ctx)
    assert knowledge.json_calls[0][0]["knowledge"] == {"limit": 4, "min_confidence": 0.7}

    prompt_runs = _Handler()
    dispatch_get(prompt_runs, urlparse("/api/prompt_runs?limit=6"), ctx)
    assert prompt_runs.json_calls[0][0]["prompt_runs"] == {"limit": 6}


def test_dispatch_get_candidates_falls_back_to_latest_async_generation_result():
    ctx, _started, _lock = _ctx()
    ctx.jobs.rows.clear()
    ctx.async_jobs.rows = {
        "task_0001": {
            "status": "completed",
            "result": {"ok": True, "candidates": [{"alpha_id": "alpha_real_1", "expression": "rank(close)"}]},
            "progress": {"phase": "completed"},
        }
    }

    handler = _Handler()
    dispatch_get(handler, urlparse("/api/candidates?limit=100"), ctx)

    payload = handler.json_calls[0][0]
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["candidates"][0]["alpha_id"] == "alpha_real_1"


def test_dispatch_root_requires_admin_token_when_remote_admin_is_enabled():
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(ctx, remote_admin_required=lambda: True)

    missing = _Handler()
    dispatch_get(missing, urlparse("/"), ctx)
    assert missing.json_calls[0][1] == 401
    assert missing.json_calls[0][0]["error_code"] == "ADMIN_AUTH_REQUIRED"
    assert missing.html_calls == []

    allowed = _Handler(headers={"Authorization": "Bearer admin-token"})
    dispatch_get(allowed, urlparse("/"), ctx)
    assert allowed.html_calls == [("html csrf_1 stream_1", [("Set-Cookie", "cookie=session_1")])]

    sqlite = _Handler()
    dispatch_get(sqlite, urlparse("/api/sqlite_indexes?top_n=7"), ctx)
    assert sqlite.json_calls[0][0]["sqlite"] == {"top_n": 7}

    expression_lookup = _Handler()
    dispatch_get(expression_lookup, urlparse("/api/sqlite_expression_lookup?expression=rank(close)&top_n=3&min_similarity=0.8&max_scan_rows=7"), ctx)
    assert expression_lookup.json_calls[0][0]["expression_lookup"] == {
        "expression": "rank(close)",
        "top_n": 3,
        "min_similarity": 0.8,
        "max_scan_rows": 7,
    }

    record_lookup = _Handler()
    dispatch_get(record_lookup, urlparse("/api/sqlite_record_lookup?alpha_id=a1&limit=4"), ctx)
    assert record_lookup.json_calls[0][0]["record_lookup"] == {"alpha_id": "a1", "limit": 4}

    anti = _Handler()
    dispatch_get(anti, urlparse("/api/anti_overfit?candidate_id=a1"), ctx)
    assert anti.json_calls[0][0]["anti"] == {"candidate_id": "a1"}

    rolling = _Handler()
    dispatch_get(rolling, urlparse("/api/rolling_validation?candidate_id=a1&windows=5"), ctx)
    assert rolling.json_calls[0][0]["rolling"] == {"candidate_id": "a1", "windows": 5}


def test_route_metadata_handlers_are_mapped():
    assert {route.handler for route in GET_ROUTES.values()} <= set(_GET_DISPATCH_HANDLERS)
    assert {route.handler for route in POST_ROUTES.values()} <= set(_POST_DISPATCH_HANDLERS)


def test_dispatch_post_body_routes_reject_non_object_payloads_before_side_effects():
    bodyless_routes = {"/api/logout", "/api/shutdown"}
    assert {path for path, route in POST_ROUTES.items() if route.handler in {"logout", "shutdown"}} == bodyless_routes

    body_validated_routes = sorted(set(POST_ROUTES) - bodyless_routes)
    assert body_validated_routes

    for path in body_validated_routes:
        ctx, started, submit_lock = _ctx()
        handler = _Handler(body=[])

        dispatch_post(handler, urlparse(path), ctx)

        assert handler.json_calls, path
        payload, status, _headers = handler.json_calls[0]
        assert status == 400, path
        assert payload["error_code"] == "VALIDATION_ERROR", path
        assert started == [], path
        assert submit_lock.acquired is False, path


def test_dispatch_post_bodyless_routes_accept_empty_body_as_session_actions():
    for path in ("/api/logout", "/api/shutdown"):
        ctx, started, _lock = _ctx()
        handler = _Handler(body=[])

        dispatch_post(handler, urlparse(path), ctx)

        payload, status, headers = handler.json_calls[0]
        assert status == 200, path
        assert payload["ok"] is True, path
        assert ("Set-Cookie", "expired-cookie") in headers, path
        assert started[0][0] == "expire", path


def test_dispatch_get_clamps_high_cost_history_limits():
    ctx, _started, _lock = _ctx()

    memory = _Handler()
    dispatch_get(memory, urlparse("/api/research_memory?limit=999999"), ctx)
    assert memory.json_calls[0][0]["memory"]["limit"] == 10000

    observability = _Handler()
    dispatch_get(observability, urlparse("/api/research_observability?limit=999999"), ctx)
    assert observability.json_calls[0][0]["observability"]["limit"] == 10000

    context = _Handler()
    dispatch_get(context, urlparse("/api/assistant_context?limit=999999"), ctx)
    assert context.json_calls[0][0]["context"]["limit"] == 10000

    request = _Handler()
    dispatch_get(request, urlparse("/api/assistant_request?limit=999999"), ctx)
    assert request.json_calls[0][0]["request"]["limit"] == 10000

    knowledge = _Handler()
    dispatch_get(knowledge, urlparse("/api/research_knowledge?limit=999999"), ctx)
    assert knowledge.json_calls[0][0]["knowledge"]["limit"] == 5000

    prompt_runs = _Handler()
    dispatch_get(prompt_runs, urlparse("/api/prompt_runs?limit=999999"), ctx)
    assert prompt_runs.json_calls[0][0]["prompt_runs"]["limit"] == 5000

    guidance = _Handler()
    dispatch_get(guidance, urlparse("/api/assistant_guidance?limit=999999"), ctx)
    assert guidance.json_calls[0][0]["guidance"]["limit"] == 5000

    record_lookup = _Handler()
    dispatch_get(record_lookup, urlparse("/api/sqlite_record_lookup?alpha_id=a1&limit=999999"), ctx)
    assert record_lookup.json_calls[0][0]["record_lookup"]["limit"] == 500


def test_dispatch_get_blocks_origin_missing_route_and_session():
    ctx, _started, _lock = _ctx()

    blocked = _Handler(allowed=False)
    dispatch_get(blocked, urlparse("/api/health"), ctx)
    assert blocked.json_calls[0][1] == 403
    assert blocked.json_calls[0][0]["error_code"] == "ORIGIN_FORBIDDEN"

    missing = _Handler()
    dispatch_get(missing, urlparse("/missing"), ctx)
    assert missing.json_calls[0][1] == 404

    bad_session = _Handler(session=False)
    dispatch_get(bad_session, urlparse("/api/config"), ctx)
    assert bad_session.json_calls[0][0]["error_code"] == "SESSION_INVALID"


def test_dispatch_post_starts_jobs_and_handles_submit_lock():
    ctx, started, submit_lock = _ctx()

    run = _Handler(body={"alpha": 1})
    dispatch_post(run, urlparse("/api/run"), ctx)
    assert run.json_calls[0][0] == {
        "ok": True,
        "job_id": "job_1",
        "task_id": "job_1",
        "sse_url": "/sse?job_id=job_1",
        "status_url": "/api/status?job_id=job_1",
    }
    assert started[0] == ("run", "job_1", {"alpha": 1})

    submit = _Handler(body={"alpha_id": "a1"})
    dispatch_post(submit, urlparse("/api/submit"), ctx)
    assert submit.json_calls[0][0]["submitted"] == {"alpha_id": "a1"}
    assert submit_lock.acquired is True
    assert submit_lock.released is True

    review = _Handler(body={"request_pack": {}, "primary_response": "{}"})
    dispatch_post(review, urlparse("/api/assistant_cross_review"), ctx)
    assert review.json_calls[0][0]["review"] == {"request_pack": {}, "primary_response": "{}"}


def test_dispatch_post_saves_config_payload():
    ctx, _started, _lock = _ctx()

    config = _Handler(body={"environment": "production", "settings": {"region": "USA"}})
    dispatch_post(config, urlparse("/api/config"), ctx)

    payload, status, _headers = config.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["config"]["environment"] == "production"
    assert payload["path"] == "config/run_config.json"


def test_dispatch_post_starts_async_operation_jobs():
    ctx, started, _lock = _ctx()

    generate = _Handler(body={"count": 3})
    dispatch_post(generate, urlparse("/api/generate_candidates"), ctx)
    assert generate.json_calls[0][0]["task_id"] == "job_1"
    assert started[-1] == ("generate_candidates", "job_1", {"count": 3})

    scoring = _Handler(body={"candidate": {"alpha_id": "a1"}})
    dispatch_post(scoring, urlparse("/api/scoring/evaluate"), ctx)
    assert scoring.json_calls[0][0]["sse_url"] == "/sse?job_id=job_1"
    assert started[-1] == ("scoring_evaluate", "job_1", {"candidate": {"alpha_id": "a1"}})

    submit_batch = _Handler(body={"alpha_ids": ["a1"]})
    dispatch_post(submit_batch, urlparse("/api/submit_batch"), ctx)
    assert submit_batch.json_calls[0][0]["status_url"] == "/api/status?job_id=job_1"
    assert started[-1] == ("submit_batch", "job_1", {"alpha_ids": ["a1"]})


def test_dispatch_post_check_batch_validates_candidate_ids_before_starting_job():
    ctx, started, _lock = _ctx()

    check_batch = _Handler(body={"candidate_ids": "not-a-list"})
    dispatch_post(check_batch, urlparse("/api/check_batch"), ctx)

    assert check_batch.json_calls[0][1] == 400
    assert check_batch.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert "candidate_ids" in check_batch.json_calls[0][0]["error"]
    assert started == []

    check_candidates = _Handler(body={"check_candidates": {}})
    dispatch_post(check_candidates, urlparse("/api/check_batch"), ctx)
    assert check_candidates.json_calls[0][1] == 400
    assert check_candidates.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert "check_candidates" in check_candidates.json_calls[0][0]["error"]
    assert started == []


def test_dispatch_post_validates_alpha_id_payloads_before_handlers():
    ctx, started, submit_lock = _ctx()

    check = _Handler(body={"alpha_id": "bad id!"})
    dispatch_post(check, urlparse("/api/check"), ctx)
    assert check.json_calls[0][1] == 400
    assert check.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert "alpha_id" in check.json_calls[0][0]["error"]

    submit = _Handler(body={"alpha_id": "bad id!"})
    dispatch_post(submit, urlparse("/api/submit"), ctx)
    assert submit.json_calls[0][1] == 400
    assert submit.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert submit_lock.acquired is False

    scoring = _Handler(body={})
    dispatch_post(scoring, urlparse("/api/scoring/evaluate"), ctx)
    assert scoring.json_calls[0][1] == 400
    assert scoring.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert "candidate or alpha_id" in scoring.json_calls[0][0]["error"]
    assert started == []


def test_dispatch_post_validates_batch_and_generate_payloads_before_starting_jobs():
    ctx, started, _lock = _ctx()

    submit_batch = _Handler(body={"alpha_ids": ["good_1", "bad id!"]})
    dispatch_post(submit_batch, urlparse("/api/submit_batch"), ctx)
    assert submit_batch.json_calls[0][1] == 400
    assert submit_batch.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert "alpha_ids[]" in submit_batch.json_calls[0][0]["error"]

    generate = _Handler(body={"count": 101})
    dispatch_post(generate, urlparse("/api/generate_candidates"), ctx)
    assert generate.json_calls[0][1] == 400
    assert generate.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert "between 1 and 100" in generate.json_calls[0][0]["error"]
    assert started == []


def test_dispatch_post_validates_generic_json_object_payloads_before_handlers():
    ctx, started, _lock = _ctx()

    run = _Handler(body=[])
    dispatch_post(run, urlparse("/api/run"), ctx)
    assert run.json_calls[0][1] == 400
    assert run.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"

    connection = _Handler(body=[])
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)
    assert connection.json_calls[0][1] == 400
    assert connection.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"

    config = _Handler(body=[])
    dispatch_post(config, urlparse("/api/config"), ctx)
    assert config.json_calls[0][1] == 400
    assert config.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"

    sync = _Handler(body=[])
    dispatch_post(sync, urlparse("/api/sync_alphas"), ctx)
    assert sync.json_calls[0][1] == 400
    assert sync.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"

    sync_range = _Handler(body={"syncRange": "30d"})
    dispatch_post(sync_range, urlparse("/api/sync_alphas"), ctx)
    assert sync_range.json_calls[0][1] == 400
    assert "syncRange" in sync_range.json_calls[0][0]["error"]
    assert started == []


def test_dispatch_post_validates_cancel_and_assistant_payload_shapes():
    ctx, started, _lock = _ctx()

    stop = _Handler(body={"job_id": "bad id!"})
    dispatch_post(stop, urlparse("/api/stop"), ctx)
    assert stop.json_calls[0][1] == 400
    assert stop.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert "job_id" in stop.json_calls[0][0]["error"]

    sync_cancel = _Handler(body={})
    dispatch_post(sync_cancel, urlparse("/api/sync_cancel"), ctx)
    assert sync_cancel.json_calls[0][1] == 400
    assert sync_cancel.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"

    parse = _Handler(body={"text": "   "})
    dispatch_post(parse, urlparse("/api/assistant_response/parse"), ctx)
    assert parse.json_calls[0][1] == 400
    assert parse.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"

    guidance_save = _Handler(body={})
    dispatch_post(guidance_save, urlparse("/api/assistant_guidance"), ctx)
    assert guidance_save.json_calls[0][1] == 400
    assert guidance_save.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"

    review = _Handler(body={"request_pack": [], "primary_response": "{}"})
    dispatch_post(review, urlparse("/api/assistant_cross_review"), ctx)
    assert review.json_calls[0][1] == 400
    assert "request_pack" in review.json_calls[0][0]["error"]
    assert started == []


def test_dispatch_post_validates_scoring_attribution_payload_before_handler():
    ctx, started, _lock = _ctx()

    attribution = _Handler(body={"candidate": []})
    dispatch_post(attribution, urlparse("/api/scoring/attribution"), ctx)

    assert attribution.json_calls[0][1] == 400
    assert attribution.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"
    assert "candidate" in attribution.json_calls[0][0]["error"]
    assert started == []


def test_dispatch_post_requires_valid_replay_headers():
    ctx, started, _lock = _ctx()

    missing = _Handler(body={"alpha": 1}, replay={"ok": False, "error_code": "REPLAY_TOKEN_REQUIRED", "error": "missing request id"})
    dispatch_post(missing, urlparse("/api/run"), ctx)
    assert missing.json_calls[0][1] == 400
    assert missing.json_calls[0][0]["error_code"] == "REPLAY_TOKEN_REQUIRED"
    assert started == []

    duplicate = _Handler(body={"alpha": 1}, replay={"ok": False, "error_code": "REPLAY_DETECTED", "error": "duplicate request id"})
    dispatch_post(duplicate, urlparse("/api/run"), ctx)
    assert duplicate.json_calls[0][1] == 409
    assert duplicate.json_calls[0][0]["error_code"] == "REPLAY_DETECTED"


def test_dispatch_blocks_api_requests_when_rate_limited():
    ctx, started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        rate_limit_request=lambda _key, _method, _path: {
            "ok": False,
            "error_code": "RATE_LIMITED",
            "error": "too many requests; retry later",
            "retry_after": 7,
        },
    )

    run = _Handler(body={"alpha": 1})
    dispatch_post(run, urlparse("/api/run"), ctx)

    payload, status, headers = run.json_calls[0]
    assert status == 429
    assert payload["error_code"] == "RATE_LIMITED"
    assert ("Retry-After", "7") in headers
    assert started == []


def test_dispatch_rate_limiter_throttles_repeated_writes_and_recovers_after_window():
    ctx, started, _lock = _ctx()
    limiter = RequestRateLimiter(RateLimitPolicy(window_seconds=10, read_requests=99, write_requests=1, submit_requests=1))
    now = [100.0]
    ctx = dataclasses.replace(
        ctx,
        rate_limit_request=lambda key, method, path: limiter.check(key=key, method=method, path=path, now=now[0]),
    )

    first = _Handler(body={"alpha": 1})
    dispatch_post(first, urlparse("/api/run"), ctx)
    assert first.json_calls[0][1] == 200
    assert len(started) == 1

    now[0] = 101.0
    second = _Handler(body={"alpha": 2})
    dispatch_post(second, urlparse("/api/run"), ctx)
    payload, status, headers = second.json_calls[0]
    assert status == 429
    assert payload["error_code"] == "RATE_LIMITED"
    assert ("Retry-After", "9") in headers
    assert len(started) == 1

    now[0] = 111.0
    third = _Handler(body={"alpha": 3})
    dispatch_post(third, urlparse("/api/run"), ctx)
    assert third.json_calls[0][1] == 200
    assert len(started) == 2


def test_dispatch_post_can_cancel_sync_job():
    ctx, _started, _lock = _ctx()

    cancel = _Handler(body={"job_id": "sync_1"})
    dispatch_post(cancel, urlparse("/api/sync_cancel"), ctx)

    payload, status, _headers = cancel.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["job_id"] == "sync_1"
    assert payload["status"] == "stopping"
    assert "云端同步" in payload["message"]


def test_dispatch_post_run_validates_before_starting_job():
    ctx, started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        validate_run_payload=lambda _payload: (_ for _ in ()).throw(ValueError("settings.decay must be >= 0")),
    )

    run = _Handler(body={"settings": {"decay": -1}})
    dispatch_post(run, urlparse("/api/run"), ctx)

    assert run.json_calls[0][1] == 400
    assert run.json_calls[0][0]["error_code"] == "RUN_ERROR"
    assert "settings.decay" in run.json_calls[0][0]["error"]
    assert started == []


def test_dispatch_post_logout_and_shutdown_expire_session():
    ctx, started, _lock = _ctx()

    logout = _Handler()
    dispatch_post(logout, urlparse("/api/logout"), ctx)
    assert logout.json_calls[0] == ({"ok": True}, 200, [("Set-Cookie", "expired-cookie")])
    assert started[-1][0] == "expire"

    shutdown = _Handler()
    dispatch_post(shutdown, urlparse("/api/shutdown"), ctx)
    assert started[-1][0] == "shutdown"


def test_dispatch_get_wraps_route_exceptions_as_json_errors():
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        route_for=lambda _method, _path: type("Route", (), {"handler": "broken", "requires_session": False})(),
    )
    handlers = dict(_GET_DISPATCH_HANDLERS)
    handlers["broken"] = lambda _handler, _parsed, _ctx: (_ for _ in ()).throw(RuntimeError("boom"))

    handler = _Handler()
    from brain_alpha_ops import web_handler_dispatch as dispatch_mod

    original = dispatch_mod._GET_DISPATCH_HANDLERS
    dispatch_mod._GET_DISPATCH_HANDLERS = handlers
    try:
        dispatch_get(handler, urlparse("/api/health"), ctx)
    finally:
        dispatch_mod._GET_DISPATCH_HANDLERS = original

    assert handler.json_calls[-1][1] == 500
    assert handler.json_calls[-1][0]["error_code"] == "GET_ROUTE_ERROR"


def test_dispatch_post_wraps_route_exceptions_as_json_errors():
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        route_for=lambda _method, _path: type("Route", (), {"handler": "broken", "requires_session": False})(),
    )
    handlers = dict(_POST_DISPATCH_HANDLERS)
    handlers["broken"] = lambda _handler, _parsed, _ctx: (_ for _ in ()).throw(RuntimeError("boom"))

    handler = _Handler()
    from brain_alpha_ops import web_handler_dispatch as dispatch_mod

    original = dispatch_mod._POST_DISPATCH_HANDLERS
    dispatch_mod._POST_DISPATCH_HANDLERS = handlers
    try:
        dispatch_post(handler, urlparse("/api/run"), ctx)
    finally:
        dispatch_mod._POST_DISPATCH_HANDLERS = original

    assert handler.json_calls[-1][1] == 500
    assert handler.json_calls[-1][0]["error_code"] == "POST_ROUTE_ERROR"

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlparse

from brain_alpha_ops.web_handler_dispatch import WebHandlerDispatchContext, dispatch_get, dispatch_post
from brain_alpha_ops.web_routes import route_for


class _Store:
    def __init__(self):
        self.active = None
        self.rows = {"job_1": {"status": "running", "progress": {"phase": "run"}}}
        self.created = []

    def latest_active(self):
        return self.active

    def get(self, job_id):
        return self.rows.get(job_id)

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


class _Handler:
    def __init__(self, *, body=None, allowed=True, session=True):
        self.body = body or {}
        self.allowed = allowed
        self.session = session
        self.json_calls = []
        self.html_calls = []
        self.stream_queries = []

    def _is_allowed_local_request(self):
        return self.allowed

    def _has_valid_session(self, query):
        return self.session

    def _session_id_from_cookie(self):
        return "session_1"

    def _html(self, html, *, extra_headers=None):
        self.html_calls.append((html, extra_headers or []))

    def _json(self, payload, status=200, *, extra_headers=None):
        self.json_calls.append((payload, status, extra_headers or []))

    def _read_json(self):
        return dict(self.body)

    def _handle_sse_stream(self, query):
        self.stream_queries.append(query)


def _ctx():
    jobs = _Store()
    sync_jobs = _Store()
    check_jobs = _Store()
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
        enrich_progress=lambda progress: {**progress, "enriched": True},
        public_run_config=lambda: {"environment": "mock"},
        latest_result_snapshot=lambda: {"ok": True, "source": "latest"},
        lifecycle_from_job=lambda job: [{"stage": "x"}],
        cloud_alpha_snapshot=lambda: {"alphas": [], "summary": {}},
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
        background_job_start_payload=lambda store, payload, starter, conflict_error: (starter("job_1", payload) or {"ok": True, "job_id": "job_1"}, 200),
        start_run_job=lambda job_id, payload: started.append(("run", job_id, payload)),
        stop_job_payload=lambda store, payload: {"ok": True, "stopped": payload.get("job_id", "")},
        active_auxiliary_operation=lambda **kwargs: None,
        start_sync_job=lambda job_id, payload: started.append(("sync", job_id, payload)),
        check_candidate=lambda payload: {"ok": True, "checked": payload},
        generate_candidates_payload=lambda payload: {"ok": True, "generated": payload},
        start_check_batch_job=lambda job_id, payload: started.append(("check_batch", job_id, payload)),
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

    memory = _Handler()
    dispatch_get(memory, urlparse("/api/research_memory?limit=3&top_n=2"), ctx)
    assert memory.json_calls[0][0]["memory"] == {"limit": 3, "top_n": 2}

    knowledge = _Handler()
    dispatch_get(knowledge, urlparse("/api/research_knowledge?limit=4&min_confidence=0.7"), ctx)
    assert knowledge.json_calls[0][0]["knowledge"] == {"limit": 4, "min_confidence": 0.7}

    prompt_runs = _Handler()
    dispatch_get(prompt_runs, urlparse("/api/prompt_runs?limit=6"), ctx)
    assert prompt_runs.json_calls[0][0]["prompt_runs"] == {"limit": 6}

    sqlite = _Handler()
    dispatch_get(sqlite, urlparse("/api/sqlite_indexes?top_n=7"), ctx)
    assert sqlite.json_calls[0][0]["sqlite"] == {"top_n": 7}

    expression_lookup = _Handler()
    dispatch_get(expression_lookup, urlparse("/api/sqlite_expression_lookup?expression=rank(close)&top_n=3&min_similarity=0.8"), ctx)
    assert expression_lookup.json_calls[0][0]["expression_lookup"] == {"expression": "rank(close)", "top_n": 3, "min_similarity": 0.8}

    record_lookup = _Handler()
    dispatch_get(record_lookup, urlparse("/api/sqlite_record_lookup?alpha_id=a1&limit=4"), ctx)
    assert record_lookup.json_calls[0][0]["record_lookup"] == {"alpha_id": "a1", "limit": 4}

    anti = _Handler()
    dispatch_get(anti, urlparse("/api/anti_overfit?candidate_id=a1"), ctx)
    assert anti.json_calls[0][0]["anti"] == {"candidate_id": "a1"}

    rolling = _Handler()
    dispatch_get(rolling, urlparse("/api/rolling_validation?candidate_id=a1&windows=5"), ctx)
    assert rolling.json_calls[0][0]["rolling"] == {"candidate_id": "a1", "windows": 5}


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
    assert run.json_calls[0][0] == {"ok": True, "job_id": "job_1"}
    assert started[0] == ("run", "job_1", {"alpha": 1})

    submit = _Handler(body={"alpha_id": "a1"})
    dispatch_post(submit, urlparse("/api/submit"), ctx)
    assert submit.json_calls[0][0]["submitted"] == {"alpha_id": "a1"}
    assert submit_lock.acquired is True
    assert submit_lock.released is True

    review = _Handler(body={"request_pack": {}, "primary_response": "{}"})
    dispatch_post(review, urlparse("/api/assistant_cross_review"), ctx)
    assert review.json_calls[0][0]["review"] == {"request_pack": {}, "primary_response": "{}"}


def test_dispatch_post_logout_and_shutdown_expire_session():
    ctx, started, _lock = _ctx()

    logout = _Handler()
    dispatch_post(logout, urlparse("/api/logout"), ctx)
    assert logout.json_calls[0] == ({"ok": True}, 200, [("Set-Cookie", "expired-cookie")])
    assert started[-1][0] == "expire"

    shutdown = _Handler()
    dispatch_post(shutdown, urlparse("/api/shutdown"), ctx)
    assert started[-1][0] == "shutdown"

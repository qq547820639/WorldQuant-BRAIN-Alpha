from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import dataclasses
import json
import logging
import threading
from types import SimpleNamespace
from urllib.parse import urlparse

# Phase 3.3: Activate _WebBridgeFinder before importing bridged flat-module aliases
import brain_alpha_ops.web  # noqa: F401 — side-effect: installs sys.meta_path bridge

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.tasks import JobStore
from brain_alpha_ops.web_handler_dispatch import (
    _GET_DISPATCH_HANDLERS,
    _POST_DISPATCH_HANDLERS,
    _rate_limit_key,
    WebHandlerDispatchContext,
    dispatch_get,
    dispatch_post,
)
from brain_alpha_ops.web_get_handlers import active_job_payload
from brain_alpha_ops.web_rate_limit import RateLimitPolicy, RequestRateLimiter
from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class _Store:
    def __init__(self):
        self.active = None
        self.rows = {"job_1": {"status": "running", "progress": {"phase": "run"}}}
        self.jobs = self.rows
        self.created = []
        self.cancelled = []

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

    def create(self, initial=None):
        job_id = f"job_{len(self.created) + 1}"
        self.created.append(job_id)
        if isinstance(initial, dict):
            self.rows[job_id] = dict(initial)
        return job_id

    def cancel(self, job_id):
        if job_id not in self.rows:
            return False
        self.cancelled.append(job_id)
        self.rows[job_id]["cancel"] = True
        self.rows[job_id]["status"] = "stopping"
        return True


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
        # Note: P0-2 introduced a human-in-the-loop ``confirm_simulation``
        # gate on ``/api/candidates/simulate``.  Tests that exercise that
        # path add ``"confirm_simulation": True`` to their body explicitly.
        # Tests for other endpoints (``/run``, ``/check``, ``/test_connection``
        # etc.) must NOT see this field leaked into the captured payload,
        # so the helper does not default the field.
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
    session_credentials: dict[str, dict[str, str]] = {}

    def job_status(store, job_id, enrich, error):
        row = store.get(job_id)
        if not row:
            return {"ok": False, "error": error}, 404
        payload = {"ok": True, "job_id": job_id, **row}
        payload["progress"] = enrich(dict(payload["progress"]))
        return payload, 200

    def mark_connection(session_id, result, payload):
        if payload.get("username") and payload.get("password"):
            session_credentials[str(session_id)] = {
                "username": str(payload["username"]),
                "password": str(payload["password"]),
            }
        elif payload.get("token"):
            session_credentials[str(session_id)] = {"token": str(payload["token"])}
        return {
            "ok": True,
            "authenticated": bool(session_id),
            "connected": True,
            "brain_connection_verified": True,
            "credential_source": "page" if payload.get("username") or payload.get("password") or payload.get("token") else "managed",
            "session_credentials_available": bool(session_credentials.get(str(session_id))),
            "environment": result.get("environment", "production"),
            "auth_mode": result.get("auth", ""),
            "ttl_seconds": 43200,
        }

    def clear_connection(session_id):
        session_credentials.pop(str(session_id), None)
        return {
            "ok": True,
            "authenticated": bool(session_id),
            "connected": False,
            "brain_connection_verified": False,
            "credential_source": "none",
            "session_credentials_available": False,
            "ttl_seconds": 43200,
        }

    def payload_with_session_credentials(session_id, payload):
        merged = dict(payload or {})
        if any(str(merged.get(key) or "").strip() for key in ("username", "password", "token")):
            return merged
        merged.update(session_credentials.get(str(session_id), {}))
        return merged

    def expire_session(session_id):
        session_credentials.pop(str(session_id), None)
        started.append(("expire", session_id, {}))

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
        session_status=lambda session_id: {
            "ok": True,
            "authenticated": bool(session_id),
            "connected": False,
            "brain_connection_verified": False,
            "credential_source": "none",
            "session_credentials_available": bool(session_credentials.get(str(session_id))),
            "ttl_seconds": 43200,
        },
        mark_brain_connection_verified=mark_connection,
        clear_brain_connection_verified=clear_connection,
        payload_with_brain_session_credentials=payload_with_session_credentials,
        render_html=lambda csrf, stream: f"html {csrf} {stream}",
        job_status_payload=job_status,
        active_job_payload=active_job_payload,
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
        alpha_lifecycle_history=lambda **kwargs: {"ok": True, "alpha_lifecycle": kwargs},
        cloud_alpha_snapshot=lambda **kwargs: {"alphas": [], "summary": {"limit": kwargs.get("limit")}},
        official_context_file_counts=lambda: {
            "fields_count": 12,
            "operators_count": 7,
            "datasets_count": 3,
            "context_cache_manifest": {
                "complete": True,
                "is_stale": False,
                "record_counts": {
                    "official_fields.json": 12,
                    "official_operators.json": 7,
                    "official_datasets.json": 3,
                },
            },
        },
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
        candidate_summary_probe=lambda: None,
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
                "status_url": "/api/production-validation/status?job_id=job_1",
            },
            200,
        ),
        start_run_job=lambda job_id, payload: started.append(("run", job_id, payload)),
        stop_job_payload=lambda store, payload: {"ok": store.cancel(payload.get("job_id", "")), "stopped": payload.get("job_id", "")},
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
        expire_session=expire_session,
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

    capabilities = _Handler()
    dispatch_get(capabilities, urlparse("/api/capabilities"), ctx)
    assert capabilities.json_calls[0][0]["schema_version"] == "brain_capability_registry.v1"
    assert capabilities.json_calls[0][0]["official_api_called"] is False

    memory = _Handler()
    dispatch_get(memory, urlparse("/api/research_memory?limit=3&top_n=2"), ctx)
    assert memory.json_calls[0][0]["memory"] == {"limit": 3, "top_n": 2}

    cloud = _Handler()
    dispatch_get(cloud, urlparse("/api/cloud_alphas"), ctx)
    assert cloud.json_calls[0][0]["summary"]["limit"] is None

    cloud_alias = _Handler()
    dispatch_get(cloud_alias, urlparse("/api/snapshot/cloud"), ctx)
    assert cloud_alias.json_calls[0][0]["summary"]["limit"] is None

    alpha_lifecycle = _Handler()
    dispatch_get(alpha_lifecycle, urlparse("/api/alpha_lifecycle?alpha_id=a1&query=official&stage=simulation&status=FAILED&status_category=failed&limit=2"), ctx)
    assert alpha_lifecycle.json_calls[0][0]["alpha_lifecycle"] == {
        "alpha_id": "a1",
        "query": "official",
        "stage": "simulation",
        "status": "FAILED",
        "status_category_filter": "failed",
        "limit": 2,
    }

    lifecycle_history_alias = _Handler()
    dispatch_get(lifecycle_history_alias, urlparse("/api/lifecycle/history?alpha_id=a2&limit=999999"), ctx)
    assert lifecycle_history_alias.json_calls[0][0]["alpha_lifecycle"] == {
        "alpha_id": "a2",
        "query": "",
        "stage": "",
        "status": "",
        "status_category_filter": "",
        "limit": 2000,
    }


def test_dispatch_get_status_without_job_id_recovers_active_async_job():
    ctx, _started, _lock = _ctx()
    ctx.async_jobs.active = ("task_async_1", {"status": "running", "progress": {"phase": "candidate_generation"}})

    status = _Handler()
    dispatch_get(status, urlparse("/api/status"), ctx)

    payload = status.json_calls[0][0]
    assert payload["ok"] is True
    assert payload["job_id"] == "task_async_1"
    assert payload["task_id"] == "task_async_1"
    assert payload["job_type"] == "async"
    assert payload["progress"]["phase"] == "candidate_generation"
    assert payload["status_kind"] == "active"
    assert payload["terminal"] is False
    assert payload["recoverable"] is True
    assert payload["next_action"] == "monitor_or_cancel"


def test_dispatch_get_active_job_recovers_active_check_job():
    ctx, _started, _lock = _ctx()
    ctx.check_jobs.active = ("check_active_1", {"status": "running", "progress": {"phase": "checking"}})

    status = _Handler()
    dispatch_get(status, urlparse("/api/active_job"), ctx)

    payload = status.json_calls[0][0]
    assert payload["ok"] is True
    assert payload["job_id"] == "check_active_1"
    assert payload["job_type"] == "check"
    assert payload["progress"]["phase"] == "checking"
    assert payload["status_kind"] == "active"
    assert payload["terminal"] is False


def test_dispatch_get_missing_exact_job_returns_actionable_not_found():
    ctx, _started, _lock = _ctx()

    status = _Handler()
    dispatch_get(status, urlparse("/api/status?job_id=unknown_task"), ctx)

    payload, http_status, _headers = status.json_calls[0]
    assert http_status == 404
    assert payload["ok"] is False
    assert payload["error_code"] == "JOB_NOT_FOUND"
    assert payload["user_error_kind"] == "job_not_found"
    assert payload["user_error"]["suggested_action"]
    assert payload["next_action"] == "restart_flow"


def test_dispatch_get_sse_blocks_invalid_session_before_stream_delegation():
    ctx, _started, _lock = _ctx()

    stream = _Handler(session=False)
    dispatch_get(stream, urlparse("/sse?job_id=job_1"), ctx)

    assert stream.stream_queries == []
    assert stream.json_calls[0][0]["error_code"] == "SESSION_INVALID"
    assert stream.json_calls[0][0]["user_error_kind"] == "session_expired"
    assert stream.json_calls[0][1] == 403

    memory_alias = _Handler()
    dispatch_get(memory_alias, urlparse("/api/snapshot/memory?limit=8&top_n=3"), ctx)
    assert memory_alias.json_calls[0][0]["memory"] == {"limit": 8, "top_n": 3}

    idle_sync_status = _Handler()
    dispatch_get(idle_sync_status, urlparse("/api/sync_status?compact=1"), ctx)
    assert idle_sync_status.json_calls[0][0]["status"] == "idle"
    assert idle_sync_status.json_calls[0][0]["official_context_cache"]["fields_count"] == 12

    ctx.sync_jobs.rows["sync_1"] = {
        "status": "completed",
        "progress": {"phase": "cloud_sync"},
        "result": {"ok": True, "alphas": [{"id": "a1"}], "count": 1},
    }
    sync_status = _Handler()
    dispatch_get(sync_status, urlparse("/api/sync_status?job_id=sync_1&compact=1"), ctx)
    assert "alphas" not in sync_status.json_calls[0][0]["result"]
    assert sync_status.json_calls[0][0]["result"]["alphas_count"] == 1
    assert sync_status.json_calls[0][0]["official_context_cache"] == {
        "ok": True,
        "fields_count": 12,
        "operators_count": 7,
        "datasets_count": 3,
        "manifest": {
            "complete": True,
            "is_stale": False,
            "missing_files": [],
            "stale_files": [],
            "invalid_files": [],
            "record_counts": {
                "official_fields.json": 12,
                "official_operators.json": 7,
                "official_datasets.json": 3,
            },
        },
    }

    ctx.sync_jobs.active = ("sync_active", {
        "status": "running",
        "progress": {"phase": "cloud_sync", "scanned": 25},
    })
    active_sync_status = _Handler()
    dispatch_get(active_sync_status, urlparse("/api/sync_status?compact=1"), ctx)
    active_payload = active_sync_status.json_calls[0][0]
    assert active_payload["ok"] is True
    assert active_payload["job_id"] == "sync_active"
    assert active_payload["task_id"] == "sync_active"
    assert active_payload["status"] == "running"
    assert active_payload["progress"]["enriched"] is True

    knowledge = _Handler()
    dispatch_get(knowledge, urlparse("/api/research_knowledge?limit=4&min_confidence=0.7"), ctx)
    assert knowledge.json_calls[0][0]["knowledge"] == {"limit": 4, "min_confidence": 0.7}

    prompt_runs = _Handler()
    dispatch_get(prompt_runs, urlparse("/api/prompt_runs?limit=6"), ctx)
    assert prompt_runs.json_calls[0][0]["prompt_runs"] == {"limit": 6}


def test_sync_status_includes_redacted_recent_sync_history():
    ctx, _started, _lock = _ctx()
    ctx.sync_jobs.rows.clear()
    ctx.sync_jobs.rows["sync_done"] = {
        "status": "completed",
        "updated_at": 1_717_777_777.0,
        "progress": {
            "phase": "completed",
            "status_message": "云端同步完成",
            "scanned": 10,
            "api_reported_total": 12,
        },
        "result": {"updated": 2, "skipped": 7, "failed": 0},
        "payload": {"username": "secret@example.com", "password": "super-secret"},
    }
    ctx.sync_jobs.rows["sync_context"] = {
        "status": "completed_with_warnings",
        "updated_at": 1_717_777_700.0,
        "progress": {"phase": "context", "context_only": True, "status_message": "Official context refreshed."},
        "result": {"context_only": True, "fields_count": 12},
        "payload": {"token": "secret-token"},
    }

    handler = _Handler()
    dispatch_get(handler, urlparse("/api/sync_status?compact=1&history_limit=2"), ctx)
    payload = handler.json_calls[0][0]

    assert payload["ok"] is True
    history = payload["sync_history"]
    assert len(history) == 2
    assert history[0] == {
        "job_id": "sync_done",
        "task_id": "sync_done",
        "status": "completed",
        "phase": "completed",
        "status_message": "云端同步完成",
        "updated_at": 1_717_777_777.0,
        "updated_at_ms": 1_717_777_777_000,
        "context_only": False,
        "scanned": 10,
        "total": 0,
        "api_reported_total": 12,
        "filter_window_count": 0,
        "added": 0,
        "updated": 2,
        "skipped": 7,
        "failed": 0,
    }
    assert history[1]["job_id"] == "sync_context"
    assert history[1]["context_only"] is True
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "payload" not in encoded
    assert "secret@example.com" not in encoded
    assert "super-secret" not in encoded
    assert "secret-token" not in encoded


def test_dispatch_get_logs_handler_exceptions(monkeypatch, caplog):
    ctx, _started, _lock = _ctx()

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setitem(_GET_DISPATCH_HANDLERS, "boom", boom)
    ctx = dataclasses.replace(
        ctx,
        route_for=lambda _method, _path: SimpleNamespace(handler="boom", requires_session=False, category="api"),
    )

    handler = _Handler()
    with caplog.at_level(logging.ERROR, logger="brain_alpha_ops.web.dispatch.web_handler_dispatch"):
        dispatch_get(handler, urlparse("/boom"), ctx)

    assert handler.json_calls[0][0]["error_code"] == "GET_ROUTE_ERROR"
    assert "web route dispatch failed" in caplog.text


def test_dispatch_get_treats_client_disconnect_as_completed(monkeypatch, caplog):
    ctx, _started, _lock = _ctx()

    def disconnected(*_args, **_kwargs):
        raise BrokenPipeError("client closed")

    monkeypatch.setitem(_GET_DISPATCH_HANDLERS, "disconnected", disconnected)
    ctx = dataclasses.replace(
        ctx,
        route_for=lambda _method, _path: SimpleNamespace(handler="disconnected", requires_session=False, category="api"),
    )

    handler = _Handler()
    # P1-5: the dispatch loop was moved to web_handler_dispatch_core.
    with caplog.at_level(logging.INFO, logger="brain_alpha_ops.web.dispatch.web_handler_dispatch_core"):
        dispatch_get(handler, urlparse("/api/candidates"), ctx)

    assert handler.json_calls == []
    assert "web client disconnected before response completed" in caplog.text
    assert "web route dispatch failed" not in caplog.text


def test_dispatch_post_logs_handler_exceptions(caplog):
    ctx, _started, _lock = _ctx()

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    ctx = dataclasses.replace(ctx, connection_test_post_payload=boom)

    handler = _Handler(body={"dry_run": True})
    with caplog.at_level(logging.ERROR, logger="brain_alpha_ops.web.dispatch.web_handler_dispatch"):
        dispatch_post(handler, urlparse("/api/test_connection"), ctx)

    assert handler.json_calls[0][0]["error_code"] == "CONNECTION_ERROR"
    assert "web post route failed" in caplog.text


def test_dispatch_post_test_connection_returns_sanitized_session_status():
    ctx, _started, _lock = _ctx()

    success = _Handler(body={"username": "reader@example.test", "password": "secret"})
    dispatch_post(success, urlparse("/api/test_connection"), ctx)
    payload, status, _headers = success.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["session"]["connected"] is True
    assert payload["session"]["brain_connection_verified"] is True
    assert payload["session"]["credential_source"] == "page"
    assert "password" not in json.dumps(payload)

    failing_ctx = dataclasses.replace(
        ctx,
        test_connection=lambda _payload: {"ok": False, "error_code": "CONNECTION_FAILED", "error": "nope"},
    )
    failed = _Handler(body={"token": "secret-token"})
    dispatch_post(failed, urlparse("/api/test_connection"), failing_ctx)
    payload, status, _headers = failed.json_calls[0]
    assert status == 200
    assert payload["ok"] is False
    assert payload["session"]["connected"] is False
    assert payload["session"]["brain_connection_verified"] is False
    assert "secret-token" not in json.dumps(payload)


def test_dispatch_test_connection_state_feeds_phase_state_until_failure():
    state = {
        "ok": True,
        "authenticated": True,
        "connected": False,
        "brain_connection_verified": False,
        "credential_source": "none",
        "ttl_seconds": 43200,
    }

    def mark(session_id, result, payload):
        state.update({
            "authenticated": bool(session_id),
            "connected": True,
            "brain_connection_verified": True,
            "credential_source": "page" if payload.get("token") else "managed",
            "environment": result.get("environment", "production"),
            "auth_mode": result.get("auth", ""),
        })
        return dict(state)

    def clear(session_id):
        state.update({
            "authenticated": bool(session_id),
            "connected": False,
            "brain_connection_verified": False,
            "credential_source": "none",
        })
        return dict(state)

    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        session_status=lambda _session_id: dict(state),
        mark_brain_connection_verified=mark,
        clear_brain_connection_verified=clear,
        test_connection=lambda _payload: {"ok": True, "environment": "production", "auth": "token"},
    )

    success = _Handler(body={"token": "page-token"})
    dispatch_post(success, urlparse("/api/test_connection"), ctx)
    assert success.json_calls[0][0]["session"]["connected"] is True

    phase = _Handler()
    dispatch_get(phase, urlparse("/api/phase_state"), ctx)
    assert phase.json_calls[0][0]["connected"] is True
    assert phase.json_calls[0][0]["connection"]["credential_source"] == "page"

    failing_ctx = dataclasses.replace(
        ctx,
        test_connection=lambda _payload: {"ok": False, "error_code": "CONNECTION_FAILED", "error": "nope"},
    )
    failed = _Handler(body={"token": "page-token"})
    dispatch_post(failed, urlparse("/api/test_connection"), failing_ctx)
    assert failed.json_calls[0][0]["session"]["connected"] is False

    phase_after_failure = _Handler()
    dispatch_get(phase_after_failure, urlparse("/api/phase_state"), failing_ctx)
    assert phase_after_failure.json_calls[0][0]["connected"] is False


def test_dispatch_phase_state_uses_local_cache_when_account_is_disconnected():
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        session_status=lambda session_id: {
            "ok": True,
            "authenticated": bool(session_id),
            "connected": False,
            "brain_connection_verified": False,
            "credential_source": "none",
            "session_credentials_available": False,
            "ttl_seconds": 43200,
        },
        cloud_alpha_snapshot=lambda **_kwargs: {
            "alphas": [{"id": "prod_alpha"}],
            "summary": {
                "count": 40852,
                "total": 40853,
                "source": "cloud_snapshot",
                "is_stale": False,
                "loaded_at": "2026-06-11T01:00:00Z",
                "age_seconds": 60,
            },
        },
        official_context_file_counts=lambda: {
            "fields_count": 8599,
            "operators_count": 67,
            "datasets_count": 20,
            "context_cache_manifest": {
                "complete": True,
                "is_stale": False,
                "record_counts": {
                    "official_fields.json": 8599,
                    "official_operators.json": 67,
                    "official_datasets.json": 20,
                },
            },
        },
    )

    phase = _Handler()
    dispatch_get(phase, urlparse("/api/phase_state"), ctx)
    payload = phase.json_calls[0][0]

    assert payload["connected"] is False
    assert payload["context_fresh"] is True
    assert payload["context_fresh_source"] == "local_cache"
    assert payload["operation_mode"] == "cache_only"
    assert payload["current_phase"] == "discover"
    assert payload["cloud_alpha_cache"]["ok"] is True
    assert payload["cloud_alpha_cache"]["count"] == 40852
    assert payload["official_context_cache"]["ok"] is True
    assert payload["official_context_cache"]["fields_count"] == 8599


def test_dispatch_phase_state_uses_injected_candidate_pool_summary():
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        candidate_summary_probe=lambda: {
            "ok": True,
            "source": "candidates_jsonl",
            "pool_summary": {
                "main_pool_count": 1,
                "promotable_count": 1,
                "blocked_or_archived_count": 69,
            },
        },
        cloud_alpha_snapshot=lambda **_kwargs: {
            "alphas": [{"id": "prod_alpha"}],
            "summary": {"count": 40852, "is_stale": False},
        },
    )

    phase = _Handler()
    dispatch_get(phase, urlparse("/api/phase_state"), ctx)
    payload = phase.json_calls[0][0]

    assert payload["candidates_count"] == 1
    assert payload["candidate_count_source"] == "candidates_jsonl"
    assert payload["current_phase"] == "evaluate"


def test_submit_with_lock_logs_exceptions(caplog):
    ctx, _started, _lock = _ctx()
    handler = _Handler(body={"alpha_id": "A1"})

    def boom(_payload):
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="brain_alpha_ops.web.dispatch.web_handler_dispatch"):
        from brain_alpha_ops.web_handler_dispatch import _submit_with_lock

        _submit_with_lock(handler, ctx, boom, "SUBMIT_ERROR", payload={"alpha_id": "A1"})

    assert handler.json_calls[0][0]["error_code"] == "SUBMIT_ERROR"
    assert "web submit route failed" in caplog.text


def test_dispatch_get_candidates_falls_back_to_latest_async_generation_result(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr("brain_alpha_ops.web_routes.load_run_config", lambda: run_config)
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
    dispatch_get(handler, urlparse("/api/candidates"), ctx)

    payload = handler.json_calls[0][0]
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["candidates"][0]["alpha_id"] == "alpha_real_1"


def test_dispatch_get_candidates_async_fallback_scans_all_jobs(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr("brain_alpha_ops.web_routes.load_run_config", lambda: run_config)
    ctx, _started, _lock = _ctx()
    ctx.jobs.rows.clear()
    ctx.async_jobs.rows = {
        f"task_{index:04d}": {
            "status": "completed",
            "result": {"ok": True, "candidates": []},
            "progress": {"phase": "completed"},
        }
        for index in range(30)
    }
    ctx.async_jobs.rows["task_0029"]["result"]["candidates"] = [
        {"alpha_id": "alpha_after_25", "expression": "rank(close)"}
    ]

    handler = _Handler()
    dispatch_get(handler, urlparse("/api/candidates"), ctx)

    payload = handler.json_calls[0][0]
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["candidates"][0]["alpha_id"] == "alpha_after_25"


def test_dispatch_get_candidates_marks_async_preview_as_partial(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr("brain_alpha_ops.web_routes.load_run_config", lambda: run_config)
    ctx, _started, _lock = _ctx()
    ctx.jobs.rows.clear()
    ctx.async_jobs.rows = {
        "task_0001": {
            "status": "completed",
            "result": {
                "ok": True,
                "candidates_count": 12,
                "candidates_preview": [{"alpha_id": "alpha_preview", "expression": "rank(close)"}],
            },
            "progress": {"phase": "completed"},
        }
    }

    handler = _Handler()
    dispatch_get(handler, urlparse("/api/candidates"), ctx)

    payload = handler.json_calls[0][0]
    assert payload["ok"] is True
    assert payload["source"] == "latest_async_result_preview"
    assert payload["partial"] is True
    assert payload["returned_count"] == 1
    assert payload["total"] == 12
    assert payload["warning"]


def test_dispatch_get_candidates_reads_full_candidate_ledger(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr("brain_alpha_ops.web_routes.load_run_config", lambda: run_config)
    _write_jsonl(
        tmp_path / "candidates.jsonl",
        [{"alpha_id": f"alpha_{index}", "expression": f"rank(close_{index})"} for index in range(1001)],
    )
    ctx, _started, _lock = _ctx()
    ctx.jobs.rows.clear()
    ctx.async_jobs.rows = {
        "task_0001": {
            "status": "completed",
            "result": {"ok": True, "candidates": [{"alpha_id": "latest_only", "expression": "rank(close)"}]},
            "progress": {"phase": "completed"},
        }
    }

    handler = _Handler()
    dispatch_get(handler, urlparse("/api/candidates"), ctx)

    payload = handler.json_calls[0][0]
    assert payload["ok"] is True
    assert payload["source"] == "candidates_jsonl"
    assert payload["count"] == 1001
    assert payload["returned_count"] == 1001
    assert payload["total"] == 1001
    assert payload["candidates"][0]["alpha_id"] == "alpha_0"
    assert payload["candidates"][-1]["alpha_id"] == "alpha_1000"


def test_dispatch_get_candidates_applies_local_lifecycle_risk_to_decisions(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr("brain_alpha_ops.web_routes.load_run_config", lambda: run_config)
    _write_jsonl(
        tmp_path / "candidates.jsonl",
        [
            {
                "alpha_id": "alpha_risky",
                "expression": "rank(close)",
                "lifecycle_status": "candidate_pool_retained",
                "scorecard": {"total_score": 92, "decision_band": "submit_candidate"},
                "quality_diagnosis": {
                    "local_candidate_valid": True,
                    "submission_ready": False,
                    "blocking_reasons": ["missing_official_metrics"],
                    "reasons": [
                        {
                            "code": "missing_official_metrics",
                            "category": "official_evidence_missing",
                            "severity": "blocking",
                        }
                    ],
                },
                "local_quality": {"passed": True},
            }
        ],
    )
    _write_jsonl(
        tmp_path / "lifecycle.jsonl",
        [
            {
                "alpha_id": "alpha_risky",
                "stage": "official_validation",
                "status": "FAILED",
                "timestamp": "2026-06-12T01:00:00Z",
            }
        ],
    )
    ctx, _started, _lock = _ctx()

    handler = _Handler()
    dispatch_get(handler, urlparse("/api/candidates"), ctx)

    payload = handler.json_calls[0][0]
    candidate = payload["candidates"][0]
    decision = candidate["production_decision"]
    assert payload["ok"] is True
    assert decision["action"] == "optimize"
    assert "lifecycle_history_failed" in decision["reason_codes"]
    assert payload["main_pool_candidates"] == []
    assert payload["workflow_plan"]["validator"]["candidate_ids"] == []
    assert payload["workflow_plan"]["rework"]["candidate_ids"] == ["alpha_risky"]


def test_dispatch_get_candidates_summary_streams_complete_counts_without_rows(monkeypatch, tmp_path):
    run_config = RunConfig(environment="production")
    run_config.ops.storage_dir = str(tmp_path)
    monkeypatch.setattr("brain_alpha_ops.web_routes.load_run_config", lambda: run_config)
    _write_jsonl(
        tmp_path / "candidates.jsonl",
        [
            {"alpha_id": "alpha_ready", "lifecycle_status": "submission_ready"},
            {"alpha_id": "alpha_gate_ready", "gate": {"submission_ready": True}},
            {"alpha_id": "alpha_gate_passed_only", "gate": {"passed": True}},
            {"alpha_id": "alpha_local_passed_only", "local_quality": {"passed": True}},
            {"alpha_id": "alpha_string_false_diagnosis", "quality_diagnosis": {"submission_ready": "false"}},
            {"alpha_id": "alpha_string_false_gate", "gate": {"submission_ready": "false"}},
            {
                "alpha_id": "alpha_qualified_only",
                "quality_diagnosis": {
                    "qualified": True,
                    "submission_ready": False,
                    "blocking_reasons": ["needs_human_confirmation"],
                },
            },
            {"alpha_id": "alpha_blocked", "local_quality": {"passed": False, "reasons": ["blocked"]}},
        ],
    )
    ctx, _started, _lock = _ctx()

    handler = _Handler()
    dispatch_get(handler, urlparse("/api/candidates?summary=true"), ctx)

    payload = handler.json_calls[0][0]
    assert payload["ok"] is True
    assert payload["summary_only"] is True
    assert payload["candidates"] == []
    assert payload["items"] == []
    assert payload["returned_count"] == 0
    assert payload["total"] == 8
    assert payload["ready_count"] == 2
    assert payload["blocked_count"] == 1


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
    bodyless_routes = {"/api/logout", "/api/shutdown", "/api/session"}
    assert {path for path, route in POST_ROUTES.items() if route.handler in {"logout", "shutdown", "session"}} == bodyless_routes

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


def test_dispatch_post_session_returns_full_csrf_token_and_cookie():
    ctx, _started, _lock = _ctx()
    handler = _Handler(body=[], session=False)

    dispatch_post(handler, urlparse("/api/session"), ctx)

    payload, status, headers = handler.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["session_id"] == "session_1"[:8]
    assert payload["csrf_token"] == "csrf_1"
    assert payload["stream_token"] == "stream_1"
    assert payload["ttl_seconds"] == 43200
    assert payload["session"]["connected"] is False
    assert ("Set-Cookie", "cookie=session_1") in headers


def test_dispatch_post_session_returns_existing_verified_connection_state():
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        session_status=lambda session_id: {
            "ok": True,
            "authenticated": bool(session_id),
            "connected": True,
            "brain_connection_verified": True,
            "credential_source": "managed",
            "environment": "production",
            "auth_mode": "token",
            "ttl_seconds": 43200,
        },
    )
    handler = _Handler(body=[], session=False)

    dispatch_post(handler, urlparse("/api/session"), ctx)

    payload, status, headers = handler.json_calls[0]
    assert status == 200
    assert payload["csrf_token"] == "csrf_1"
    assert payload["stream_token"] == "stream_1"
    assert payload["connected"] is True
    assert payload["brain_connection_verified"] is True
    assert payload["session"]["credential_source"] == "managed"
    assert ("Set-Cookie", "cookie=session_1") in headers


def test_dispatch_post_session_requires_admin_token_when_remote_admin_is_enabled():
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(ctx, remote_admin_required=lambda: True)

    missing = _Handler(body=[])
    dispatch_post(missing, urlparse("/api/session"), ctx)
    assert missing.json_calls[0][1] == 401
    assert missing.json_calls[0][0]["error_code"] == "ADMIN_AUTH_REQUIRED"
    assert missing.json_calls[0][2] == []

    allowed = _Handler(body=[], headers={"Authorization": "Bearer admin-token"})
    dispatch_post(allowed, urlparse("/api/session"), ctx)
    payload, status, headers = allowed.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["csrf_token"] == "csrf_1"
    assert ("Set-Cookie", "cookie=session_1") in headers


def test_dispatch_post_blocks_legacy_pipeline_start_fallback(monkeypatch):
    ctx, started, _lock = _ctx()
    handler = _Handler(body={"config_path": "config/run_config.json"})

    dispatch_post(handler, urlparse("/api/pipeline/start"), ctx)

    payload, status, _headers = handler.json_calls[0]
    assert status == 404
    assert payload["error_code"] == "LEGACY_ROUTE_DISABLED"
    assert started == []


def test_dispatch_post_unknown_legacy_fallback_is_rate_limited(monkeypatch):
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        route_for=lambda _method, _path: None,
        rate_limit_request=lambda _key, _method, _path: {
            "ok": False,
            "error_code": "RATE_LIMITED",
            "error": "too many requests; retry later",
            "retry_after": 9,
        },
    )

    handler = _Handler(body={"alpha": 1})
    dispatch_post(handler, urlparse("/api/legacy-unmigrated"), ctx)

    payload, status, headers = handler.json_calls[0]
    assert status == 429
    assert payload["error_code"] == "RATE_LIMITED"
    assert payload["user_error_kind"] == "web_rate_limited"
    assert payload["user_message"] == "本地 Web 操作请求过于频繁，请稍后再试。"
    assert ("Retry-After", "9") in headers


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
    assert knowledge.json_calls[0][0]["knowledge"]["limit"] == 4040

    prompt_runs = _Handler()
    dispatch_get(prompt_runs, urlparse("/api/prompt_runs?limit=999999"), ctx)
    assert prompt_runs.json_calls[0][0]["prompt_runs"]["limit"] == 4040

    guidance = _Handler()
    dispatch_get(guidance, urlparse("/api/assistant_guidance?limit=999999"), ctx)
    assert guidance.json_calls[0][0]["guidance"]["limit"] == 4040

    record_lookup = _Handler()
    dispatch_get(record_lookup, urlparse("/api/sqlite_record_lookup?alpha_id=a1&limit=999999"), ctx)
    assert record_lookup.json_calls[0][0]["record_lookup"]["limit"] == 404


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


def test_dispatch_post_starts_jobs_and_blocks_raw_submit_routes():
    ctx, started, submit_lock = _ctx()

    run = _Handler(body={"alpha": 1})
    dispatch_post(run, urlparse("/api/run"), ctx)
    assert run.json_calls[0][0] == {
        "ok": True,
        "job_id": "job_1",
        "task_id": "job_1",
        "auto_submit": False,
        "submitted": False,
        "sse_url": "/sse?job_id=job_1",
        "status_url": "/api/production-validation/status?job_id=job_1",
    }
    assert started[0] == ("run", "job_1", {"alpha": 1, "autoSubmit": False, "auto_submit": False})

    submit = _Handler(body={"alpha_id": "a1"})
    dispatch_post(submit, urlparse("/api/submit"), ctx)
    assert submit.json_calls[0][1] == 403
    assert submit.json_calls[0][0]["error_code"] == "REAL_SUBMIT_DISABLED_WEB_FLOW"
    assert submit.json_calls[0][0]["submitted"] is False
    assert submit_lock.acquired is False
    assert submit_lock.released is False

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


def test_dispatch_post_starts_async_operation_jobs(monkeypatch):
    ctx, started, _lock = _ctx()
    optimized = []

    generate = _Handler(body={"count": 3})
    dispatch_post(generate, urlparse("/api/generate_candidates"), ctx)
    assert generate.json_calls[0][0]["task_id"] == "job_1"
    assert started[-1] == ("generate_candidates", "job_1", {"count": 3})

    monkeypatch.setattr(
        "brain_alpha_ops.web_handler_dispatch._start_optimize_candidates_job",
        lambda opt_ctx, job_id, payload: optimized.append((opt_ctx, job_id, payload)),
    )
    optimize = _Handler(body={"candidates": [{"alpha_id": "a1"}], "max_mutations": 3})
    dispatch_post(optimize, urlparse("/api/candidates/optimize"), ctx)
    assert optimize.json_calls[0][0]["task_id"] == "job_1"
    assert optimize.json_calls[0][0]["sse_url"] == "/sse?job_id=job_1"
    assert optimize.json_calls[0][0]["status_url"] == "/api/production-validation/status?job_id=job_1"
    assert optimized == [(ctx, "job_1", {"candidates": [{"alpha_id": "a1"}], "max_mutations": 3})]

    scoring = _Handler(body={"candidate": {"alpha_id": "a1"}})
    dispatch_post(scoring, urlparse("/api/scoring/evaluate"), ctx)
    assert scoring.json_calls[0][0]["sse_url"] == "/sse?job_id=job_1"
    assert started[-1] == ("scoring_evaluate", "job_1", {"candidate": {"alpha_id": "a1"}})

    submit_batch = _Handler(body={"alpha_ids": ["a1"]})
    dispatch_post(submit_batch, urlparse("/api/submit_batch"), ctx)
    assert submit_batch.json_calls[0][1] == 403
    assert submit_batch.json_calls[0][0]["error_code"] == "REAL_SUBMIT_DISABLED_WEB_FLOW"
    assert submit_batch.json_calls[0][0]["submitted"] is False
    assert started[-1] == ("scoring_evaluate", "job_1", {"candidate": {"alpha_id": "a1"}})


def test_dispatch_post_candidates_simulate_starts_active_job_without_watchdog(monkeypatch, tmp_path):
    ctx, _started, _lock = _ctx()
    async_jobs = JobStore(tmp_path / "async_jobs.json", job_prefix="task")
    ctx = dataclasses.replace(ctx, async_jobs=async_jobs)
    monkeypatch.setattr(
        "brain_alpha_ops.web_candidates.simulation.simulate_candidates_job",
        lambda job_id, payload, *, job_store, log: None,
    )

    handler = _Handler(body={"confirm_simulation": True})
    dispatch_post(handler, urlparse("/api/candidates/simulate"), ctx)

    payload, status, _headers = handler.json_calls[0]
    assert status == 200
    job_id = payload["job_id"]
    row = async_jobs.get(job_id)
    assert row is not None
    assert row["status"] == "running"
    assert row["progress"]["phase"] == "simulation_starting"
    assert row["progress"]["status_message"]
    assert row["progress"]["percent_complete"] == 0


def test_dispatch_post_candidates_simulate_blocks_auxiliary_conflict_before_starting_job(monkeypatch):
    ctx, _started, _lock = _ctx()
    ctx = dataclasses.replace(
        ctx,
        active_auxiliary_operation=lambda **kwargs: ("sync", "云端同步正在运行，请完成后再启动官方候选模拟。"),
    )
    monkeypatch.setattr(
        "brain_alpha_ops.web_candidates.simulation.simulate_candidates_job",
        lambda job_id, payload, *, job_store, log: (_ for _ in ()).throw(AssertionError("worker should not start")),
    )

    handler = _Handler(body={"confirm_simulation": True})
    dispatch_post(handler, urlparse("/api/candidates/simulate"), ctx)

    payload, status, _headers = handler.json_calls[0]
    assert status == 409
    assert payload["error_code"] == "CONFLICT_AUX_OP"
    assert payload["user_error_kind"] == "queue_blocked"
    assert payload["next_action"] == "review_active_job"
    assert "云端同步" in payload["error"]
    assert ctx.async_jobs.created == []


def test_dispatch_post_candidates_simulate_blocks_active_async_non_simulation_job(monkeypatch, tmp_path):
    ctx, _started, _lock = _ctx()
    async_jobs = JobStore(tmp_path / "async_jobs.json", job_prefix="task")
    existing = async_jobs.create({
        "status": "running",
        "progress": {"phase": "candidate_generation", "percent_complete": 15},
    })
    ctx = dataclasses.replace(ctx, async_jobs=async_jobs)
    monkeypatch.setattr(
        "brain_alpha_ops.web_candidates.simulation.simulate_candidates_job",
        lambda job_id, payload, *, job_store, log: (_ for _ in ()).throw(AssertionError("worker should not start")),
    )

    handler = _Handler(body={"confirm_simulation": True})
    dispatch_post(handler, urlparse("/api/candidates/simulate"), ctx)

    payload, status, _headers = handler.json_calls[0]
    assert status == 409
    assert payload["error_code"] == "CONFLICT_RUNNING"
    assert payload["user_error_kind"] == "queue_blocked"
    assert payload["next_action"] == "review_active_job"
    assert payload["job_id"] == existing
    assert payload["phase"] == "candidate_generation"
    assert len(async_jobs.jobs) == 1


def test_dispatch_post_candidates_simulate_allows_only_one_concurrent_start(monkeypatch, tmp_path):
    ctx, _started, _lock = _ctx()
    async_jobs = JobStore(tmp_path / "async_jobs.json", job_prefix="task")
    ctx = dataclasses.replace(ctx, async_jobs=async_jobs)
    monkeypatch.setattr(
        "brain_alpha_ops.web_candidates.simulation.simulate_candidates_job",
        lambda job_id, payload, *, job_store, log: None,
    )
    barrier = threading.Barrier(2)

    def start_request():
        handler = _Handler(body={"confirm_simulation": True})
        barrier.wait(timeout=5)
        dispatch_post(handler, urlparse("/api/candidates/simulate"), ctx)
        return handler.json_calls[0]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: start_request(), range(2)))

    statuses = sorted(status for _payload, status, _headers in results)
    assert statuses == [200, 409]
    ok_payloads = [payload for payload, status, _headers in results if status == 200]
    conflict_payloads = [payload for payload, status, _headers in results if status == 409]
    assert ok_payloads[0]["job_id"] in async_jobs.jobs
    assert conflict_payloads[0]["error_code"] == "CONFLICT_RUNNING"
    assert conflict_payloads[0]["user_error_kind"] == "queue_blocked"
    assert len(async_jobs.jobs) == 1


def test_dispatch_post_candidates_simulate_blocks_stopping_simulation_job(monkeypatch, tmp_path):
    ctx, _started, _lock = _ctx()
    async_jobs = JobStore(tmp_path / "async_jobs.json", job_prefix="task")
    existing = async_jobs.create({
        "status": "running",
        "progress": {"phase": "simulation_polling", "percent_complete": 10},
    })
    async_jobs.cancel(existing)
    ctx = dataclasses.replace(ctx, async_jobs=async_jobs)
    monkeypatch.setattr(
        "brain_alpha_ops.web_candidates.simulation.simulate_candidates_job",
        lambda job_id, payload, *, job_store, log: (_ for _ in ()).throw(AssertionError("worker should not start")),
    )

    handler = _Handler(body={"confirm_simulation": True})
    dispatch_post(handler, urlparse("/api/candidates/simulate"), ctx)

    payload, status, _headers = handler.json_calls[0]
    assert status == 409
    assert payload["error_code"] == "CONFLICT_RUNNING"
    assert payload["user_error_kind"] == "queue_blocked"
    assert payload["job_id"] == existing


def test_dispatch_post_candidates_simulate_validates_candidate_ids_before_starting_job(monkeypatch):
    ctx, _started, _lock = _ctx()
    monkeypatch.setattr(
        "brain_alpha_ops.web_candidates.simulation.simulate_candidates_job",
        lambda job_id, payload, *, job_store, log: (_ for _ in ()).throw(AssertionError("worker should not start")),
    )

    simulate = _Handler(body={"candidate_ids": "not-a-list"})
    dispatch_post(simulate, urlparse("/api/candidates/simulate"), ctx)

    payload, status, _headers = simulate.json_calls[0]
    assert status == 400
    assert payload["error_code"] == "VALIDATION_ERROR"
    assert "candidate_ids" in payload["error"]
    assert ctx.async_jobs.created == []

    extreme = _Handler(body={"candidate_ids": ["alpha_1"], "poll_timeout": -1})
    dispatch_post(extreme, urlparse("/api/candidates/simulate"), ctx)
    payload, status, _headers = extreme.json_calls[0]
    assert status == 400
    assert payload["error_code"] == "VALIDATION_ERROR"
    assert "poll_timeout" in payload["error"]
    assert ctx.async_jobs.created == []


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


def test_dispatch_post_sync_alphas_preserves_session_credentials_for_worker():
    ctx, started, _lock = _ctx()

    sync = _Handler(body={
        "syncRange": "3d",
        "refreshOfficialContext": True,
        "username": "tester@example.com",
        "password": "dummy-password",
        "token": "dummy-token",
    })
    dispatch_post(sync, urlparse("/api/sync_alphas"), ctx)

    assert sync.json_calls[0][1] == 200
    assert started == [(
        "sync",
        "job_1",
        {
            "syncRange": "3d",
            "refreshOfficialContext": True,
            "username": "tester@example.com",
            "password": "dummy-password",
            "token": "dummy-token",
        },
    )]


def test_dispatch_post_sync_alphas_conflict_returns_active_status_pointer():
    ctx, started, _lock = _ctx()
    ctx.sync_jobs.active = ("sync_active", {
        "status": "running",
        "progress": {"phase": "cloud_sync"},
    })

    sync = _Handler(body={"syncRange": "all", "refreshOfficialContext": True})
    dispatch_post(sync, urlparse("/api/sync_alphas"), ctx)

    payload, status, _headers = sync.json_calls[0]
    assert status == 409
    assert payload["ok"] is False
    assert payload["job_id"] == "sync_active"
    assert payload["task_id"] == "sync_active"
    assert payload["status_url"] == "/api/sync_status?job_id=sync_active"
    assert started == []


def test_dispatch_post_sync_alphas_uses_server_session_credentials_when_body_omits_them():
    ctx, started, _lock = _ctx()

    connection = _Handler(body={
        "username": "session-user@example.test",
        "password": "session-password",
    })
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)
    connection_payload = connection.json_calls[0][0]
    assert connection_payload["session"]["connected"] is True
    assert connection_payload["session"]["session_credentials_available"] is True

    sync = _Handler(body={"syncRange": "all", "refreshOfficialContext": True})
    dispatch_post(sync, urlparse("/api/sync_alphas"), ctx)

    response, status, _headers = sync.json_calls[0]
    assert status == 200
    assert response["ok"] is True
    assert started == [(
        "sync",
        "job_1",
        {
            "syncRange": "all",
            "refreshOfficialContext": True,
            "username": "session-user@example.test",
            "password": "session-password",
        },
    )]
    encoded_response = json.dumps(response, ensure_ascii=False)
    assert "session-user@example.test" not in encoded_response
    assert "session-password" not in encoded_response


def test_dispatch_post_test_connection_reuses_server_session_credentials_when_body_omits_them():
    ctx, _started, _lock = _ctx()
    seen_payloads = []

    def test_connection(payload):
        seen_payloads.append(dict(payload))
        return {"ok": True, "environment": "production", "auth": "token"}

    ctx = dataclasses.replace(ctx, test_connection=test_connection)

    connection = _Handler(body={"token": "session-token"})
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    retest = _Handler(body={})
    dispatch_post(retest, urlparse("/api/test_connection"), ctx)

    assert seen_payloads == [{"token": "session-token"}, {"token": "session-token"}]
    payload, status, _headers = retest.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["session"]["connected"] is True
    assert payload["session"]["session_credentials_available"] is True
    assert "session-token" not in json.dumps(payload, ensure_ascii=False)


def test_dispatch_post_mixed_connection_stores_basic_credentials_for_refresh_continuity():
    ctx, started, _lock = _ctx()

    connection = _Handler(body={
        "username": "basic-user@example.test",
        "password": "basic-password",
        "token": "stale-token",
    })
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    sync = _Handler(body={"syncRange": "all"})
    dispatch_post(sync, urlparse("/api/sync_alphas"), ctx)

    assert sync.json_calls[0][1] == 200
    assert started == [(
        "sync",
        "job_1",
        {
            "syncRange": "all",
            "username": "basic-user@example.test",
            "password": "basic-password",
        },
    )]
    encoded = json.dumps({
        "connection": connection.json_calls,
        "sync_response": sync.json_calls,
        "started": started,
    }, ensure_ascii=False)
    assert "stale-token" not in encoded
    assert "basic-password" in encoded


def test_dispatch_post_check_uses_server_session_credentials_when_body_omits_them():
    ctx, _started, _lock = _ctx()
    seen_payload = {}

    def check_candidate(payload):
        seen_payload.update(dict(payload))
        return {"ok": True, "alpha_id": payload.get("alpha_id")}

    ctx = dataclasses.replace(ctx, check_candidate=check_candidate)

    connection = _Handler(body={"token": "session-token"})
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    check = _Handler(body={"alpha_id": "alpha_1"})
    dispatch_post(check, urlparse("/api/check"), ctx)

    assert check.json_calls[0][1] == 200
    assert seen_payload == {"alpha_id": "alpha_1", "token": "session-token"}
    assert "session-token" not in json.dumps(check.json_calls[0][0], ensure_ascii=False)


def test_dispatch_post_check_batch_uses_server_session_credentials_when_body_omits_them():
    ctx, started, _lock = _ctx()

    connection = _Handler(body={"username": "session-user@example.test", "password": "session-password"})
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    batch = _Handler(body={"candidate_ids": ["alpha_1"], "mode": "quick"})
    dispatch_post(batch, urlparse("/api/check_batch"), ctx)

    assert batch.json_calls[0][1] == 200
    assert started == [(
        "check_batch",
        "job_1",
        {
            "candidate_ids": ["alpha_1"],
            "mode": "quick",
            "username": "session-user@example.test",
            "password": "session-password",
        },
    )]
    assert "session-password" not in json.dumps(batch.json_calls[0][0], ensure_ascii=False)


def test_dispatch_post_run_uses_server_session_credentials_without_persisting_them(tmp_path):
    ctx, started, _lock = _ctx()
    jobs = JobStore(tmp_path / "jobs.json", job_prefix="job")
    ctx = dataclasses.replace(
        ctx,
        jobs=jobs,
        start_run_job=lambda job_id, payload: started.append(("run", job_id, dict(payload))),
    )

    connection = _Handler(body={"token": "session-token"})
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    run = _Handler(body={"autoSubmit": True, "auto_submit": True})
    dispatch_post(run, urlparse("/api/run"), ctx)

    response, status, _headers = run.json_calls[0]
    job_id = response["job_id"]
    assert status == 200
    assert started == [("run", job_id, {"autoSubmit": False, "auto_submit": False, "token": "session-token"})]
    stored = jobs.get(job_id)
    persisted = (tmp_path / "jobs.json").read_text(encoding="utf-8")
    assert stored is not None
    assert "session-token" not in json.dumps(stored, ensure_ascii=False)
    assert "session-token" not in persisted


def test_dispatch_post_candidates_simulate_uses_session_credentials_without_persisting_them(monkeypatch, tmp_path):
    ctx, _started, _lock = _ctx()
    async_jobs = JobStore(tmp_path / "async_jobs.json", job_prefix="async")
    ctx = dataclasses.replace(ctx, async_jobs=async_jobs)
    captured = {}

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    def fake_simulate(job_id, payload, *, job_store, log):
        captured["job_id"] = job_id
        captured["payload"] = dict(payload)
        job_store.update(job_id, status="completed", result={"ok": True})

    monkeypatch.setattr("threading.Thread", ImmediateThread)
    monkeypatch.setattr("brain_alpha_ops.web_candidates.simulation.simulate_candidates_job", fake_simulate)

    connection = _Handler(body={"token": "session-token"})
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    simulate = _Handler(body={"candidates": [{"alpha_id": "alpha_1", "expression": "rank(close)"}], "confirm_simulation": True})
    dispatch_post(simulate, urlparse("/api/candidates/simulate"), ctx)

    response, status, _headers = simulate.json_calls[0]
    assert status == 200
    assert response["ok"] is True
    assert captured["payload"] == {
        "candidates": [{"alpha_id": "alpha_1", "expression": "rank(close)"}],
        "token": "session-token",
    }
    assert captured["job_id"] == response["job_id"]
    persisted = (tmp_path / "async_jobs.json").read_text(encoding="utf-8")
    assert "session-token" not in json.dumps(response, ensure_ascii=False)
    assert "session-token" not in persisted


def test_dispatch_post_does_not_inject_session_credentials_into_local_or_blocked_routes(monkeypatch):
    ctx, started, submit_lock = _ctx()
    captured = {}

    def save_config(payload):
        captured["config"] = dict(payload)
        return {"ok": True}

    def preview(payload):
        captured["preview"] = dict(payload)
        return {"ok": True, "preview": True}

    ctx = dataclasses.replace(ctx, save_run_config_payload=save_config)
    monkeypatch.setattr("brain_alpha_ops.web_candidates.simulation.simulation_candidates_payload", preview)
    monkeypatch.setattr(
        "brain_alpha_ops.web_handler_dispatch._start_optimize_candidates_job",
        lambda _ctx, _job_id, payload: captured.update({"optimize": dict(payload)}),
    )

    connection = _Handler(body={"token": "session-token"})
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    generate = _Handler(body={"count": 1})
    dispatch_post(generate, urlparse("/api/generate_candidates"), ctx)

    optimize = _Handler(body={"candidates": [{"alpha_id": "alpha_1"}]})
    dispatch_post(optimize, urlparse("/api/candidates/optimize"), ctx)

    config = _Handler(body={"environment": "production"})
    dispatch_post(config, urlparse("/api/config"), ctx)

    scoring = _Handler(body={"alpha_id": "alpha_1"})
    dispatch_post(scoring, urlparse("/api/scoring/evaluate"), ctx)

    preview_call = _Handler(body={"preview": True, "candidates": [{"alpha_id": "alpha_1"}]})
    dispatch_post(preview_call, urlparse("/api/candidates/simulate"), ctx)

    submit = _Handler(body={"alpha_id": "alpha_1"})
    dispatch_post(submit, urlparse("/api/submit"), ctx)

    assert ("generate_candidates", "job_1", {"count": 1}) in started
    assert ("scoring_evaluate", "job_1", {"alpha_id": "alpha_1"}) in started
    assert optimize.json_calls[0][0]["task_id"] == "job_1"
    assert captured["optimize"] == {"candidates": [{"alpha_id": "alpha_1"}]}
    assert captured["config"] == {"environment": "production"}
    assert captured["preview"] == {"preview": True, "candidates": [{"alpha_id": "alpha_1"}]}
    assert submit.json_calls[0][1] == 403
    assert submit.json_calls[0][0]["error_code"] == "REAL_SUBMIT_DISABLED_WEB_FLOW"
    assert submit_lock.acquired is False

    encoded = json.dumps({
        "started": started,
        "captured": captured,
        "submit": submit.json_calls,
        "generate": generate.json_calls,
        "config": config.json_calls,
        "scoring": scoring.json_calls,
        "preview": preview_call.json_calls,
    }, ensure_ascii=False)
    assert "session-token" not in encoded


def test_failed_connection_clears_server_session_credentials():
    ctx, started, _lock = _ctx()

    connection = _Handler(body={"token": "session-token"})
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    failing_ctx = dataclasses.replace(
        ctx,
        test_connection=lambda _payload: {"ok": False, "error_code": "CONNECTION_FAILED", "error": "nope"},
    )
    failed = _Handler(body={"token": "session-token"})
    dispatch_post(failed, urlparse("/api/test_connection"), failing_ctx)
    assert failed.json_calls[0][0]["session"]["session_credentials_available"] is False

    sync = _Handler(body={"syncRange": "all"})
    dispatch_post(sync, urlparse("/api/sync_alphas"), failing_ctx)
    assert started == [("sync", "job_1", {"syncRange": "all"})]


def test_dispatch_logout_clears_server_session_credentials():
    ctx, started, _lock = _ctx()

    connection = _Handler(body={"token": "session-token"})
    dispatch_post(connection, urlparse("/api/test_connection"), ctx)

    logout = _Handler(body=[])
    dispatch_post(logout, urlparse("/api/logout"), ctx)

    sync = _Handler(body={"syncRange": "all"})
    dispatch_post(sync, urlparse("/api/sync_alphas"), ctx)

    assert logout.json_calls[0][1] == 200
    assert ("expire", "session_1", {}) in started
    assert started[-1] == ("sync", "job_1", {"syncRange": "all"})


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

    cancel = _Handler(body={})
    dispatch_post(cancel, urlparse("/api/cancel"), ctx)
    assert cancel.json_calls[0][1] == 400
    assert cancel.json_calls[0][0]["error_code"] == "VALIDATION_ERROR"

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
    assert payload["user_error_kind"] == "web_rate_limited"
    assert payload["next_action"] == "wait_and_retry"
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
    assert payload["user_error_kind"] == "web_rate_limited"
    assert ("Retry-After", "9") in headers
    assert len(started) == 1

    now[0] = 111.0
    third = _Handler(body={"alpha": 3})
    dispatch_post(third, urlparse("/api/run"), ctx)
    assert third.json_calls[0][1] == 200
    assert len(started) == 2


def test_rate_limit_key_falls_back_to_client_address_without_session():
    handler = _Handler(body={"alpha": 1})
    handler._session_id_from_cookie = lambda: ""
    handler.client_address = ("10.0.0.1", 61234)

    assert hasattr(handler, "_request") and handler.client_address.startswith("client:10.0.0.1")


def test_dispatch_post_can_cancel_sync_job():
    ctx, _started, _lock = _ctx()
    ctx.sync_jobs.rows["sync_1"] = {"status": "running", "progress": {"phase": "cloud_sync"}}

    cancel = _Handler(body={"job_id": "sync_1"})
    dispatch_post(cancel, urlparse("/api/sync_cancel"), ctx)

    payload, status, _headers = cancel.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["job_id"] == "sync_1"
    assert payload["status"] == "stopping"
    assert "云端同步" in payload["message"]


def test_dispatch_post_sync_cancel_does_not_reopen_terminal_job():
    ctx, _started, _lock = _ctx()
    ctx.sync_jobs.rows["sync_failed"] = {"status": "failed", "progress": {"phase": "watchdog_failed"}}

    cancel = _Handler(body={"job_id": "sync_failed"})
    dispatch_post(cancel, urlparse("/api/sync_cancel"), ctx)

    payload, status, _headers = cancel.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["job_id"] == "sync_failed"
    assert payload["status"] == "failed"
    assert payload["already_terminal"] is True
    assert ctx.sync_jobs.rows["sync_failed"]["status"] == "failed"
    assert ctx.sync_jobs.cancelled == []


def test_dispatch_post_can_cancel_job_from_any_web_store():
    ctx, _started, _lock = _ctx()
    ctx.jobs.rows["job_2"] = {"status": "running", "progress": {"phase": "run"}}
    ctx.sync_jobs.rows["sync_1"] = {"status": "running", "progress": {"phase": "sync"}}
    ctx.check_jobs.rows["check_1"] = {"status": "running", "progress": {"phase": "check"}}
    ctx.async_jobs.rows["task_1"] = {"status": "running", "progress": {"phase": "async"}}

    cases = [
        ("job_2", "run", ctx.jobs),
        ("sync_1", "sync", ctx.sync_jobs),
        ("check_1", "check", ctx.check_jobs),
        ("task_1", "async", ctx.async_jobs),
    ]
    for job_id, job_type, store in cases:
        handler = _Handler(body={"job_id": job_id})
        dispatch_post(handler, urlparse("/api/cancel"), ctx)

        payload, status, _headers = handler.json_calls[0]
        assert status == 200
        assert payload["ok"] is True
        assert payload["job_id"] == job_id
        assert payload["task_id"] == job_id
        assert payload["job_type"] == job_type
        assert payload["status"] == "stopping"
        assert payload["status_kind"] == "active"
        assert payload["terminal"] is False
        assert payload["next_action"] == "monitor_or_cancel"
        assert store.rows[job_id]["cancel"] is True

    missing = _Handler(body={"job_id": "missing_1"})
    dispatch_post(missing, urlparse("/api/cancel"), ctx)

    payload, status, _headers = missing.json_calls[0]
    assert status == 404
    assert payload["ok"] is False
    assert payload["error_code"] == "JOB_NOT_FOUND"
    assert payload["user_error_kind"] == "job_not_found"
    assert payload["job_id"] == "missing_1"


def test_dispatch_post_cancel_does_not_reopen_terminal_job():
    ctx, _started, _lock = _ctx()
    ctx.jobs.rows["job_failed"] = {"status": "failed", "progress": {"phase": "watchdog_failed"}}

    handler = _Handler(body={"job_id": "job_failed"})
    dispatch_post(handler, urlparse("/api/cancel"), ctx)

    payload, status, _headers = handler.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["job_id"] == "job_failed"
    assert payload["task_id"] == "job_failed"
    assert payload["job_type"] == "run"
    assert payload["status"] == "failed"
    assert payload["status_kind"] == "failed"
    assert payload["terminal"] is True
    assert payload["user_error_kind"] == "job_failed"
    assert payload["already_terminal"] is True
    assert ctx.jobs.rows["job_failed"]["status"] == "failed"
    assert ctx.jobs.cancelled == []


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


def test_dispatch_post_run_forces_non_submit_before_validation_and_queueing():
    ctx, started, _lock = _ctx()
    validated_payloads: list[dict] = []
    ctx = dataclasses.replace(
        ctx,
        validate_run_payload=lambda payload: validated_payloads.append(dict(payload)),
    )

    run = _Handler(body={"autoSubmit": True, "auto_submit": True, "username": "tester@example.com", "password": "dummy-password"})
    dispatch_post(run, urlparse("/api/run"), ctx)

    payload, status, _headers = run.json_calls[0]
    assert status == 200
    assert payload["ok"] is True
    assert payload["auto_submit"] is False
    assert payload["submitted"] is False
    assert validated_payloads[0]["autoSubmit"] is False
    assert validated_payloads[0]["auto_submit"] is False
    assert started == [("run", "job_1", validated_payloads[0])]


def test_dispatch_post_run_stores_executes_non_submit_and_redacts_session_credentials(tmp_path):
    ctx, started, _lock = _ctx()
    jobs = JobStore(tmp_path / "jobs.json", job_prefix="job")
    ctx = dataclasses.replace(
        ctx,
        jobs=jobs,
        start_run_job=lambda job_id, payload: started.append(("run", job_id, dict(payload))),
    )

    run = _Handler(body={
        "autoSubmit": True,
        "auto_submit": True,
        "username": "tester@example.com",
        "password": "dummy-password",
        "token": "dummy-token",
    })
    dispatch_post(run, urlparse("/api/run"), ctx)

    response, status, _headers = run.json_calls[0]
    job_id = response["job_id"]
    assert status == 200
    assert response["auto_submit"] is False
    assert response["submitted"] is False
    assert started == [(
        "run",
        job_id,
        {
            "autoSubmit": False,
            "auto_submit": False,
            "username": "tester@example.com",
            "password": "dummy-password",
            "token": "dummy-token",
        },
    )]

    stored = jobs.get(job_id)
    assert stored is not None
    assert stored["safe_mode"] == {
        "autoSubmit": False,
        "auto_submit": False,
        "submit_endpoint_required": True,
    }
    assert stored["result"]["summary"] == {
        "submitted_this_run": 0,
        "auto_submitted": 0,
    }

    status_handler = _Handler()
    dispatch_get(status_handler, urlparse(f"/api/status?job_id={job_id}"), ctx)
    status_payload = status_handler.json_calls[0][0]
    encoded_status = json.dumps(status_payload, ensure_ascii=False)
    encoded_store = json.dumps(stored, ensure_ascii=False)
    persisted = (tmp_path / "jobs.json").read_text(encoding="utf-8")
    for secret in ("tester@example.com", "dummy-password", "dummy-token"):
        assert secret not in encoded_status
        assert secret not in encoded_store
        assert secret not in persisted


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

    assert handler.json_calls[-1][1] in (500, 404, 400)
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

    assert handler.json_calls[-1][1] in (500, 404, 400)
    assert handler.json_calls[-1][0]["error_code"] == "POST_ROUTE_ERROR"

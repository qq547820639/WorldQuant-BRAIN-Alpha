from __future__ import annotations

import logging
import os
from types import SimpleNamespace

import brain_alpha_ops.web  # noqa: F401  install meta-path bridge for web_* modules
import brain_alpha_ops.web_runtime_facade as facade
from brain_alpha_ops.web_config import public_run_config_dict
from brain_alpha_ops.web_errors import web_error_payload
from brain_alpha_ops.web_job_registry import resolve_web_job_registry


class _Collector:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _WebDouble:
    DEFAULT_FIELDS = ("close",)
    DEFAULT_OPERATORS = ("rank",)
    CLOUD_SYNC_STALE_SECONDS = 120
    DEFAULT_PORT = 8765
    HOST = "127.0.0.1"
    LOOPBACK_BIND_HOSTS = ("127.0.0.1",)
    SESSION_COOKIE_NAME = "brain_session"

    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []
        self.JOBS = {}
        self.SYNC_JOBS = {}
        self.CHECK_JOBS = {}
        self.ASYNC_JOBS = {}
        self.SUBMIT_LOCK = object()
        self.WebHandlerDispatchContext = _Collector
        self.WebDispatchCoreContext = _Collector
        self.WebDispatchSessionContext = _Collector
        self.WebDispatchJobContext = _Collector
        self.WebDispatchConfigContext = _Collector
        self.WebDispatchResearchContext = _Collector
        self.WebDispatchAssistantContext = _Collector
        self.WebDispatchActionContext = _Collector
        self.WebSnapshotRuntime = _Collector
        self.WebSnapshotFacade = _Collector
        self.runtime_project_root = "/tmp/project"
        self.SERVER = None
        self.SERVER_STOP = SimpleNamespace(wait=lambda _seconds: True)
        self.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
        self.web_html = SimpleNamespace(
            WEB_FRONTEND_ENV="BRAIN_ALPHA_OPS_WEB_FRONTEND",
            reset_html_cache=lambda: self.calls.append(("reset_html_cache", (), {})),
        )
        self.web_session = SimpleNamespace(
            DEFAULT_ADMIN_TOKEN_ENV="ADMIN_TOKEN",
            SESSION_MANAGER=SimpleNamespace(secure_cookies=False),
            set_remote_policy=lambda **kwargs: self.calls.append(("set_remote_policy", (), kwargs)),
            require_remote_admin_token=lambda: self.calls.append(("require_remote_admin_token", (), {})),
        )

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        return {"called": name}

    def __getattr__(self, name):
        def _method(*args, **kwargs):
            return self._record(name, *args, **kwargs)

        return _method


def test_runtime_facade_context_and_snapshot_factories_collect_dependencies():
    web = _WebDouble()

    ctx = facade.handler_dispatch_context(web)
    runtime = facade.snapshot_runtime(web)
    snapshots = facade.snapshot_facade(web)

    assert ctx.kwargs["core"].kwargs["route_for"] is not None
    assert ctx.kwargs["job"].kwargs["jobs"] is web.JOBS
    assert ctx.kwargs["actions"].kwargs["submit_lock"] is web.SUBMIT_LOCK
    assert runtime.kwargs["job_store"] is web.JOBS
    assert snapshots.kwargs["runtime_factory"] is not None


def test_runtime_facade_prefers_job_registry_and_honors_legacy_overrides():
    web = _WebDouble()
    registry = SimpleNamespace(
        jobs={"registry": "jobs"},
        sync_jobs={"registry": "sync"},
        check_jobs={"registry": "check"},
        async_jobs={"registry": "async"},
        submit_lock=object(),
        rate_limiter=object(),
        task_executor=object(),
    )
    web.JOB_REGISTRY = registry
    web.JOBS = registry.jobs
    web.SYNC_JOBS = registry.sync_jobs
    web.CHECK_JOBS = registry.check_jobs
    web.ASYNC_JOBS = registry.async_jobs
    web.SUBMIT_LOCK = registry.submit_lock

    ctx = facade.handler_dispatch_context(web)
    runtime = facade.snapshot_runtime(web)

    assert ctx.kwargs["job"].kwargs["jobs"] is registry.jobs
    assert ctx.kwargs["job"].kwargs["sync_jobs"] is registry.sync_jobs
    assert ctx.kwargs["job"].kwargs["check_jobs"] is registry.check_jobs
    assert ctx.kwargs["job"].kwargs["async_jobs"] is registry.async_jobs
    assert ctx.kwargs["actions"].kwargs["submit_lock"] is registry.submit_lock
    assert runtime.kwargs["job_store"] is registry.jobs
    assert resolve_web_job_registry(web).rate_limiter is registry.rate_limiter

    legacy_jobs = {"legacy": "jobs"}
    legacy_lock = object()
    web.JOBS = legacy_jobs
    web.SUBMIT_LOCK = legacy_lock

    ctx = facade.handler_dispatch_context(web)
    runtime = facade.snapshot_runtime(web)

    assert ctx.kwargs["job"].kwargs["jobs"] is legacy_jobs
    assert ctx.kwargs["actions"].kwargs["submit_lock"] is legacy_lock
    assert runtime.kwargs["job_store"] is legacy_jobs
    assert ctx.kwargs["job"].kwargs["sync_jobs"] is registry.sync_jobs


def test_runtime_facade_connection_success_and_failure(caplog):
    class API:
        def __init__(self):
            self.profile_called = False

        def authenticate(self):
            return {"auth": "token"}

        def get_user_profile(self):
            self.profile_called = True

    api = API()
    web = SimpleNamespace(
        run_config_from_payload=lambda payload: SimpleNamespace(environment="production"),
        api_from_run_config=lambda config: api,
        _web_error=lambda exc, code: {"ok": False, "error_code": code, "error": str(exc)},
    )

    assert facade.test_connection(web, {"x": 1}) == {"ok": True, "environment": "production", "auth": "token"}
    assert api.profile_called is True

    web.run_config_from_payload = lambda payload: (_ for _ in ()).throw(RuntimeError("bad config"))
    with caplog.at_level(logging.ERROR, logger="brain_alpha_ops.web_runtime_facade"):
        assert facade.test_connection(web, {})["error_code"] == "CONNECTION_FAILED"
    assert "web connection test failed" in caplog.text


def test_runtime_facade_connection_fails_when_profile_returns_auth_error():
    class API:
        def authenticate(self):
            return {"auth": "token"}

        def get_user_profile(self):
            return {
                "error": "Failed to fetch user profile: HTTP 403: Forbidden",
                "status_code": 403,
            }

    web = SimpleNamespace(
        run_config_from_payload=lambda payload: SimpleNamespace(environment="production"),
        api_from_run_config=lambda config: API(),
        _web_error=web_error_payload,
    )

    payload = facade.test_connection(web, {})

    assert payload["ok"] is False
    assert payload["error_code"] == "CONNECTION_FAILED"
    assert payload["error_category"] == "auth"
    assert payload["status_code"] == 403
    assert payload["retryable"] is False
    assert payload["error"] == "认证失败，请检查凭据或连接设置。"


def test_runtime_facade_job_selection_lookup_and_simple_delegates():
    web = _WebDouble()

    facade.run_job(web, "job_guided", {"guided": True})
    facade.run_job(web, "job_plain", {})
    assert [call[0] for call in web.calls[:2]] == ["run_guided_job_service", "run_job_service"]

    web.CHECK_JOBS["check_1"] = {"id": "check_1"}
    assert facade.lookup_sse_job(web, "check_1") == {"id": "check_1"}
    assert facade.lookup_sse_job(web, "missing") is None

    assert facade.generate_candidates_payload(web, {"count": 1})["called"] == "_generate_candidates_payload"
    assert facade.run_generate_candidates_job(web, "gen", {})["called"] == "run_simple_async_job_service"
    assert facade.run_scoring_evaluate_job(web, "score", {})["called"] == "run_simple_async_job_service"
    assert facade.lifecycle_from_job(web, {})["called"] == "_lifecycle_from_job_service"
    assert facade.cloud_alpha_snapshot(web, limit=5)["called"] == "_cloud_alpha_snapshot_service"
    assert facade.cloud_similarity_risk(web, {}, [])["called"] == "_cloud_similarity_risk"
    assert facade.load_presets(web)["called"] == "_load_presets_service"
    assert facade.match_preset_id(web, {})["called"] == "_match_preset_id_service"
    assert facade.candidate_from_payload(web, {})["called"] == "_candidate_from_payload"
    assert facade.sync_cloud_alphas(web, {})["called"] == "sync_cloud_alphas_payload"
    assert facade.run_sync_job(web, "sync", {})["called"] == "run_sync_job_service"
    assert facade.run_check_batch_job(web, "check", {})["called"] == "run_check_batch_job_service"
    assert facade.datasets_from_fields(web, [])["called"] == "_datasets_from_fields_service"
    assert facade.passed_candidates_from_payload(web, {})["called"] == "_passed_candidates_from_payload"
    assert facade.check_candidate(web, {})["called"] == "check_candidate_payload"
    assert facade.submission_preflight_error(web, {}, object())["called"] == "_submission_preflight_error_message"
    assert facade.submission_preflight_advisory(web, {}, object())["called"] == "_submission_preflight_advisory"
    assert facade.observability_submission_preflight(web, "data")["called"] == "_observability_submission_preflight"
    assert facade.submit_candidate(web, {})["called"] == "submit_candidate_payload"
    assert facade.load_check_results(web)["called"] == "_load_check_results_service"
    assert facade.submit_batch(web, {})["called"] == "submit_batch_payload"
    assert facade.storage_jsonl_path(web, "events.jsonl")["called"] == "_storage_jsonl_path_service"
    assert facade.read_storage_jsonl(web, "events.jsonl")["called"] == "_read_storage_jsonl_service"
    assert facade.read_storage_jsonl_stats(web, "events.jsonl")["called"] == "_read_storage_jsonl_stats_service"
    assert facade.find_free_port(web, 9000, "127.0.0.1")["called"] == "_find_free_port_service"
    assert facade.smoke_test_server(web, port=9000)["called"] == "_smoke_test_server_service"

    facade.maybe_archive_lifecycle(web)
    facade.refresh_cloud_context_for_check(web, object(), object(), "recent", "job", 1, "quick")
    facade.persist_official_context(web, [], [], [])
    facade.save_official_context_json(web, "fields.json", [])
    facade.record_submit_blocked(web, {}, {}, object(), "blocked")
    facade.shutdown_server(web)
    assert any(call[0] == "_shutdown_server_service" for call in web.calls)


def test_runtime_facade_public_config_redacts_credentials_and_serve_sets_policy():
    web = _WebDouble()
    web.load_run_config = lambda *args, **kwargs: SimpleNamespace(
        to_dict=lambda: {
            "credentials": {
                "username": "user",
                "password": "secret",
                "token": "token",
                "username_env": "USER_ENV",
                "password_env": "PASS_ENV",
                "token_env": "TOKEN_ENV",
            }
        },
        web=SimpleNamespace(
            admin_token_env="ADMIN_TOKEN",
            port=8765,
            open_browser=False,
            host="127.0.0.1",
            session_ttl_seconds=60,
            allow_multiple_sessions=True,
            allow_remote=False,
            secure_cookies=False,
        ),
    )
    web.configure_session_policy = lambda *args, **kwargs: web.calls.append(("configure_session_policy", args, kwargs))
    web._serve_service = lambda **kwargs: ("http://127.0.0.1:8765", "server")

    public_config = facade.public_run_config(web)
    assert public_config["credentials"] == {
        "username": "",
        "password": "",
        "token": "",
        "username_env": "USER_ENV",
        "password_env": "PASS_ENV",
        "token_env": "TOKEN_ENV",
        "managed_credentials_available": True,
    }

    url = facade.serve(web, port=8765, allow_remote=True, secure_cookies=None)
    assert url == "http://127.0.0.1:8765"
    assert web.SERVER == "server"
    assert ("require_remote_admin_token", (), {}) in web.calls


def test_public_run_config_reports_managed_credential_presence_without_values(monkeypatch):
    for key in ("BRAIN_USERNAME", "BRAIN_PASSWORD", "BRAIN_TOKEN", "USER_ENV", "PASS_ENV", "TOKEN_ENV"):
        monkeypatch.delenv(key, raising=False)

    empty_config = SimpleNamespace(
        to_dict=lambda: {
            "credentials": {
                "username_env": "USER_ENV",
                "password_env": "PASS_ENV",
                "token_env": "TOKEN_ENV",
            }
        }
    )
    redacted = public_run_config_dict(empty_config)["credentials"]
    assert redacted == {
        "username": "",
        "password": "",
        "token": "",
        "username_env": "USER_ENV",
        "password_env": "PASS_ENV",
        "token_env": "TOKEN_ENV",
        "managed_credentials_available": False,
    }

    value_config = SimpleNamespace(
        to_dict=lambda: {
            "credentials": {
                "username": "stored@example.com",
                "password": "stored-password",
                "token": "",
            }
        }
    )
    redacted = public_run_config_dict(value_config)["credentials"]
    assert redacted["managed_credentials_available"] is True
    assert redacted["username"] == ""
    assert redacted["password"] == ""
    assert redacted["token"] == ""

    env_config = SimpleNamespace(
        to_dict=lambda: {
            "credentials": {
                "username_env": "USER_ENV",
                "password_env": "PASS_ENV",
                "token_env": "TOKEN_ENV",
            }
        }
    )
    monkeypatch.setenv("USER_ENV", "env@example.com")
    monkeypatch.setenv("PASS_ENV", "env-password")
    assert public_run_config_dict(env_config)["credentials"]["managed_credentials_available"] is True

    monkeypatch.delenv("USER_ENV", raising=False)
    monkeypatch.delenv("PASS_ENV", raising=False)
    monkeypatch.setenv("TOKEN_ENV", "env-token")
    assert public_run_config_dict(env_config)["credentials"]["managed_credentials_available"] is True


def test_runtime_facade_submit_batch_job_locking_and_progress():
    class Lock:
        def __init__(self, acquired: bool):
            self.acquired = acquired
            self.released = False

        def acquire(self, blocking=False):
            return self.acquired

        def release(self):
            self.released = True

    web = _WebDouble()
    web.progress_updates = []
    web.progress_update = lambda *args, **kwargs: web.progress_updates.append((args, kwargs))
    web.safe_error_message = lambda exc: str(exc)
    web.error_payload = lambda exc: {"error": str(exc)}

    web.SUBMIT_LOCK = Lock(False)

    def run_service(job_id, payload, *, worker, **kwargs):
        return worker(payload)

    web.run_simple_async_job_service = run_service
    conflict = facade.run_submit_batch_job(web, "submit", {})
    assert conflict["error_code"] == "CONFLICT_RUNNING"

    web.SUBMIT_LOCK = Lock(True)

    def submit_batch_payload(body, *, progress_callback, **kwargs):
        progress_callback({"message": "one done", "done": 1, "total": 2, "submitted": 1, "failed": 0, "current_alpha_id": "a1"})
        return {"ok": True}

    web.submit_batch_payload = submit_batch_payload
    assert facade.run_submit_batch_job(web, "submit", {}) == {"ok": True}
    assert web.SUBMIT_LOCK.released is True
    assert web.progress_updates[0][1]["current_alpha_id"] == "a1"


def test_runtime_facade_generate_job_persists_candidates_into_summary():
    web = _WebDouble()
    saved: list[tuple[str, str, dict]] = []
    web.safe_error_message = lambda exc: str(exc)
    web.error_payload = lambda exc: {"error": str(exc)}
    web.run_config_from_payload = lambda body: SimpleNamespace(ops=SimpleNamespace(storage_dir="/tmp/data"))
    web.generate_candidates_payload = lambda body: {
        "ok": True,
        "candidates": [
            {
                "alpha_id": "alpha_web_1",
                "expression": "rank(close)",
                "family": "momentum",
                "hypothesis": "web generated candidate",
            }
        ],
        "summary": {},
    }

    def persist(job_id, run_config, result, candidate_type, repository_type):
        for row in result["candidates"]:
            saved.append((job_id, run_config.ops.storage_dir, candidate_type.from_dict(row).to_dict()))
        return {
            "schema_version": "candidate-persistence-v1",
            "target": "candidates.jsonl",
            "persisted_count": len(saved),
            "error_count": 0,
            "errors": [],
        }

    def run_service(job_id, payload, *, worker, **kwargs):
        return worker(payload)

    web._persist_generated_candidates = persist
    web.run_simple_async_job_service = run_service

    result = facade.run_generate_candidates_job(web, "job_generate", {"count": 1})

    assert saved[0][0] == "job_generate"
    assert saved[0][1] == "/tmp/data"
    assert saved[0][2]["alpha_id"] == "alpha_web_1"
    assert result["summary"]["persistence"]["persisted_count"] == 1


def test_runtime_facade_main_smoke_serve_and_keyboard_interrupt(capsys, monkeypatch):
    web = _WebDouble()
    monkeypatch.delenv("BRAIN_ALPHA_OPS_WEB_FRONTEND", raising=False)
    web.load_run_config = lambda _path=None: SimpleNamespace(
        web=SimpleNamespace(
            port=7777,
            open_browser=True,
            host="127.0.0.1",
            session_ttl_seconds=60,
            allow_multiple_sessions=False,
            allow_remote=False,
            secure_cookies=False,
        )
    )
    web.config_from_payload = lambda payload: web.calls.append(("config_from_payload", (), payload))
    web.smoke_test_server = lambda port=None: {"port": port}
    web.serve = lambda **kwargs: "http://127.0.0.1:7777"

    assert facade.main(web, ["--smoke-test", "--port", "9001", "--frontend", "react"]) == 0
    first_out = capsys.readouterr().out
    assert '"status": "web ready"' in first_out
    assert '"port": 9001' in first_out
    assert os.environ["BRAIN_ALPHA_OPS_WEB_FRONTEND"] == "react"
    assert ("reset_html_cache", (), {}) in web.calls

    assert facade.main(web, ["--smoke-test", "--port", "0"]) == 0
    zero_out = capsys.readouterr().out
    assert '"port": 0' in zero_out

    assert facade.main(web, ["--no-browser", "--frontend", "inline"]) == 0
    assert "BRAIN Alpha Ops 已启动" in capsys.readouterr().out
    assert os.environ["BRAIN_ALPHA_OPS_WEB_FRONTEND"] == "inline"

    waits = iter([False, True])
    web.SERVER_STOP = SimpleNamespace(wait=lambda _seconds: next(waits))
    assert facade.main(web, []) == 0

    shutdown_called = []
    web.SERVER_STOP = SimpleNamespace(wait=lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()))
    web.shutdown_server = lambda: shutdown_called.append(True)
    assert facade.main(web, []) == 0
    assert shutdown_called == [True]


def test_runtime_facade_main_warns_when_safe_print_fails(monkeypatch):
    web = _WebDouble()
    web.load_run_config = lambda _path=None: SimpleNamespace(
        web=SimpleNamespace(
            port=7777,
            open_browser=False,
            host="127.0.0.1",
            session_ttl_seconds=60,
            allow_multiple_sessions=False,
            allow_remote=False,
            secure_cookies=False,
        )
    )
    web.config_from_payload = lambda payload: web.calls.append(("config_from_payload", (), payload))
    web.smoke_test_server = lambda port=None: {"port": port}

    def fail_print(*_args, **_kwargs):
        raise OSError("stdout unavailable")

    warnings = []
    monkeypatch.setattr("builtins.print", fail_print)
    monkeypatch.setattr(facade.logger, "warning", lambda *args, **kwargs: warnings.append((args, kwargs)))

    assert facade.main(web, ["--smoke-test"]) == 0

    assert warnings
    assert warnings[0][0][0] == "failed to write web runtime CLI output"

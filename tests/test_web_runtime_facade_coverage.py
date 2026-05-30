from __future__ import annotations

import os
from types import SimpleNamespace

from brain_alpha_ops import web_runtime_facade as facade


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
        self.WebHandlerDispatchContext = _Collector
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

    assert ctx.kwargs["route_for"] is not None
    assert runtime.kwargs["job_store"] is web.JOBS
    assert snapshots.kwargs["runtime_factory"] is not None


def test_runtime_facade_connection_success_and_failure():
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
    assert facade.test_connection(web, {})["error_code"] == "CONNECTION_FAILED"


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
    }

    url = facade.serve(web, port=8765, allow_remote=True, secure_cookies=None)
    assert url == "http://127.0.0.1:8765"
    assert web.SERVER == "server"
    assert ("require_remote_admin_token", (), {}) in web.calls


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
    assert '"status": "web ready"' in capsys.readouterr().out
    assert os.environ["BRAIN_ALPHA_OPS_WEB_FRONTEND"] == "react"
    assert ("reset_html_cache", (), {}) in web.calls

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

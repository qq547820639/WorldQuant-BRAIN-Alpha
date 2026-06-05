from __future__ import annotations

import pytest

from brain_alpha_ops import web
from brain_alpha_ops.web_application_context import WEB_CONTEXT_ALLOWED_NAMES
from brain_alpha_ops.web_facade_bindings import build_web_facade_bindings
from brain_alpha_ops.web_legacy_exports import LEGACY_EXPORT_SPECS
from brain_alpha_ops.web_service_namespace import build_web_service_namespace
from scripts.check_web_facade_contract import check_web_facade_contract


def test_web_facade_contract_accepts_current_web_module():
    result = check_web_facade_contract()

    assert result["ok"] is True
    assert result["schema_version"] == "web_facade_contract_check.v1"
    assert result["has_context_class"] is True
    assert result["has_context_factory"] is True
    assert result["direct_sys_modules_count"] == 1
    assert result["runtime_facade_sys_modules_count"] == 0
    assert result["lambda_alias_count"] == 0
    assert result["public_brain_alpha_import_count"] == 0


def test_web_application_context_is_exposed():
    ctx = web.web_application_context()

    assert ctx is web.WEB_APPLICATION_CONTEXT
    assert ctx.JOBS is web.JOBS


def test_web_application_context_rejects_unlisted_module_attributes():
    ctx = web.web_application_context()

    with pytest.raises(AttributeError):
        getattr(ctx, "_module")
    with pytest.raises(AttributeError):
        getattr(ctx, "_allowed_names")
    with pytest.raises(AttributeError):
        getattr(ctx, "_LEGACY_IMPORTED_EXPORTS")
    with pytest.raises(AttributeError):
        getattr(ctx, "sys")


def test_web_context_allowed_names_keep_job_controls_explicit():
    assert {
        "JOB_REGISTRY",
        "JOBS",
        "SYNC_JOBS",
        "CHECK_JOBS",
        "ASYNC_JOBS",
        "SUBMIT_LOCK",
        "RATE_LIMITER",
        "TASK_EXECUTOR",
    }.issubset(WEB_CONTEXT_ALLOWED_NAMES)
    assert "_module" not in WEB_CONTEXT_ALLOWED_NAMES
    assert "_LEGACY_IMPORTED_EXPORTS" not in WEB_CONTEXT_ALLOWED_NAMES
    assert "sys" not in WEB_CONTEXT_ALLOWED_NAMES


def test_web_job_controls_are_dynamic_compatibility_exports():
    assert {
        "JOBS",
        "SYNC_JOBS",
        "CHECK_JOBS",
        "ASYNC_JOBS",
        "SUBMIT_LOCK",
        "RATE_LIMITER",
        "TASK_EXECUTOR",
    }.isdisjoint(web.__dict__)
    assert web.JOBS is web.JOB_REGISTRY.jobs
    assert web.SYNC_JOBS is web.JOB_REGISTRY.sync_jobs
    assert web.CHECK_JOBS is web.JOB_REGISTRY.check_jobs
    assert web.ASYNC_JOBS is web.JOB_REGISTRY.async_jobs
    assert web.SUBMIT_LOCK is web.JOB_REGISTRY.submit_lock
    assert web.RATE_LIMITER is web.JOB_REGISTRY.rate_limiter
    assert web.TASK_EXECUTOR is web.JOB_REGISTRY.task_executor


def test_web_dynamic_job_exports_support_from_import():
    from brain_alpha_ops.web import JOBS
    from brain_alpha_ops.web import SUBMIT_LOCK

    assert JOBS is web.JOB_REGISTRY.jobs
    assert SUBMIT_LOCK is web.JOB_REGISTRY.submit_lock


def test_web_legacy_imported_exports_keep_public_compatibility():
    assert web.RunConfig is web._RunConfig
    assert web.web_html is web._web_html
    assert web.WebJobRegistry is web._WebJobRegistry
    assert web.route_for is web._route_for
    assert web.WebDefaults is web._WebDefaults

    with pytest.raises(AttributeError):
        getattr(web, "missing_legacy_export")


def test_web_service_namespace_supplies_legacy_export_private_names():
    namespace = build_web_service_namespace()

    assert [private_name for _, private_name in LEGACY_EXPORT_SPECS if private_name not in namespace] == []
    assert [public_name for public_name, _ in LEGACY_EXPORT_SPECS if public_name in namespace] == []


def test_web_facade_bindings_install_core_public_surface():
    bindings = build_web_facade_bindings(web.__dict__)

    assert {
        "JOBS",
        "SYNC_JOBS",
        "CHECK_JOBS",
        "ASYNC_JOBS",
        "SUBMIT_LOCK",
        "RATE_LIMITER",
        "TASK_EXECUTOR",
    }.isdisjoint(bindings)
    assert bindings["Handler"].server_version == web.Handler.server_version
    assert callable(bindings["run_config_from_payload"])
    assert callable(bindings["serve"])


def test_web_application_context_builds_grouped_dispatch_context():
    ctx = web._handler_dispatch_context()

    assert isinstance(ctx.core, web.WebDispatchCoreContext)
    assert isinstance(ctx.job, web.WebDispatchJobContext)
    assert ctx.route_for is web.route_for
    assert ctx.jobs is web.JOBS


def test_web_snapshot_bindings_delegate_to_current_snapshot_facade(monkeypatch):
    class Facade:
        def research_memory_snapshot(self, **kwargs):
            return {"called": "research_memory_snapshot", "kwargs": kwargs}

        def assistant_response_parse_payload(self, payload):
            return {"called": "assistant_response_parse_payload", "payload": payload}

    monkeypatch.setattr(web, "_snapshot_facade", lambda: Facade())

    assert web.research_memory_snapshot(limit=7, top_n=2) == {
        "called": "research_memory_snapshot",
        "kwargs": {"limit": 7, "top_n": 2},
    }
    assert web.assistant_response_parse_payload({"text": "draft"}) == {
        "called": "assistant_response_parse_payload",
        "payload": {"text": "draft"},
    }


def test_web_readonly_bindings_delegate_to_current_runtime_and_providers(monkeypatch):
    ctx = web.web_application_context()
    sqlite_calls = []

    class RuntimeFacade:
        def cloud_alpha_snapshot(self, runtime_ctx, *, limit=None):
            return {"called": "cloud_alpha_snapshot", "ctx": runtime_ctx is ctx, "limit": limit}

        def read_storage_jsonl(self, runtime_ctx, filename, *, limit=500):
            return {"called": "read_storage_jsonl", "ctx": runtime_ctx is ctx, "filename": filename, "limit": limit}

        def public_run_config(self, runtime_ctx):
            return {"called": "public_run_config", "ctx": runtime_ctx is ctx}

    def sqlite_index_snapshot_service(**kwargs):
        sqlite_calls.append(kwargs)
        return {"called": "sqlite_index_snapshot"}

    monkeypatch.setattr(web, "_runtime_facade", RuntimeFacade())
    monkeypatch.setattr(web, "_load_run_config_provider", lambda: "loader")
    monkeypatch.setattr(web, "_sqlite_index_snapshot_service", sqlite_index_snapshot_service)

    assert web.cloud_alpha_snapshot(limit=3) == {"called": "cloud_alpha_snapshot", "ctx": True, "limit": 3}
    assert web._read_storage_jsonl("jobs.jsonl", limit=9) == {
        "called": "read_storage_jsonl",
        "ctx": True,
        "filename": "jobs.jsonl",
        "limit": 9,
    }
    assert web.public_run_config() == {"called": "public_run_config", "ctx": True}
    assert web.sqlite_index_snapshot(top_n=4) == {"called": "sqlite_index_snapshot"}
    assert sqlite_calls == [{"top_n": 4, "load_config": "loader", "web_error": web._web_error}]


def test_web_candidate_bindings_delegate_to_current_runtime_facade(monkeypatch):
    ctx = web.web_application_context()

    class RuntimeFacade:
        def generate_candidates_payload(self, runtime_ctx, payload):
            return {"called": "generate_candidates_payload", "ctx": runtime_ctx is ctx, "payload": payload}

        def refresh_cloud_context_for_check(
            self,
            runtime_ctx,
            api,
            repo,
            sync_range,
            job_id,
            total,
            mode,
            region,
            *,
            refresh_remote=False,
        ):
            return {
                "called": "refresh_cloud_context_for_check",
                "ctx": runtime_ctx is ctx,
                "args": [api, repo, sync_range, job_id, total, mode, region],
                "refresh_remote": refresh_remote,
            }

        def observability_submission_preflight(self, runtime_ctx, storage_dir, *, limit=5000, top_n=5):
            return {
                "called": "observability_submission_preflight",
                "ctx": runtime_ctx is ctx,
                "storage_dir": storage_dir,
                "limit": limit,
                "top_n": top_n,
            }

        def submit_candidate(self, runtime_ctx, payload):
            return {"called": "submit_candidate", "ctx": runtime_ctx is ctx, "payload": payload}

    monkeypatch.setattr(web, "_runtime_facade", RuntimeFacade())

    assert web.generate_candidates_payload({"count": 1}) == {
        "called": "generate_candidates_payload",
        "ctx": True,
        "payload": {"count": 1},
    }
    assert web.refresh_cloud_context_for_check("api", "repo", "all", "job-1", 3, "quick", "USA", refresh_remote=True) == {
        "called": "refresh_cloud_context_for_check",
        "ctx": True,
        "args": ["api", "repo", "all", "job-1", 3, "quick", "USA"],
        "refresh_remote": True,
    }
    assert web.observability_submission_preflight("data", limit=10, top_n=2) == {
        "called": "observability_submission_preflight",
        "ctx": True,
        "storage_dir": "data",
        "limit": 10,
        "top_n": 2,
    }
    assert web.submit_candidate({"alpha": "x"}) == {
        "called": "submit_candidate",
        "ctx": True,
        "payload": {"alpha": "x"},
    }


def test_web_runtime_bindings_delegate_to_current_runtime_facade(monkeypatch):
    ctx = web.web_application_context()

    class RuntimeFacade:
        def test_connection(self, runtime_ctx, payload):
            return {"called": "test_connection", "ctx": runtime_ctx is ctx, "payload": payload}

        def handler_dispatch_context(self, runtime_ctx):
            return {"called": "handler_dispatch_context", "ctx": runtime_ctx is ctx}

        def run_job(self, runtime_ctx, job_id, payload):
            return {"called": "run_job", "ctx": runtime_ctx is ctx, "job_id": job_id, "payload": payload}

        def find_free_port(self, runtime_ctx, start, host):
            return {"called": "find_free_port", "ctx": runtime_ctx is ctx, "start": start, "host": host}

        def serve(self, runtime_ctx, **kwargs):
            return {"called": "serve", "ctx": runtime_ctx is ctx, "kwargs": kwargs}

        def main(self, runtime_ctx, argv):
            return {"called": "main", "ctx": runtime_ctx is ctx, "argv": argv}

    monkeypatch.setattr(web, "_runtime_facade", RuntimeFacade())

    assert web.test_connection({"ping": True}) == {
        "called": "test_connection",
        "ctx": True,
        "payload": {"ping": True},
    }
    assert web._handler_dispatch_context() == {"called": "handler_dispatch_context", "ctx": True}
    assert web.run_job("job-1", {"guided": False}) == {
        "called": "run_job",
        "ctx": True,
        "job_id": "job-1",
        "payload": {"guided": False},
    }
    assert web.find_free_port() == {
        "called": "find_free_port",
        "ctx": True,
        "start": web.DEFAULT_PORT,
        "host": web.HOST,
    }
    assert web.serve(port=0, open_browser=False, host="127.0.0.1", allow_remote=True) == {
        "called": "serve",
        "ctx": True,
        "kwargs": {
            "port": 0,
            "open_browser": False,
            "host": "127.0.0.1",
            "session_ttl_seconds": None,
            "allow_multiple_sessions": None,
            "allow_remote": True,
            "secure_cookies": None,
        },
    }
    assert web.main(["--smoke-test"]) == {"called": "main", "ctx": True, "argv": ["--smoke-test"]}


def test_web_config_bindings_delegate_to_current_provider(monkeypatch):
    calls = []

    monkeypatch.setattr(web, "_load_run_config_provider", lambda: "loader")
    monkeypatch.setattr(
        web,
        "_run_config_from_payload",
        lambda payload, *, loader: calls.append(("run", payload, loader)) or {"run": payload, "loader": loader},
    )
    monkeypatch.setattr(
        web,
        "_config_from_payload",
        lambda payload, *, loader: calls.append(("config", payload, loader)) or {"config": payload, "loader": loader},
    )
    monkeypatch.setattr(
        web,
        "_save_run_config_payload",
        lambda payload, *, loader: calls.append(("save", payload, loader)) or {"save": payload, "loader": loader},
    )

    assert web.run_config_from_payload({"kind": "run"}) == {"run": {"kind": "run"}, "loader": "loader"}
    assert web.config_from_payload({"kind": "config"}) == {"config": {"kind": "config"}, "loader": "loader"}
    assert web.save_run_config_payload({"kind": "save"}) == {"save": {"kind": "save"}, "loader": "loader"}
    assert calls == [
        ("run", {"kind": "run"}, "loader"),
        ("config", {"kind": "config"}, "loader"),
        ("save", {"kind": "save"}, "loader"),
    ]


def test_web_session_bindings_update_public_policy_state(monkeypatch):
    class SessionModule:
        def __init__(self):
            self.configured = []

        def configure_session_policy(self, ttl_seconds, allow_multiple_sessions, secure_cookies):
            self.configured.append((ttl_seconds, allow_multiple_sessions, secure_cookies))

        def session_ttl_seconds(self):
            return 77

        def session_allow_multiple(self):
            return False

        def normalize_host(self, host, *, default_host):
            return default_host if not host else host

    session = SessionModule()
    monkeypatch.setattr(web, "web_session", session, raising=False)
    monkeypatch.setattr(web, "HOST", "127.0.0.9")

    web.configure_session_policy(77, False, True)

    assert session.configured == [(77, False, True)]
    assert web.SESSION_TTL_SECONDS == 77
    assert web.SESSION_ALLOW_MULTIPLE is False
    assert web.normalize_host("") == "127.0.0.9"


def test_web_runtime_bindings_delegate_compute_run_stats(monkeypatch):
    monkeypatch.setattr(web, "_compute_run_stats_service", lambda data, run_config: {"data": data, "run": run_config})

    assert web._compute_run_stats({"rows": 2}, "config") == {"data": {"rows": 2}, "run": "config"}


def test_web_facade_contract_rejects_runtime_facade_sys_modules(tmp_path):
    web_path = tmp_path / "web.py"
    web_path.write_text(
        """
import sys

class WebApplicationContext:
    pass

def web_application_context():
    return None

WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])
bad = lambda payload: _runtime_facade.test_connection(sys.modules[__name__], payload)
""",
        encoding="utf-8",
    )

    result = check_web_facade_contract(web_path)

    assert result["ok"] is False
    assert any(finding["code"] == "runtime_facade_sys_modules_call" for finding in result["findings"])


def test_web_facade_contract_accepts_private_imported_context_binding(tmp_path):
    web_path = tmp_path / "web.py"
    web_path.write_text(
        """
import sys
from brain_alpha_ops.web_application_context import WebApplicationContext as _WebApplicationContext

WebApplicationContext = _WebApplicationContext

def web_application_context():
    return WEB_APPLICATION_CONTEXT

WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])
""",
        encoding="utf-8",
    )

    result = check_web_facade_contract(web_path)

    assert result["ok"] is True
    assert result["has_context_class"] is True
    assert result["public_brain_alpha_import_count"] == 0


def test_web_facade_contract_rejects_public_brain_alpha_imports(tmp_path):
    web_path = tmp_path / "web.py"
    web_path.write_text(
        """
import sys
from brain_alpha_ops.web_routes import route_for

class WebApplicationContext:
    pass

def web_application_context():
    return None

WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])
""",
        encoding="utf-8",
    )

    result = check_web_facade_contract(web_path)

    assert result["ok"] is False
    assert result["public_brain_alpha_import_count"] == 1
    assert any(finding["code"] == "public_brain_alpha_import" for finding in result["findings"])

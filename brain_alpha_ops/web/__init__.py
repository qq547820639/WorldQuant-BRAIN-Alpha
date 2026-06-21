"""Local web console for BRAIN Alpha Ops.

Serves the React frontend and provides API endpoints for the complete
alpha research business loop.  See ``web_handler_dispatch.py`` (routes),
``web_handler_dispatch_core.py`` (dispatch loop), and
``web_facade_bindings.py`` (import-time facade surface) for the split.
"""

from __future__ import annotations

import json
import logging
import sys
import importlib as _importlib

# ═══════════════════════ sys.modules backward-compat aliases (Phase 3.3) ═══
# Bridge is now installed early from brain_alpha_ops/__init__.py via _web_bridge.
# Keep a redundant install call here for direct web-package imports.
from brain_alpha_ops._web_bridge import install_web_bridge as _install_web_bridge
_install_web_bridge()

import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from brain_alpha_ops.web.dispatch import web_routes as _web_routes
from brain_alpha_ops.web.misc import web_runtime_facade as _web_runtime_facade
from brain_alpha_ops.web.security import web_session as _web_session
from brain_alpha_ops.web.submissions import web_submit_readiness as _web_submit_readiness
from brain_alpha_ops.config import load_run_config as _load_run_config
from brain_alpha_ops.runtime_constants import WebDefaults as _WebDefaults
from brain_alpha_ops.web.misc.web_application_context import (
    WebApplicationContext as _WebApplicationContext,
)
from brain_alpha_ops.web.misc import web_cli as _web_cli
_serve_server = _web_cli.serve
_shutdown_server = _web_cli.shutdown_server
_smoke_test_server = _web_cli.smoke_test_server
_main_cli = _web_cli.main
from brain_alpha_ops.web.misc.web_facade_bindings import (
    build_web_facade_bindings as _build_web_facade_bindings,
)
from brain_alpha_ops.web.misc.web_html import (
    load_html as _load_html_asset,
)
from brain_alpha_ops.web.misc.web_html import (
    resolve_react_asset as _resolve_react_asset,
)
from brain_alpha_ops.web.business.web_jobs import job_get as _job_get
from brain_alpha_ops.web.business.web_jobs import job_update as _job_update
from brain_alpha_ops.web.business.web_jobs import new_job_id as _new_job_id
from brain_alpha_ops.web.dispatch.web_routes import dispatch_get as _routes_dispatch_get
from brain_alpha_ops.web.dispatch.web_routes import dispatch_post as _routes_dispatch_post
from brain_alpha_ops.web.misc.web_server_lifecycle import (
    SafeThreadingHTTPServer as _SafeThreadingHTTPServer,
)
from brain_alpha_ops.web.misc.web_server_lifecycle import (
    find_free_port as _find_free_port,
)
from brain_alpha_ops.web.misc.web_service_namespace import (
    build_web_service_namespace as _build_web_service_namespace,
)
from brain_alpha_ops.web.security.web_session import (
    DEFAULT_SESSION_TTL_SECONDS as _DEFAULT_SESSION_TTL_SECONDS,
)
from brain_alpha_ops.web.security.web_session import csrf_for_session as _csrf_for_session
from brain_alpha_ops.web.misc.web_sse import handle_sse_request as _handle_sse_request

logger = logging.getLogger(__name__)
WebApplicationContext = _WebApplicationContext

# ═══════════════════════ Server config ═══════════════════════════
HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SESSION_TTL_SECONDS = _DEFAULT_SESSION_TTL_SECONDS
SESSION_ALLOW_MULTIPLE = True
SERVER_LOCK = threading.Lock()
SERVER = None
SERVER_STOP = threading.Event()

# ═══════════════════════ Dispatch ════════════════════════════════════════
# Legacy dispatch (dispatch_get / dispatch_post / _real_* handlers) removed in Phase 3.3.
# All routing now consolidated in web_handler_dispatch.py. See REFACTORING_PLAN.md Phase 3.2.


def _run_live_submit_readiness_check() -> dict:
    return _web_submit_readiness.run_live_submit_readiness_check()


def _submit_readiness_payload() -> dict:
    return _web_submit_readiness.submit_readiness_payload(_run_live_submit_readiness_check)


def _compact_submit_readiness_payload(result: dict) -> dict:
    return _web_submit_readiness.compact_submit_readiness_payload(result)


def _counter_rows(counter: object, *, limit: int = 6) -> list[dict[str, int]]:
    return _web_submit_readiness.counter_rows(counter, limit=limit)


def _submit_readiness_next_steps(result: dict) -> list[str]:
    return _web_submit_readiness.submit_readiness_next_steps(result)


def _safe_int(value: object) -> int:
    return _web_submit_readiness.safe_int(value)


# ── Real backend handlers removed in Phase 3.3 ────────────────────────────
# All _real_* handler functions, _safe_non_submit_run_payload,
# _production_job_store, dispatch_post, and related helpers were moved
# to web_handler_dispatch.py and web_handler_dispatch_core.py.
# See REFACTORING_PLAN.md Phase 3.2-3.3.


# ═══════════════════════ Handler ═══════════════════════════════
class Handler(BaseHTTPRequestHandler):
    _MAX_BODY_BYTES = _WebDefaults.MAX_BODY_BYTES

    def log_message(self, fmt, *args):
        logger.debug(fmt, *args)

    def _session_id_from_cookie(self):
        return _web_session.session_id_from_cookie(str(self.headers.get("Cookie", "")))

    def _has_valid_session(self, query_string=""):
        csrf_header = str(
            self.headers.get("X-Brain-Alpha-CSRF", "")
            or self.headers.get("X-CSRF-Token", "")
            or self.headers.get("X-CSRF", "")
        )
        return _web_session.has_valid_request_session(
            path=urlparse(self.path).path,
            query_string=query_string,
            csrf_header=csrf_header,
            cookie_header=str(self.headers.get("Cookie", "")),
        )

    def _validate_replay_request(self):
        return _web_session.validate_replay_request(
            session_id=self._session_id_from_cookie(),
            request_id=str(self.headers.get("X-Brain-Alpha-Request-ID", "")),
            request_timestamp=str(self.headers.get("X-Brain-Alpha-Request-Timestamp", "")),
        )

    def _is_allowed_local_request(self):
        return _web_session.is_allowed_request(
            host_header=str(self.headers.get("Host", "")),
            origin_header=str(self.headers.get("Origin", "")),
            referer_header=str(self.headers.get("Referer", "")),
        )

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0:
            raise ValueError("invalid request body length")
        if length > self._MAX_BODY_BYTES:
            raise ValueError("request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _handle_sse_stream(self, query_string):
        if not self._has_valid_session(query_string):
            self._json({"ok": False, "error_code": "AUTH_REQUIRED", "error": "session required"}, status=401)
            return
        _handle_sse_request(self, parse_qs(query_string))

    def _html(self, html, *, extra_headers=None):
        self._send_html(html, extra_headers=extra_headers)

    def _json(self, payload, status=200, *, extra_headers=None):
        self._send_json(payload, status=status, extra_headers=extra_headers)
    
    def _send_security_headers(self, html=None):
        """Add standard security headers to response (P1-2: includes CSP)."""
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        # Lazy import: web_csp uses re + hashlib only, safe to import here.
        from brain_alpha_ops.web_csp import (
            content_security_policy_for_html as _csp_for_html,
        )
        self.send_header("Content-Security-Policy", _csp_for_html(html or ""))

    def _send_html(self, html, *, extra_headers=None):
        """Send HTML response with security headers."""
        body = html.encode("utf-8") if isinstance(html, str) else html
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers(html=html)
        if extra_headers:
            for name, value in extra_headers:
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload, status=200, *, extra_headers=None):
        """Send JSON response with security headers."""
        import json as _json_module
        body = _json_module.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_security_headers()
        if extra_headers:
            for name, value in extra_headers:
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

def _json_default(obj):
    """Safe JSON default for module-level dispatch helpers."""
    from datetime import date, datetime
    from decimal import Decimal
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    import logging
    logging.getLogger(__name__).warning(
        "JSON fallback: %s of type %s", repr(obj)[:100], type(obj).__name__
    )
    return repr(obj)

# ═══════════════════════ Server ═══════════════════════════════
def serve(port=None, open_browser=True, host=HOST, **kw):
    with SERVER_LOCK:
        global SERVER
        url = _serve_server(
            port=port, open_browser=open_browser, host=host,
            default_port=DEFAULT_PORT, handler_class=Handler,
            _SafeThreadingHTTPServer=_SafeThreadingHTTPServer,
            _find_free_port=_find_free_port,
            **kw,
        )
        SERVER = getattr(_serve_server, "_SERVER", None)
    return url

def shutdown_server():
    with SERVER_LOCK:
        global SERVER
        _shutdown_server(server=SERVER, server_stop=SERVER_STOP)
        SERVER = None

def smoke_test_server(port=None):
    return _smoke_test_server(port=port if port is not None else DEFAULT_PORT)

def config_from_payload(payload):
    return _load_run_config()

def load_run_config_provider():
    return _load_run_config

# ═══════════════════ Inlined from web_compat_facade.py (Phase 3.3) ═══════
# Backward-compatible facade wrappers for legacy test modules.
# Inlined to eliminate the external dependency on web_compat_facade.py.

def _load_html():
    """Backward-compatible loader: returns the inline HTML bundle."""
    from brain_alpha_ops.web_html import load_html as _load
    return _load()


def _compat_facade(func_name: str):
    """Return a lazy wrapper that delegates to binding modules."""
    def wrapper(*args, **kwargs):
        from brain_alpha_ops import web_candidate_bindings as _cand
        from brain_alpha_ops import web_config_bindings as _cfg
        from brain_alpha_ops import web_job_bindings as _job
        from brain_alpha_ops import web_session_bindings as _snap
        for mod in (_snap, _cand, _cfg, _job):
            fn = getattr(mod, func_name, None)
            if fn is not None:
                return fn(*args, **kwargs)
        raise AttributeError(f"web compatibility: {func_name} not found in binding modules")
    wrapper.__name__ = func_name
    return wrapper


_SNAPSHOT_FUNCS: list[str] = [
    "anti_overfit_snapshot", "assistant_context_snapshot",
    "assistant_cross_review_payload", "assistant_guidance_snapshot",
    "assistant_request_snapshot", "assistant_response_guidance_payload",
    "assistant_response_parse_payload", "cloud_alpha_snapshot",
    "generate_candidates_payload", "passed_candidates_from_payload",
    "public_run_config", "research_memory_snapshot",
    "research_observability_snapshot", "rolling_validation_snapshot",
    "save_assistant_guidance_payload", "sqlite_expression_lookup_payload",
    "sqlite_index_snapshot", "sqlite_record_lookup_payload",
]


def _install_compat_facades(module_globals: dict) -> None:
    """Install backward-compatible wrapper functions into the caller's module namespace."""
    for name in _SNAPSHOT_FUNCS:
        module_globals[name] = _compat_facade(name)


def _get_snapshot_export_names() -> list[str]:
    """Return the list of snapshot function names for __all__ exports."""
    return [n for n in _SNAPSHOT_FUNCS if n != "_load_html"]


_install_compat_facades(locals())


# ═══════════════════ Inlined from web_legacy_exports.py (Phase 3.3) ═══════
_LEGACY_EXPORT_SPECS = (
    ("RunConfig", "_RunConfig"),
    ("load_run_config", "_load_run_config"),
    ("runtime_project_root", "_runtime_project_root"),
    ("payload_truthy", "_payload_truthy"),
    ("public_config_schema", "_public_config_schema"),
    ("web_html", "_web_html"),
    ("DEFAULT_FIELDS", "_DEFAULT_FIELDS"),
    ("DEFAULT_OPERATORS", "_DEFAULT_OPERATORS"),
    ("tail_text_lines", "_tail_text_lines_service"),
    ("error_payload", "_error_payload"),
    ("ThreadTaskExecutor", "_ThreadTaskExecutor"),
    ("WebJobRegistry", "_WebJobRegistry"),
    ("build_research_observability_snapshot", "_build_research_observability_snapshot"),
    ("ResearchRepository", "_ResearchRepository"),
    ("SubmissionLedger", "_SubmissionLedger"),
    ("api_from_run_config", "_api_from_run_config"),
    ("run_pipeline_from_config", "_run_pipeline_from_config"),
    ("DurableJobStore", "_DurableJobStore"),
    ("run_check_batch_job_service", "_run_check_batch_job_service"),
    ("check_candidate_payload", "_check_candidate_payload"),
    ("candidate_official_metrics", "_candidate_official_metrics"),
    ("is_passed_candidate_for_check", "_is_passed_candidate_for_check"),
    ("official_alpha_id", "_official_alpha_id"),
    ("refresh_cloud_context_for_check_service", "_refresh_cloud_context_for_check_service"),
    ("active_job_payload", "_active_job_payload"),
    ("health_payload", "_health_payload"),
    ("job_status_payload", "_job_status_payload"),
    ("lifecycle_payload", "_lifecycle_payload"),
    ("presets_payload", "_presets_payload"),
    ("profile_payload", "_profile_payload"),
    ("assistant_response_guidance_post_payload", "_assistant_response_guidance_post_payload"),
    ("assistant_response_parse_post_payload", "_assistant_response_parse_post_payload"),
    ("background_job_start_payload", "_background_job_start_payload"),
    ("connection_test_post_payload", "_connection_test_post_payload"),
    ("save_assistant_guidance_post_payload", "_save_assistant_guidance_post_payload"),
    ("session_end_payload", "_session_end_payload"),
    ("stop_job_payload", "_stop_job_payload"),
    ("RequestRateLimiter", "_RequestRateLimiter"),
    ("WebDispatchActionContext", "_WebDispatchActionContext"),
    ("WebDispatchAssistantContext", "_WebDispatchAssistantContext"),
    ("WebDispatchConfigContext", "_WebDispatchConfigContext"),
    ("WebDispatchCoreContext", "_WebDispatchCoreContext"),
    ("WebDispatchJobContext", "_WebDispatchJobContext"),
    ("WebDispatchResearchContext", "_WebDispatchResearchContext"),
    ("WebDispatchSessionContext", "_WebDispatchSessionContext"),
    ("WebHandlerDispatchContext", "_WebHandlerDispatchContext"),
    ("dispatch_get", "_dispatch_get"),
    ("dispatch_post", "_dispatch_post"),
    ("create_handler_class", "_create_handler_class"),
    ("route_for", "_route_for"),
    ("progress_update", "_progress_update"),
    ("run_simple_async_job_service", "_run_simple_async_job_service"),
    ("run_guided_job_service", "_run_guided_job_service"),
    ("run_job_service", "_run_job_service"),
    ("web_session", "_web_session"),
    ("WebSnapshotFacade", "_WebSnapshotFacade"),
    ("WebSnapshotRuntime", "_WebSnapshotRuntime"),
    ("DEFAULT_SESSION_TTL_SECONDS", "_DEFAULT_SESSION_TTL_SECONDS"),
    ("LOOPBACK_BIND_HOSTS", "_LOOPBACK_BIND_HOSTS"),
    ("SESSION_COOKIE_NAME", "_SESSION_COOKIE_NAME"),
    ("submit_batch_payload", "_submit_batch_payload"),
    ("submit_candidate_payload", "_submit_candidate_payload"),
    ("run_sync_job_service", "_run_sync_job_service"),
    ("sync_cloud_alphas_payload", "_sync_cloud_alphas_payload"),
    ("CloudDefaults", "_CloudDefaults"),
    ("WebDefaults", "_WebDefaults"),
    ("SnapshotDefaults", "_SnapshotDefaults"),
)


def _build_legacy_imported_exports(namespace: dict) -> dict:
    """Build the legacy exports lookup from module namespace (inlined from web_legacy_exports.py)."""
    return {public_name: namespace[private_name] for public_name, private_name in _LEGACY_EXPORT_SPECS}


def _install_facade_bindings() -> None:
    """Install three distinct facade surfaces into this module's globals.

    Three surfaces coexist on purpose (P1-6 doc — do NOT consolidate):

    1. ``web_service_namespace.build_web_service_namespace`` (legacy
       import-time facade): provides backwards-compatible top-level symbols
       for tests and external scripts that historically did
       ``from brain_alpha_ops.web import X``.

    2. ``web_runtime_facade``: lazy runtime facade used by
       ``web_service_namespace`` for ``compute_run_stats`` and
       ``status_category``; not intended to be the production dispatch path.

    3. ``web_facade_bindings.build_web_facade_bindings``: extended facade
       used by the factory ``Handler`` defined in ``web_http_handler.py``
       for the (latent) alt-dispatch path.  Production dispatch is still
       the in-line ``Handler`` defined in this module (the factory is
       reserved for future enablement).

    See ``web_handler_dispatch.py`` for the route table and
    ``web_handler_dispatch_core.py`` for the dispatch loop.
    """
    try:
        namespace = _build_web_service_namespace()
        globals().update(namespace)
        globals()["_runtime_facade"] = _web_runtime_facade
        globals().update(_build_web_facade_bindings(globals()))
        globals()["_LEGACY_IMPORTED_EXPORTS"] = _build_legacy_imported_exports(globals())
    except Exception as e:
        from brain_alpha_ops.redaction import redact_error_message; logger.error("Facade bindings install failed: %s", redact_error_message(e))


def web_application_context():
    return WEB_APPLICATION_CONTEXT


def _app_context():
    return WEB_APPLICATION_CONTEXT


# Pre-declared for mypy — populated by _install_facade_bindings() below.
JOB_REGISTRY: object = None  # type: ignore[assignment]
_LEGACY_IMPORTED_EXPORTS: object = {}  # type: ignore[assignment]

def __getattr__(name: str):
    if name == "JOBS":
        return JOB_REGISTRY.jobs
    if name == "SYNC_JOBS":
        return JOB_REGISTRY.sync_jobs
    if name == "CHECK_JOBS":
        return JOB_REGISTRY.check_jobs
    if name == "ASYNC_JOBS":
        return JOB_REGISTRY.async_jobs
    if name == "SUBMIT_LOCK":
        return JOB_REGISTRY.submit_lock
    if name == "RATE_LIMITER":
        return JOB_REGISTRY.rate_limiter
    if name == "TASK_EXECUTOR":
        return JOB_REGISTRY.task_executor
    if name == "_backtest_slots_payload":
        from brain_alpha_ops.web_backtest_slots import backtest_slots_payload
        return backtest_slots_payload
    legacy = _LEGACY_IMPORTED_EXPORTS.get(name)
    if legacy is not None:
        return legacy
    raise AttributeError(name)

def main(argv=None):
    return _main_cli(
        argv=argv, serve_fn=serve, shutdown_fn=shutdown_server,
        host=HOST, server_stop=SERVER_STOP,
    )

_install_facade_bindings()
WEB_APPLICATION_CONTEXT = WebApplicationContext(sys.modules[__name__])

_snapshot_exports = _get_snapshot_export_names()
__all__ = ["Handler", "main", "serve", "shutdown_server", "smoke_test_server",
           "find_free_port",
           "HOST", "DEFAULT_PORT", "SERVER", "SERVER_STOP", "SERVER_LOCK",
           "SESSION_TTL_SECONDS", "SESSION_ALLOW_MULTIPLE",
           "load_run_config_provider", "config_from_payload", "_load_html",
           *_snapshot_exports]

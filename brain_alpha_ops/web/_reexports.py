"""Re-exports and bootstrap logic for ``brain_alpha_ops.web``.

This module hosts the bulk of the web package's import-time re-export
aggregation plus the legacy ``Handler`` / ``serve`` / ``shutdown_server``
implementation that is overwritten by ``_install_facade_bindings`` at
package import time.  Keeping it here lets ``brain_alpha_ops/web/__init__.py``
stay a thin entry point that only runs the side effects which must
operate on the package's own namespace (facade install +
``WEB_APPLICATION_CONTEXT``).

The package-level ``__getattr__``, ``web_application_context``,
``_install_facade_bindings``, and ``WEB_APPLICATION_CONTEXT`` remain in
``__init__.py`` because they depend on ``brain_alpha_ops.web``'s own
globals or are required by the web facade contract check.
"""

from __future__ import annotations

import importlib as _importlib  # noqa: F401
import json
import logging
import os as _os
import sys  # noqa: F401
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# ═══════════════════════ sys.modules backward-compat aliases (Phase 3.3) ═══
# Bridge is installed early from brain_alpha_ops/__init__.py via _web_bridge.
# Keep a redundant install call here for direct web-package imports.
from brain_alpha_ops._web_bridge import install_web_bridge as _install_web_bridge
_install_web_bridge()

from brain_alpha_ops.web.dispatch import web_routes as _web_routes  # noqa: F401
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
    load_html as _load_html_asset,  # noqa: F401
)
from brain_alpha_ops.web.misc.web_html import (
    resolve_react_asset as _resolve_react_asset,  # noqa: F401
)
from brain_alpha_ops.web.business.web_jobs import job_get as _job_get  # noqa: F401
from brain_alpha_ops.web.business.web_jobs import job_update as _job_update  # noqa: F401
from brain_alpha_ops.web.business.web_jobs import new_job_id as _new_job_id  # noqa: F401
from brain_alpha_ops.web.dispatch.web_routes import dispatch_get as _routes_dispatch_get  # noqa: F401
from brain_alpha_ops.web.dispatch.web_routes import dispatch_post as _routes_dispatch_post  # noqa: F401
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
from brain_alpha_ops.web.security.web_session import csrf_for_session as _csrf_for_session  # noqa: F401
from brain_alpha_ops.web.misc.web_sse import handle_sse_request as _handle_sse_request

# Hardcode logger name to ``brain_alpha_ops.web`` so it matches the original
# semantics where ``__name__`` in ``__init__.py`` was ``brain_alpha_ops.web``.
logger = logging.getLogger("brain_alpha_ops.web")

# ═══════════════════════ Server config ═══════════════════════════
HOST = _os.environ.get("WEB_HOST", "127.0.0.1")
DEFAULT_PORT = 8765
SESSION_TTL_SECONDS = _DEFAULT_SESSION_TTL_SECONDS
SESSION_ALLOW_MULTIPLE = True
SERVER_LOCK = threading.Lock()
SERVER = None
SERVER_STOP = threading.Event()


# ═══════════════════════ Dispatch helpers ══════════════════════════════════
# NOTE: ``_run_live_submit_readiness_check`` / ``_submit_readiness_payload`` /
# ``_compact_submit_readiness_payload`` are intentionally NOT defined here.
# They live in ``__init__.py`` so that ``monkeypatch.setattr(web,
# "_run_live_submit_readiness_check", ...)`` is observed by
# ``web._submit_readiness_payload()`` (which looks up the name through
# ``brain_alpha_ops.web``'s globals, not this module's).
def _counter_rows(counter: object, *, limit: int = 6) -> list[dict[str, int]]:
    return _web_submit_readiness.counter_rows(counter, limit=limit)


def _submit_readiness_next_steps(result: dict) -> list[str]:
    return _web_submit_readiness.submit_readiness_next_steps(result)


def _safe_int(value: object) -> int:
    return _web_submit_readiness.safe_int(value)


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
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (ValueError, TypeError):
            length = 0
        length = min(length, self._MAX_BODY_BYTES)
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
    logging.getLogger("brain_alpha_ops.web").warning(
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


# Install compat facade wrappers into this module's namespace so that
# ``from ._reexports import *`` re-exports them on ``brain_alpha_ops.web``.
_install_compat_facades(locals())


def main(argv=None):
    return _main_cli(
        argv=argv, serve_fn=serve, shutdown_fn=shutdown_server,
        host=HOST, server_stop=SERVER_STOP,
    )

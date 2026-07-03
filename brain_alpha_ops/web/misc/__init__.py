"""Miscellaneous web modules: CLI, HTML, SSE, errors, facades, etc."""
from __future__ import annotations


def __getattr__(name: str):
    if name in _MISC_LAZY:
        module_name, attr = _MISC_LAZY[name]
        import importlib
        mod = importlib.import_module(module_name, __package__)
        result = getattr(mod, attr)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_MISC_LAZY: dict[str, tuple[str, str]] = {
    # web_cli.py (merged into web_sse.py)
    "main": (".web_sse", "main"),
    "serve": (".web_sse", "serve"),
    "shutdown_server": (".web_sse", "shutdown_server"),
    "smoke_test_server": (".web_sse", "smoke_test_server"),
    # web_html.py (merged into web_errors.py)
    "load_html": (".web_errors", "load_html"),
    "resolve_react_asset": (".web_errors", "resolve_react_asset"),
    # web_sse.py
    "handle_sse_request": (".web_sse", "handle_sse_request"),
    # web_errors.py
    "error_payload": (".web_errors", "web_error_payload"),
    # web_rate_limit.py (merged into web_errors.py)
    "RateLimitPolicy": (".web_errors", "RateLimitPolicy"),
    "RequestRateLimiter": (".web_errors", "RequestRateLimiter"),
    # web_facade_bindings.py
    "build_web_facade_bindings": (".web_facade_bindings", "build_web_facade_bindings"),
    # web_service_namespace.py
    "build_web_service_namespace": (".web_service_namespace", "build_web_service_namespace"),
    # web_server_lifecycle.py (merged into web_payload_validation.py)
    "SafeThreadingHTTPServer": (".web_payload_validation", "SafeThreadingHTTPServer"),
    "find_free_port": (".web_payload_validation", "find_free_port"),
    # web_application_context.py (deleted; source is web_dispatch_context)
    "WebApplicationContext": ("brain_alpha_ops.web_dispatch_context", "WebApplicationContext"),
}

__all__ = list(_MISC_LAZY.keys())

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
    # web_cli.py
    "main": (".web_cli", "main"),
    "serve": (".web_cli", "serve"),
    "shutdown_server": (".web_cli", "shutdown_server"),
    "smoke_test_server": (".web_cli", "smoke_test_server"),
    # web_html.py
    "load_html": (".web_html", "load_html"),
    "resolve_react_asset": (".web_html", "resolve_react_asset"),
    # web_sse.py
    "handle_sse_request": (".web_sse", "handle_sse_request"),
    # web_errors.py
    "error_payload": (".web_errors", "error_payload"),
    # web_rate_limit.py
    "RateLimitPolicy": (".web_rate_limit", "RateLimitPolicy"),
    "RequestRateLimiter": (".web_rate_limit", "RequestRateLimiter"),
    # web_facade_bindings.py
    "build_web_facade_bindings": (".web_facade_bindings", "build_web_facade_bindings"),
    # web_service_namespace.py
    "build_web_service_namespace": (".web_service_namespace", "build_web_service_namespace"),
    # web_server_lifecycle.py
    "SafeThreadingHTTPServer": (".web_server_lifecycle", "SafeThreadingHTTPServer"),
    "find_free_port": (".web_server_lifecycle", "find_free_port"),
    # web_application_context.py
    "WebApplicationContext": (".web_application_context", "WebApplicationContext"),
}

__all__ = list(_MISC_LAZY.keys())

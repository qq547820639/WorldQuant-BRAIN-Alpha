"""HTTP dispatch, routing, handler factory, and context modules."""
from __future__ import annotations

# Lazy re-exports for backward compatibility.
# All modules accessible via brain_alpha_ops.web.dispatch.<name>


def __getattr__(name: str):
    if name in _DISPATCH_LAZY:
        module_name, attr = _DISPATCH_LAZY[name]
        import importlib
        mod = importlib.import_module(module_name, __package__)
        result = getattr(mod, attr)
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_DISPATCH_LAZY: dict[str, tuple[str, str]] = {
    # web_handler_dispatch.py
    "dispatch_get": (".web_handler_dispatch", "dispatch_get"),
    "dispatch_post": (".web_handler_dispatch", "dispatch_post"),
    "WebHandlerDispatchContext": (".web_handler_dispatch", "WebHandlerDispatchContext"),
    "POST_DISPATCH_HANDLERS": (".web_handler_dispatch", "_POST_DISPATCH_HANDLERS"),
    "GET_DISPATCH_HANDLERS": (".web_handler_dispatch", "_GET_DISPATCH_HANDLERS"),
    # web_http_handler.py
    "create_handler_class": (".web_http_handler", "create_handler_class"),
    # web_routes.py
    "Route": (".web_routes", "Route"),
    "GET_ROUTES": (".web_routes", "GET_ROUTES"),
    "POST_ROUTES": (".web_routes", "POST_ROUTES"),
    "route_for": (".web_routes", "route_for"),
    # web_handler_dispatch_core.py
    "dispatch_route": (".web_handler_dispatch_core", "dispatch_route"),
    "error_response": (".web_handler_dispatch_core", "error_response"),
    "rate_limit_key": (".web_handler_dispatch_core", "rate_limit_key"),
    "apply_rate_limit": (".web_handler_dispatch_core", "apply_rate_limit"),
    # web_handler_candidate_routes.py
    "get_candidates": (".web_handler_candidate_routes", "get_candidates"),
    "candidate_ledger_summary": (".web_handler_candidate_routes", "candidate_ledger_summary"),
    "candidate_ledger_rows": (".web_handler_candidate_routes", "candidate_ledger_rows"),
    "candidate_lifecycle_rows": (".web_handler_candidate_routes", "candidate_lifecycle_rows"),
    "candidate_target_pool_size": (".web_handler_candidate_routes", "candidate_target_pool_size"),
    "latest_async_candidates": (".web_handler_candidate_routes", "latest_async_candidates"),
    # web_get_handlers.py
    "active_job_payload": (".web_get_handlers", "active_job_payload"),
    "job_status_payload": (".web_get_handlers", "job_status_payload"),
    "lifecycle_payload": (".web_get_handlers", "lifecycle_payload"),
    "health_payload": (".web_get_handlers", "health_payload"),
    "profile_payload": (".web_get_handlers", "profile_payload"),
    "presets_payload": (".web_get_handlers", "presets_payload"),
    # web_post_handlers.py
    "stop_job_payload": (".web_post_handlers", "stop_job_payload"),
    "background_job_start_payload": (".web_post_handlers", "background_job_start_payload"),
    "connection_test_post_payload": (".web_post_handlers", "connection_test_post_payload"),
    "assistant_response_parse_post_payload": (".web_post_handlers", "assistant_response_parse_post_payload"),
    "assistant_response_guidance_post_payload": (".web_post_handlers", "assistant_response_guidance_post_payload"),
    "save_assistant_guidance_post_payload": (".web_post_handlers", "save_assistant_guidance_post_payload"),
    "session_end_payload": (".web_post_handlers", "session_end_payload"),
    # web_dispatch_context.py
    "WebApplicationContext": (".web_dispatch_context", "WebApplicationContext"),
    "WebDispatchCoreContext": (".web_dispatch_context", "WebDispatchCoreContext"),
    "WebDispatchSessionContext": (".web_dispatch_context", "WebDispatchSessionContext"),
    "WebDispatchJobContext": (".web_dispatch_context", "WebDispatchJobContext"),
    "WebDispatchConfigContext": (".web_dispatch_context", "WebDispatchConfigContext"),
    "WebDispatchResearchContext": (".web_dispatch_context", "WebDispatchResearchContext"),
    "WebDispatchAssistantContext": (".web_dispatch_context", "WebDispatchAssistantContext"),
    "WebDispatchActionContext": (".web_dispatch_context", "WebDispatchActionContext"),
}

__all__ = list(_DISPATCH_LAZY.keys())

"""Route metadata for the local web API."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WebRoute:
    method: str
    path: str
    handler: str
    requires_session: bool = True
    category: str = "api"


GET_ROUTES = {
    route.path: route
    for route in [
        WebRoute("GET", "/", "root", requires_session=False, category="html"),
        WebRoute("GET", "/api/status", "status"),
        WebRoute("GET", "/api/config", "config"),
        WebRoute("GET", "/api/active_job", "active_job"),
        WebRoute("GET", "/api/latest_result", "latest_result"),
        WebRoute("GET", "/api/health", "health", requires_session=False),
        WebRoute("GET", "/api/stream", "stream"),
        WebRoute("GET", "/api/lifecycle", "lifecycle"),
        WebRoute("GET", "/api/cloud_alphas", "cloud_alphas"),
        WebRoute("GET", "/api/research_memory", "research_memory"),
        WebRoute("GET", "/api/research_knowledge", "research_knowledge"),
        WebRoute("GET", "/api/research_observability", "research_observability"),
        WebRoute("GET", "/api/prompt_runs", "prompt_runs"),
        WebRoute("GET", "/api/sqlite_indexes", "sqlite_indexes"),
        WebRoute("GET", "/api/sqlite_expression_lookup", "sqlite_expression_lookup"),
        WebRoute("GET", "/api/sqlite_record_lookup", "sqlite_record_lookup"),
        WebRoute("GET", "/api/assistant_context", "assistant_context"),
        WebRoute("GET", "/api/assistant_guidance", "assistant_guidance"),
        WebRoute("GET", "/api/assistant_request", "assistant_request"),
        WebRoute("GET", "/api/anti_overfit", "anti_overfit"),
        WebRoute("GET", "/api/rolling_validation", "rolling_validation"),
        WebRoute("GET", "/api/sync_status", "sync_status"),
        WebRoute("GET", "/api/check_status", "check_status"),
        WebRoute("GET", "/api/check_results", "check_results"),
        WebRoute("GET", "/api/profile", "profile"),
        WebRoute("GET", "/api/presets", "presets"),
        WebRoute("GET", "/api/redline/report", "redline_report"),
        WebRoute("GET", "/api/scoring/health", "scoring_health"),
        WebRoute("GET", "/api/checkpoint/status", "checkpoint_status"),
    ]
}


POST_ROUTES = {
    route.path: route
    for route in [
        WebRoute("POST", "/api/run", "run"),
        WebRoute("POST", "/api/test_connection", "test_connection"),
        WebRoute("POST", "/api/stop", "stop"),
        WebRoute("POST", "/api/sync_alphas", "sync_alphas"),
        WebRoute("POST", "/api/check", "check"),
        WebRoute("POST", "/api/generate_candidates", "generate_candidates"),
        WebRoute("POST", "/api/check_batch", "check_batch"),
        WebRoute("POST", "/api/submit", "submit"),
        WebRoute("POST", "/api/submit_batch", "submit_batch"),
        WebRoute("POST", "/api/assistant_response/parse", "assistant_response_parse"),
        WebRoute("POST", "/api/assistant_response/guidance", "assistant_response_guidance"),
        WebRoute("POST", "/api/assistant_cross_review", "assistant_cross_review"),
        WebRoute("POST", "/api/assistant_guidance", "assistant_guidance"),
        WebRoute("POST", "/api/logout", "logout"),
        WebRoute("POST", "/api/shutdown", "shutdown"),
        WebRoute("POST", "/api/scoring/evaluate", "scoring_evaluate"),
        WebRoute("POST", "/api/scoring/attribution", "scoring_attribution"),
    ]
}


ROUTES_BY_METHOD = {
    "GET": GET_ROUTES,
    "POST": POST_ROUTES,
}


def route_for(method: str, path: str) -> WebRoute | None:
    return ROUTES_BY_METHOD.get(str(method or "").upper(), {}).get(path)


def is_known_route(method: str, path: str) -> bool:
    return route_for(method, path) is not None

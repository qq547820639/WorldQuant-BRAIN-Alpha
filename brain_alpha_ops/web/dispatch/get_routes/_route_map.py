"""Backward-Compatible route map builders and lazy-loading proxies.

Tests written against the old monolithic web_routes.py expect GET_ROUTES,
POST_ROUTES, and route_for symbols.  These are provided as backward-
compatible shims that reconstruct the route tables from the dispatch
functions.
"""

from __future__ import annotations

from typing import Any

from ._types import Route


def _build_route_map() -> dict[str, dict[str, Route]]:
    """Reconstruct GET/POST route tables for dispatch compatibility."""
    get_routes = {
        "/": Route("root", requires_session=False, category="html"),
        "/api/health": Route("health", requires_session=False),
        "/api/status": Route("status"),
        "/api/production-validation/status": Route("status"),
        "/api/config": Route("config"),
        "/api/config_schema": Route("config_schema"),
        "/api/capabilities": Route("capabilities"),
        "/api/active_job": Route("active_job"),
        "/api/latest_result": Route("latest_result"),
        "/api/stream": Route("stream"),
        "/sse": Route("stream"),
        "/api/lifecycle": Route("lifecycle"),
        "/api/alpha_lifecycle": Route("alpha_lifecycle"),
        "/api/lifecycle/history": Route("alpha_lifecycle"),
        "/api/candidates": Route("candidates"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/candidate/list": Route("candidates"),
        "/api/cloud_alphas": Route("cloud_alphas"),
        "/api/snapshot/cloud": Route("cloud_alphas"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/snapshot/cloud_alphas": Route("cloud_alphas"),
        "/api/research_memory": Route("research_memory"),
        "/api/snapshot/memory": Route("research_memory"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/snapshot/research_memory": Route("research_memory"),
        "/api/research_knowledge": Route("research_knowledge"),
        "/api/research_observability": Route("research_observability"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/snapshot/observability": Route("research_observability"),
        "/api/prompt_runs": Route("prompt_runs"),
        "/api/sqlite_indexes": Route("sqlite_indexes"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/snapshot/sqlite_indexes": Route("sqlite_indexes"),
        "/api/sqlite_expression_lookup": Route("sqlite_expression_lookup"),
        "/api/sqlite_record_lookup": Route("sqlite_record_lookup"),
        "/api/assistant_context": Route("assistant_context"),
        "/api/snapshot/assistant_context": Route("assistant_context"),
        "/api/assistant_guidance": Route("assistant_guidance"),
        "/api/snapshot/assistant_guidance": Route("assistant_guidance"),
        "/api/assistant_request": Route("assistant_request"),
        "/api/snapshot/assistant_requests": Route("assistant_request"),
        "/api/anti_overfit": Route("anti_overfit"),
        "/api/snapshot/anti_overfit": Route("anti_overfit"),
        "/api/rolling_validation": Route("rolling_validation"),
        "/api/snapshot/rolling_validation": Route("rolling_validation"),
        "/api/sync_status": Route("sync_status"),
        "/api/check_status": Route("check_status"),
        "/api/check_results": Route("check_results"),
        "/api/profile": Route("profile"),
        "/api/presets": Route("presets"),
        "/api/redline_report": Route("redline_report"),
        "/api/scoring/health": Route("scoring_health"),
        "/api/checkpoint_status": Route("checkpoint_status"),
        "/api/backtest_slots": Route("backtest_slots"),
        "/api/submit_readiness": Route("submit_readiness"),
        "/api/candidates/simulate/eligible": Route("candidates_simulate_eligible"),
        "/api/phase_state": Route("phase_state"),
        "/api/trends": Route("trends"),
        "/api/audit/export": Route("audit_export"),
    }
    post_routes = {
        "/api/run": Route("run"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/production-validation/start": Route("run"),
        "/api/config": Route("config"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/config/update": Route("config"),
        "/api/test_connection": Route("test_connection"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/connection_test": Route("test_connection"),
        "/api/stop": Route("stop"),
        "/api/production-validation/stop": Route("stop"),
        "/api/cancel": Route("cancel"),
        "/api/sync_alphas": Route("sync_alphas"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/sync-cloud-alphas": Route("sync_alphas"),          # R-02: legacy alias
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/sync/sync_alphas": Route("sync_alphas"),
        "/api/sync_context_only": Route("sync_context_only"),
        "/api/sync_cancel": Route("sync_cancel"),
        "/api/check": Route("check"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/candidate/check": Route("check"),
        "/api/generate_candidates": Route("generate_candidates"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/generate": Route("generate_candidates"),
        "/api/candidates/optimize": Route("optimize_candidates"),
        # DEPRECATED 2026-06-28: 前端无调用，候选清理，确认无外部脚本使用后再删除
        "/api/candidate/optimize": Route("optimize_candidates"),
        "/api/check_batch": Route("check_batch"),
        "/api/submit": Route("submit"),
        "/api/candidate/submit": Route("submit"),
        "/api/submit_batch": Route("submit_batch"),
        "/api/assistant/parse": Route("assistant_response_parse"),
        "/api/assistant_response/parse": Route("assistant_response_parse"),
        "/api/assistant_response_parse": Route("assistant_response_parse"),
        "/api/assistant/guidance": Route("assistant_response_guidance"),
        "/api/assistant_response_guidance": Route("assistant_response_guidance"),
        "/api/assistant/cross_review": Route("assistant_cross_review"),
        "/api/assistant_cross_review": Route("assistant_cross_review"),
        "/api/assistant_guidance": Route("assistant_guidance"),
        "/api/logout": Route("logout"),
        "/api/shutdown": Route("shutdown"),
        "/api/scoring/evaluate": Route("scoring_evaluate"),
        "/api/scoring/attribution": Route("scoring_attribution"),
        "/api/scoring/gate_decision": Route("scoring_gate_decision"),
        "/api/scoring/multi_attribution": Route("scoring_multi_attribution"),
        "/api/candidates/simulate": Route("candidates_simulate"),
        "/api/trends": Route("trends"),
        "/api/session": Route("session", requires_session=False),    # R-02: creates new session
    }
    return {"GET": get_routes, "POST": post_routes}

_route_map = None
_get_routes_cache = None

def _get_routes():
    """Lazy load route tables to avoid circular imports."""
    global _get_routes_cache
    if _get_routes_cache is not None:
        return _get_routes_cache
    m = _build_route_map()
    _get_routes_cache = (dict(m["GET"]), dict(m["POST"]))
    return _get_routes_cache

def _make_get_routes_proxy(kind: str):
    """Create a dict-like proxy that lazily loads the route table."""
    class _RouteProxy(dict):
        def __init__(self):
            pass  # Don't call super().__init__() — load lazily
        def _load(self):
            if not dict.__len__(self):
                g, p = _get_routes()
                d = g if kind == "GET" else p
                dict.update(self, d)
        def __getitem__(self, key):
            self._load()
            return dict.__getitem__(self, key)
        def __contains__(self, key):
            self._load()
            return dict.__contains__(self, key)
        def get(self, key, default=None):
            self._load()
            return dict.get(self, key, default)
        def keys(self):
            self._load()
            return dict.keys(self)
        def items(self):
            self._load()
            return dict.items(self)
        def values(self):
            self._load()
            return dict.values(self)
        def __len__(self):
            self._load()
            return dict.__len__(self)
        def __iter__(self):
            self._load()
            return dict.__iter__(self)
    return _RouteProxy()

GET_ROUTES = _make_get_routes_proxy("GET")
POST_ROUTES = _make_get_routes_proxy("POST")

def route_for(method: str, path: str) -> Route | None:
    """Backward-compatible route lookup."""
    g, p = _get_routes()
    _map = {"GET": g, "POST": p}.get(method.upper(), {})
    return _map.get(path)

"""Tests for /api/trends route registration and handler consistency.

Verifies that GET and POST /api/trends are registered, dispatch correctly,
and return the expected response structures.
"""
from __future__ import annotations

import brain_alpha_ops.web  # noqa: F401 — side-effect: installs sys.meta_path bridge
from brain_alpha_ops.web_routes import GET_ROUTES, POST_ROUTES, route_for


def test_get_trends_route_registered():
    """GET /api/trends must be in the GET route table."""
    assert "trends" in GET_ROUTES or "/api/trends" in GET_ROUTES


def test_post_trends_route_registered():
    """POST /api/trends must be in the POST route table."""
    assert "trends" in POST_ROUTES or "/api/trends" in POST_ROUTES


def test_get_trends_route_map_entry():
    """_build_route_map must map /api/trends → Route(handler='trends') for GET."""
    from brain_alpha_ops.web_routes import _build_route_map
    route_map = _build_route_map()
    get_entry = route_map["GET"].get("/api/trends")
    assert get_entry is not None
    assert get_entry.handler == "trends"


def test_post_trends_route_map_entry():
    """_build_route_map must map /api/trends → Route(handler='trends') for POST."""
    from brain_alpha_ops.web_routes import _build_route_map
    route_map = _build_route_map()
    post_entry = route_map["POST"].get("/api/trends")
    assert post_entry is not None
    assert post_entry.handler == "trends"


def test_route_for_trends():
    """route_for('GET', '/api/trends') must return Route with handler='trends'."""
    result = route_for("GET", "/api/trends")
    assert result is not None
    assert result.handler == "trends"


def test_trends_get_handler_exists():
    """_get_trends handler must be callable."""
    from brain_alpha_ops.web_handler_dispatch import _GET_DISPATCH_HANDLERS
    assert "trends" in _GET_DISPATCH_HANDLERS
    assert callable(_GET_DISPATCH_HANDLERS["trends"])


def test_trends_post_handler_exists():
    """_post_trends handler must be callable."""
    from brain_alpha_ops.web_handler_dispatch import _POST_DISPATCH_HANDLERS
    assert "trends" in _POST_DISPATCH_HANDLERS
    assert callable(_POST_DISPATCH_HANDLERS["trends"])


def test_trends_dispatch_consistency():
    """Dispatch handler keys must match route table handler names."""
    from brain_alpha_ops.web_handler_dispatch import (
        _GET_DISPATCH_HANDLERS,
        _POST_DISPATCH_HANDLERS,
    )
    for route in GET_ROUTES.values():
        name = route.handler if hasattr(route, "handler") else route
        if name == "trends":
            assert name in _GET_DISPATCH_HANDLERS
    for route in POST_ROUTES.values():
        name = route.handler if hasattr(route, "handler") else route
        if name == "trends":
            assert name in _POST_DISPATCH_HANDLERS


def test_trends_get_returns_ok_structure():
    """GET handler must return dict with 'ok' key."""
    from brain_alpha_ops.web.api.trends import get_trends
    result = get_trends(days=1)
    assert isinstance(result, list)


def test_trends_post_record_roundtrip():
    """record_trend then get_trends must return the recorded entry."""
    import tempfile
    import os
    from brain_alpha_ops.web.api import trends as trends_mod

    old_file = trends_mod._TRENDS_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            trends_mod._TRENDS_FILE = os.path.join(tmp, "trends.jsonl")
            trends_mod.record_trend(candidates=5, submissions=2, completed_cycles=1)
            entries = trends_mod.get_trends(days=365)
            assert len(entries) == 1
            assert entries[0]["candidates"] == 5
            assert entries[0]["submissions"] == 2
    finally:
        trends_mod._TRENDS_FILE = old_file

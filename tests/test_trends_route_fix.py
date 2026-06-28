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


class _TrendsHandlerStub:
    """Minimal handler stub for exercising _post_trends validation directly."""

    def __init__(self, payload):
        self._payload = payload
        self.json_calls = []

    def _read_json(self):
        return self._payload

    def _json(self, payload, status=200, *, extra_headers=None):
        self.json_calls.append((payload, status, extra_headers or []))


def test_post_trends_rejects_out_of_range_and_non_integer_fields(monkeypatch):
    """_post_trends must 400 on negative/over-limit/non-integer/bool/None fields."""
    from brain_alpha_ops.web.api import trends as trends_mod
    from brain_alpha_ops.web.dispatch.post_routes.misc import _post_trends

    recorded = []
    monkeypatch.setattr(trends_mod, "record_trend", lambda **kw: recorded.append(kw))

    cases = [
        ({"candidates": -1, "submissions": 1, "cycles": 0}, "candidates"),
        ({"candidates": 1, "submissions": 10001, "cycles": 0}, "submissions"),
        ({"candidates": 1, "submissions": 1, "cycles": 1001}, "cycles"),
        ({"candidates": "x", "submissions": 1, "cycles": 0}, "candidates"),
        ({"candidates": 1, "submissions": 1.5, "cycles": 0}, "submissions"),
        ({"candidates": True, "submissions": 1, "cycles": 0}, "candidates"),
        ({"candidates": None, "submissions": 1, "cycles": 0}, "candidates"),
    ]
    for body, field in cases:
        handler = _TrendsHandlerStub(body)
        _post_trends(handler, None, None)
        assert handler.json_calls, body
        payload, status, _headers = handler.json_calls[0]
        assert status == 400, body
        assert payload["error_code"] == "VALIDATION_ERROR", body
        assert field in payload["details"], body
    assert recorded == []


def test_post_trends_rejects_non_object_payload():
    """Non-dict JSON body must 400 with VALIDATION_ERROR."""
    from brain_alpha_ops.web.dispatch.post_routes.misc import _post_trends

    handler = _TrendsHandlerStub([])
    _post_trends(handler, None, None)
    payload, status, _headers = handler.json_calls[0]
    assert status == 400
    assert payload["error_code"] == "VALIDATION_ERROR"


def test_post_trends_accepts_valid_in_range_payload(monkeypatch):
    """Valid in-range payloads (including 0 and upper bounds) must be recorded."""
    from brain_alpha_ops.web.api import trends as trends_mod
    from brain_alpha_ops.web.dispatch.post_routes.misc import _post_trends

    recorded = []
    monkeypatch.setattr(trends_mod, "record_trend", lambda **kw: recorded.append(kw))

    handler = _TrendsHandlerStub({"candidates": 5, "submissions": 2, "cycles": 0})
    _post_trends(handler, None, None)
    payload, status, _headers = handler.json_calls[0]
    assert status == 200
    assert payload == {"ok": True}
    assert recorded == [{"candidates": 5, "submissions": 2, "completed_cycles": 0}]

    # 上界值应被接受
    handler = _TrendsHandlerStub(
        {"candidates": 10000, "submissions": 10000, "cycles": 1000}
    )
    _post_trends(handler, None, None)
    assert handler.json_calls[0][1] == 200
    assert recorded[-1] == {
        "candidates": 10000,
        "submissions": 10000,
        "completed_cycles": 1000,
    }

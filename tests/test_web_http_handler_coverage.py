from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

import pytest

from brain_alpha_ops.web_http_handler import create_handler_class, _is_terminal_status, _sse_event_type


class _Session:
    def __init__(self):
        self.allowed = True
        self.valid = True

    def is_allowed_request(self, *, host_header, origin_header, referer_header):
        return self.allowed and host_header == "127.0.0.1:8765"

    def has_valid_request_session(self, **kwargs):
        return self.valid and kwargs["csrf_header"] == "csrf"

    def validate_replay_request(self, **kwargs):
        return {"ok": kwargs["request_id"] == "req_1", "session": kwargs["session_id"]}

    def session_id_from_cookie(self, cookie_header):
        return "session_1" if "session=1" in str(cookie_header) else ""


class _Jobs:
    def __init__(self, row=None):
        self.row = row

    def get(self, job_id):
        return self.row


def _handler(row=None, *, session=None, resolve=None, resolve_static_asset=None):
    session = session or _Session()
    calls = []

    Handler = create_handler_class(
        server_version="TestServer/1",
        max_body_bytes=32,
        dispatch_get=lambda handler, parsed, ctx: handler._json({"ok": True, "path": parsed.path, "ctx": ctx}),
        dispatch_post=lambda handler, parsed, ctx: handler._json({"ok": True, "posted": parsed.path, "ctx": ctx}),
        dispatch_context=lambda: {"ctx": "value"},
        web_session=session,
        jobs=_Jobs(row),
        enrich_progress=lambda progress: {**progress, "enriched": True},
        content_security_policy_for_html=lambda html=None: "default-src 'self'" if html is None else "script-src 'self'",
        sse_push_interval=0,
        max_sse_duration=1,
        resolve_sse_job=resolve,
        resolve_static_asset=resolve_static_asset,
    )
    handler = object.__new__(Handler)
    handler.path = "/api/status"
    handler.headers = {
        "Host": "127.0.0.1:8765",
        "Origin": "",
        "Referer": "",
        "Cookie": "session=1",
        "X-Brain-Alpha-CSRF": "csrf",
        "X-Brain-Alpha-Request-ID": "req_1",
        "X-Brain-Alpha-Request-Timestamp": "1",
    }
    handler.rfile = BytesIO()
    handler.wfile = BytesIO()
    handler.send_response = lambda status: calls.append(("status", status))
    handler.send_header = lambda name, value: calls.append(("header", name, value))
    handler.end_headers = lambda: calls.append(("end",))
    return handler, calls, session


def test_handler_dispatch_methods_and_session_delegates():
    handler, calls, session = _handler()
    handler.path = "/api/config?x=1"

    handler.do_GET()
    assert b'"path": "/api/config"' in handler.wfile.getvalue()
    assert handler._is_allowed_local_request() is True
    assert handler._has_valid_session("x=1") is True
    assert handler._validate_replay_request()["ok"] is True
    assert handler._session_id_from_cookie() == "session_1"

    handler.wfile = BytesIO()
    handler.path = "/api/run"
    handler.do_POST()
    assert b'"posted": "/api/run"' in handler.wfile.getvalue()

    session.allowed = False
    assert handler._is_allowed_local_request() is False
    assert any(item == ("header", "Content-Security-Policy", "default-src 'self'") for item in calls)


def test_handler_read_json_size_and_decode_boundaries():
    handler, _calls, _session = _handler()
    handler.headers = {"Content-Length": "0"}
    assert handler._read_json() == {}

    handler.headers = {"Content-Length": "7"}
    handler.rfile = BytesIO(b'{"a":1}')
    assert handler._read_json() == {"a": 1}

    handler.headers = {"Content-Length": "-1"}
    with pytest.raises(ValueError, match="invalid request body length"):
        handler._read_json()

    handler.headers = {"Content-Length": "33"}
    with pytest.raises(ValueError, match="request body too large"):
        handler._read_json()


def test_handler_json_and_html_send_security_headers():
    handler, calls, _session = _handler()

    handler._json({"ok": True, "message": "hello"}, status=202, extra_headers=[("X-Test", "1")])
    body = handler.wfile.getvalue()
    assert b'"message": "hello"' in body
    assert ("status", 202) in calls
    assert ("header", "X-Test", "1") in calls
    assert ("header", "X-Frame-Options", "DENY") in calls

    handler.wfile = BytesIO()
    calls.clear()
    handler._html("<html></html>", extra_headers=[("Set-Cookie", "session=1")])
    assert handler.wfile.getvalue() == b"<html></html>"
    assert ("header", "Content-Type", "text/html; charset=utf-8") in calls
    assert ("header", "Content-Security-Policy", "script-src 'self'") in calls


def test_handler_serves_opt_in_static_assets_and_rejects_missing_or_forbidden_requests():
    resolve = lambda path: (b"console.log('react')", "text/javascript") if path == "/assets/app.js" else None
    handler, calls, session = _handler(resolve_static_asset=resolve)
    handler.path = "/assets/app.js"

    handler.do_GET()

    assert handler.wfile.getvalue() == b"console.log('react')"
    assert ("status", 200) in calls
    assert ("header", "Content-Type", "text/javascript") in calls
    assert ("header", "X-Content-Type-Options", "nosniff") in calls

    handler.wfile = BytesIO()
    calls.clear()
    handler.path = "/assets/missing.js"
    handler.do_GET()
    assert b"NOT_FOUND" in handler.wfile.getvalue()
    assert ("status", 404) in calls

    handler.wfile = BytesIO()
    calls.clear()
    session.allowed = False
    handler.path = "/assets/app.js"
    handler.do_GET()
    assert b"ORIGIN_FORBIDDEN" in handler.wfile.getvalue()
    assert ("status", 403) in calls


def test_sse_stream_handles_auth_validation_missing_unknown_and_complete():
    session = _Session()
    session.valid = False
    handler, _calls, _session = _handler(session=session)
    handler._handle_sse_stream("job_id=job_1")
    assert b"AUTH_REQUIRED" in handler.wfile.getvalue()

    session.valid = True
    handler, _calls, _session = _handler(session=session)
    handler._handle_sse_stream("")
    assert b"missing job_id" in handler.wfile.getvalue()

    handler, _calls, _session = _handler(row=None)
    handler._handle_sse_stream("job_id=missing")
    assert b"job not found" in handler.wfile.getvalue()

    row = {
        "status": "completed",
        "progress": {"phase": "done", "percent_complete": 100},
        "result": {"count": 1},
        "error": "",
    }
    handler, calls, _session = _handler(row=row)
    handler._handle_sse_stream("job_id=job_1")
    payload = handler.wfile.getvalue()
    assert b'"type": "complete"' in payload
    assert b'"enriched": true' in payload
    assert ("header", "Content-Type", "text/event-stream") in calls


def test_sse_stream_timeout_and_broken_pipe_are_safe(monkeypatch):
    times = iter([0.0, 2.0])
    monkeypatch.setattr("brain_alpha_ops.web_http_handler.time.monotonic", lambda: next(times))
    handler, _calls, _session = _handler(row={"status": "running", "progress": {}})
    handler._handle_sse_stream("job_id=job_1")
    assert b"sse stream timeout" in handler.wfile.getvalue()

    monkeypatch.setattr("brain_alpha_ops.web_http_handler.time.monotonic", lambda: 0.0)

    class _BrokenWriter:
        def write(self, _data):
            raise BrokenPipeError()

        def flush(self):
            raise AssertionError("flush should not run after write fails")

    handler, _calls, _session = _handler(row={"status": "completed", "progress": {}})
    handler.wfile = _BrokenWriter()
    handler._handle_sse_stream("job_id=job_1")


def test_sse_status_helpers():
    assert _is_terminal_status("completed") is True
    assert _is_terminal_status("canceled") is True
    assert _is_terminal_status("running") is False
    assert _sse_event_type("failed") == "error"
    assert _sse_event_type("completed_with_warnings") == "complete"
    assert _sse_event_type("queued") == "progress"

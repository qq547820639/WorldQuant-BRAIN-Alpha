from __future__ import annotations

from brain_alpha_ops.web_security import (
    LocalSessionManager,
    header_hostname,
    header_port,
    is_allowed_local_request,
    normalize_host,
    parse_cookies,
    path_requires_session,
)


def test_host_cookie_and_path_helpers_normalize_inputs():
    assert header_hostname("localhost:8765") == "localhost"
    assert header_hostname("[::1]:8765") == "::1"
    assert header_port("localhost:8765") == 8765
    assert header_port("bad:port") is None
    assert parse_cookies("a=1; brain_alpha_ops_session=abc; flag") == {"a": "1", "brain_alpha_ops_session": "abc"}
    assert path_requires_session("/api/status") is True
    assert path_requires_session("/api/health") is False
    assert normalize_host("") == "127.0.0.1"


def test_local_request_origin_and_referer_must_match_loopback_and_port():
    assert is_allowed_local_request(host_header="127.0.0.1:8765", origin_header="http://127.0.0.1:8765")
    assert not is_allowed_local_request(host_header="example.com:8765")
    assert not is_allowed_local_request(host_header="127.0.0.1:8765", origin_header="https://evil.example")
    assert not is_allowed_local_request(host_header="127.0.0.1:8765", referer_header="http://127.0.0.1:9999/page")


def test_session_manager_uses_distinct_csrf_and_stream_tokens():
    manager = LocalSessionManager(ttl_seconds=120)
    session_id, csrf_token = manager.create()
    stream_token = manager.stream_token_for_session(session_id)

    assert session_id
    assert csrf_token
    assert stream_token
    assert stream_token != csrf_token
    assert manager.validate_csrf(session_id, csrf_token) is True
    assert manager.validate_stream(session_id, csrf_token) is False
    assert manager.validate_stream(session_id, stream_token) is True
    assert "HttpOnly" in manager.cookie_header(session_id)
    assert "SameSite=Strict" in manager.cookie_header(session_id)


def test_session_manager_prunes_and_single_session_policy():
    manager = LocalSessionManager(ttl_seconds=120, allow_multiple_sessions=False)
    first_id, _first_csrf = manager.create()
    second_id, _second_csrf = manager.create()

    assert first_id not in manager.sessions
    assert second_id in manager.sessions

    manager.sessions["expired"] = {"expires_at": 1.0}
    manager.prune(now=2.0)

    assert "expired" not in manager.sessions


def test_has_valid_request_session_allows_header_csrf_or_stream_query_only():
    manager = LocalSessionManager(ttl_seconds=120)
    session_id, csrf_token = manager.create()
    stream_token = manager.stream_token_for_session(session_id)
    cookie = manager.cookie_header(session_id)

    assert manager.has_valid_request_session(
        path="/api/status",
        query_string="stream_token=wrong",
        csrf_header=csrf_token,
        cookie_header=cookie,
    )
    assert manager.has_valid_request_session(
        path="/api/stream",
        query_string=f"stream_token={stream_token}",
        csrf_header="",
        cookie_header=cookie,
    )
    assert not manager.has_valid_request_session(
        path="/api/status",
        query_string=f"stream_token={stream_token}",
        csrf_header="",
        cookie_header=cookie,
    )

from __future__ import annotations

from brain_alpha_ops.web_security import (
    LocalSessionManager,
    admin_token_from_headers,
    header_hostname,
    header_port,
    is_allowed_local_request,
    normalize_host,
    parse_cookies,
    path_requires_session,
    validate_admin_token,
)
from brain_alpha_ops.web_rate_limit import RateLimitPolicy, RequestRateLimiter


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


def test_remote_request_policy_requires_same_origin_when_enabled():
    assert is_allowed_local_request(
        host_header="console.example.test:8765",
        origin_header="http://console.example.test:8765",
        allow_remote=True,
    )
    assert not is_allowed_local_request(
        host_header="console.example.test:8765",
        origin_header="http://evil.example:8765",
        allow_remote=True,
    )
    assert not is_allowed_local_request(
        host_header="console.example.test:8765",
        referer_header="http://console.example.test:9999/page",
        allow_remote=True,
    )


def test_remote_admin_token_accepts_bearer_or_dedicated_header():
    assert admin_token_from_headers({"Authorization": "Bearer secret-token"}) == "secret-token"
    assert admin_token_from_headers({"X-Brain-Alpha-Admin-Token": "secret-token"}) == "secret-token"
    assert validate_admin_token("secret-token", "secret-token") is True
    assert validate_admin_token("secret-token", "other-token") is False
    assert validate_admin_token("", "secret-token") is False
    assert validate_admin_token("secret-token", "") is False


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
    assert "Secure" not in manager.cookie_header(session_id)


def test_session_manager_can_mark_cookies_secure_for_remote_https():
    manager = LocalSessionManager(ttl_seconds=120, secure_cookies=True)
    session_id, _csrf_token = manager.create()

    assert "Secure" in manager.cookie_header(session_id)
    assert "Secure" in manager.expired_cookie_header()


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
    assert manager.has_valid_request_session(
        path="/sse",
        query_string=f"job_id=job_1&stream_token={stream_token}",
        csrf_header="",
        cookie_header=cookie,
    )
    assert not manager.has_valid_request_session(
        path="/api/status",
        query_string=f"stream_token={stream_token}",
        csrf_header="",
        cookie_header=cookie,
    )


def test_session_manager_rejects_replayed_or_stale_post_requests():
    manager = LocalSessionManager(ttl_seconds=120)
    session_id, _csrf_token = manager.create()

    accepted = manager.validate_replay(
        session_id=session_id,
        request_id="req-1",
        request_timestamp=str(int(1_700_000_000 * 1000)),
        now=1_700_000_000,
    )
    assert accepted["ok"] is True

    duplicate = manager.validate_replay(
        session_id=session_id,
        request_id="req-1",
        request_timestamp=str(int(1_700_000_001 * 1000)),
        now=1_700_000_001,
    )
    assert duplicate["ok"] is False
    assert duplicate["error_code"] == "REPLAY_DETECTED"

    stale = manager.validate_replay(
        session_id=session_id,
        request_id="req-2",
        request_timestamp=str(int(1_699_999_000 * 1000)),
        now=1_700_000_001,
    )
    assert stale["ok"] is False
    assert stale["error_code"] == "REPLAY_TIMESTAMP_STALE"


def test_request_rate_limiter_uses_separate_read_write_and_submit_buckets():
    limiter = RequestRateLimiter(RateLimitPolicy(window_seconds=10, read_requests=2, write_requests=1, submit_requests=1))

    assert limiter.check(key="session-1", method="GET", path="/api/status", now=100)["ok"] is True
    assert limiter.check(key="session-1", method="GET", path="/api/status", now=101)["ok"] is True
    limited_read = limiter.check(key="session-1", method="GET", path="/api/status", now=102)
    assert limited_read["ok"] is False
    assert limited_read["error_code"] == "RATE_LIMITED"

    assert limiter.check(key="session-1", method="POST", path="/api/run", now=102)["ok"] is True
    limited_write = limiter.check(key="session-1", method="POST", path="/api/run", now=103)
    assert limited_write["ok"] is False
    assert limited_write["retry_after"] > 0

    assert limiter.check(key="session-1", method="POST", path="/api/submit", now=103)["ok"] is True
    assert limiter.check(key="session-1", method="POST", path="/api/submit", now=104)["ok"] is False
    assert limiter.check(key="session-1", method="GET", path="/api/status", now=112)["ok"] is True

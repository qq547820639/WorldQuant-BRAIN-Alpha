"""Global session policy facade for the local web console."""

from __future__ import annotations

import os
from typing import Any

from brain_alpha_ops.web_security import (
    LOCAL_HOSTS,
    LocalSessionManager,
    admin_token_from_headers,
    is_allowed_local_request,
    normalize_host as _normalize_host,
    validate_admin_token,
)


DEFAULT_ADMIN_TOKEN_ENV = "BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN"

SESSION_MANAGER = LocalSessionManager()
SESSIONS = SESSION_MANAGER.sessions
SESSION_LOCK = SESSION_MANAGER.lock

allow_remote_requests = False
remote_admin_token_env = DEFAULT_ADMIN_TOKEN_ENV


def configure_session_policy(
    ttl_seconds: int | float | None = None,
    allow_multiple_sessions: bool | None = None,
    secure_cookies: bool | None = None,
) -> None:
    SESSION_MANAGER.configure(ttl_seconds, allow_multiple_sessions, secure_cookies)


def session_ttl_seconds() -> int:
    return SESSION_MANAGER.ttl_seconds


def session_allow_multiple() -> bool:
    return SESSION_MANAGER.allow_multiple_sessions


def set_remote_policy(*, allow_remote: bool, admin_token_env: str | None = None) -> None:
    global allow_remote_requests, remote_admin_token_env
    allow_remote_requests = bool(allow_remote)
    if admin_token_env:
        remote_admin_token_env = str(admin_token_env)


def require_remote_admin_token() -> None:
    if allow_remote_requests and not os.getenv(remote_admin_token_env, ""):
        raise ValueError(f"remote web bind requires admin token env var {remote_admin_token_env}")


def remote_admin_required() -> bool:
    return bool(allow_remote_requests)


def has_valid_admin_token(headers: Any) -> bool:
    expected_token = os.getenv(remote_admin_token_env, "")
    provided_token = admin_token_from_headers(headers)
    return validate_admin_token(provided_token, expected_token)


def is_allowed_request(*, host_header: str, origin_header: str = "", referer_header: str = "") -> bool:
    return is_allowed_local_request(
        host_header=host_header,
        origin_header=origin_header,
        referer_header=referer_header,
        local_hosts=LOCAL_HOSTS,
        allow_remote=allow_remote_requests,
    )


def normalize_host(host: str | None, *, default_host: str = "127.0.0.1") -> str:
    return _normalize_host(host, default_host=default_host)


def session_cookie_header(session_id: str, *, max_age: int | None = None) -> str:
    return SESSION_MANAGER.cookie_header(session_id, max_age=max_age)


def expired_session_cookie_header() -> str:
    return SESSION_MANAGER.expired_cookie_header()


def prune_sessions(now: float | None = None) -> None:
    SESSION_MANAGER.prune(now)


def create_session() -> tuple[str, str]:
    return SESSION_MANAGER.create()


def expire_session(session_id: str) -> None:
    SESSION_MANAGER.expire(session_id)


def validate_session_token(session_id: str, token: str, token_key: str) -> bool:
    return SESSION_MANAGER.validate_token(session_id, token, token_key)


def validate_session(session_id: str, csrf_token: str) -> bool:
    return SESSION_MANAGER.validate_csrf(session_id, csrf_token)


def validate_stream_session(session_id: str, stream_token: str) -> bool:
    return SESSION_MANAGER.validate_stream(session_id, stream_token)


def csrf_for_session(session_id: str) -> str:
    return SESSION_MANAGER.csrf_for_session(session_id)


def stream_token_for_session(session_id: str) -> str:
    return SESSION_MANAGER.stream_token_for_session(session_id)


def get_or_create_session(existing_session_id: str) -> tuple[str, str]:
    return SESSION_MANAGER.get_or_create(existing_session_id)


def session_id_from_cookie(cookie_header: str) -> str:
    return SESSION_MANAGER.session_id_from_cookie(cookie_header)


def has_valid_request_session(
    *,
    path: str,
    query_string: str,
    csrf_header: str,
    cookie_header: str,
) -> bool:
    return SESSION_MANAGER.has_valid_request_session(
        path=path,
        query_string=query_string,
        csrf_header=csrf_header,
        cookie_header=cookie_header,
    )


def validate_replay_request(
    *,
    session_id: str,
    request_id: str,
    request_timestamp: str,
) -> dict[str, Any]:
    return SESSION_MANAGER.validate_replay(
        session_id=session_id,
        request_id=request_id,
        request_timestamp=request_timestamp,
    )

"""Global session policy facade for the local web console."""

from __future__ import annotations

import os
import time
from typing import Any

from brain_alpha_ops.web_security import (
    DEFAULT_SESSION_TTL_SECONDS,
    LOCAL_HOSTS,
    LocalSessionManager,
    SESSION_COOKIE_NAME,
    admin_token_from_headers,
    header_hostname,
    header_port,
    is_allowed_local_request,
    normalize_host as _normalize_host,
    parse_cookies,
    path_requires_session,
    validate_admin_token,
)
from brain_alpha_ops.web_post_handlers import session_end_payload


DEFAULT_ADMIN_TOKEN_ENV = "BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN"

SESSION_MANAGER = LocalSessionManager()
SESSIONS = SESSION_MANAGER.sessions
SESSION_LOCK = SESSION_MANAGER.lock

allow_remote_requests = False
remote_admin_token_env = DEFAULT_ADMIN_TOKEN_ENV


class WebSession:
    """Compatibility wrapper around LocalSessionManager for isolated tests/tools."""

    def __init__(self, ttl_seconds: int | float = DEFAULT_SESSION_TTL_SECONDS, **kwargs: Any) -> None:
        self.manager = LocalSessionManager(ttl_seconds=int(ttl_seconds), **kwargs)

    def create_session(
        self,
        *,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id, csrf_token = self.manager.create()
        with self.manager.lock:
            row = self.manager.sessions[session_id]
            row["metadata"] = dict(metadata or {})
            if user_id is not None:
                row["user_id"] = user_id
        return self._row(session_id, csrf_token)

    def get_session(self, session_id: str | None) -> dict[str, Any] | None:
        if not session_id:
            return None
        self.manager.prune()
        with self.manager.lock:
            row = self.manager.sessions.get(session_id)
            if not row:
                return None
            row["last_accessed"] = time.time()
            return self._row_from_existing(session_id, row)

    def validate_session(self, session_id: str | None) -> bool:
        return self.get_session(session_id) is not None

    def validate_csrf(self, session_id: str | None, csrf_token: str | None) -> bool:
        return self.manager.validate_csrf(str(session_id or ""), str(csrf_token or ""))

    def expire_session(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        existed = self.get_session(session_id) is not None
        self.manager.expire(session_id)
        return existed

    def refresh_session(self, session_id: str | None) -> dict[str, Any] | None:
        if not session_id:
            return None
        self.manager.prune()
        with self.manager.lock:
            row = self.manager.sessions.get(session_id)
            if not row:
                return None
            current = time.time()
            absolute_expires_at = float(row.get("absolute_expires_at", row.get("expires_at", 0.0)) or 0.0)
            row["last_accessed"] = current
            row["expires_at"] = min(current + self.manager.ttl_seconds, absolute_expires_at)
            return self._row_from_existing(session_id, row)

    def get_or_create_session(self, session_id: str | None) -> dict[str, Any]:
        existing = self.get_session(session_id)
        if existing:
            return existing
        return self.create_session()

    def prune_sessions(self) -> int:
        before = len(self.manager.sessions)
        self.manager.prune()
        return max(0, before - len(self.manager.sessions))

    def _row(self, session_id: str, csrf_token: str) -> dict[str, Any]:
        with self.manager.lock:
            row = dict(self.manager.sessions.get(session_id, {}))
        row["csrf"] = csrf_token
        return self._row_from_existing(session_id, row)

    @staticmethod
    def _row_from_existing(session_id: str, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": session_id,
            "csrf_token": str(row.get("csrf", "")),
            "created_at": float(row.get("created_at", 0.0) or 0.0),
            "expires_at": float(row.get("expires_at", 0.0) or 0.0),
            "last_accessed": float(row.get("last_accessed", row.get("created_at", 0.0)) or 0.0),
            "metadata": dict(row.get("metadata") or {}),
            **({"user_id": row["user_id"]} if "user_id" in row else {}),
        }


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


def create_session(*_args: Any, **_kwargs: Any) -> tuple[str, str]:
    return SESSION_MANAGER.create()


def new_session_id(*_args: Any, **_kwargs: Any) -> str:
    session_id, _csrf_token = create_session()
    return session_id


def expire_session(session_id: str, *_args: Any, **_kwargs: Any) -> None:
    SESSION_MANAGER.expire(session_id)


def validate_session_token(session_id: str, token: str = "", token_key: str = "csrf", *_args: Any, **_kwargs: Any) -> bool:
    return SESSION_MANAGER.validate_token(session_id, token, token_key)


def validate_session(session_id: str, csrf_token: str = "", *_args: Any, **_kwargs: Any) -> bool:
    return SESSION_MANAGER.validate_csrf(session_id, csrf_token)


def validate_stream_session(session_id: str, stream_token: str = "", *_args: Any, **_kwargs: Any) -> bool:
    return SESSION_MANAGER.validate_stream(session_id, stream_token)


def csrf_for_session(session_id: str) -> str:
    return SESSION_MANAGER.csrf_for_session(session_id)


def stream_token_for_session(session_id: str) -> str:
    return SESSION_MANAGER.stream_token_for_session(session_id)


def get_or_create_session(existing_session_id: str | None = "") -> tuple[str, str]:
    return SESSION_MANAGER.get_or_create(existing_session_id or "")


def session_id_from_cookie(cookie_header: str) -> str:
    return SESSION_MANAGER.session_id_from_cookie(cookie_header)


def extract_session_from_request(handler: Any) -> str | None:
    cookie_header = str(getattr(handler, "headers", {}).get("Cookie", "") if handler else "")
    cookies = parse_cookies(cookie_header)
    return cookies.get(SESSION_COOKIE_NAME) or cookies.get("session") or None


def validate_request_session(handler: Any) -> bool:
    session_id = extract_session_from_request(handler)
    if not session_id:
        return False
    headers = getattr(handler, "headers", {}) if handler else {}
    csrf_header = str(
        headers.get("X-CSRF-Token")
        or headers.get("X-Brain-Alpha-CSRF")
        or headers.get("X-CSRF")
        or ""
    )
    if not csrf_header:
        return False
    return validate_session(session_id, csrf_header)


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

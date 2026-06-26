"""Shared session state, ``WebSession`` wrapper, and policy primitives.

Split out of the former ``web_session.py`` monolith (Phase 12 / Task B9).
Holds the module-level singletons (``SESSION_MANAGER``, ``SESSIONS``,
``SESSION_LOCK``), the ``WebSession`` compatibility wrapper, and the
request/admin-token policy helpers.
"""

from __future__ import annotations

import os
import time
from typing import Any

from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.web_security import (
    DEFAULT_SESSION_TTL_SECONDS,
    LOCAL_HOSTS,
    LocalSessionManager,
    admin_token_from_headers,
    is_allowed_local_request,
    validate_admin_token,
)
from brain_alpha_ops.web_security import (
    normalize_host as _normalize_host,
)

DEFAULT_ADMIN_TOKEN_ENV = "BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN"

SESSION_MANAGER = LocalSessionManager()
SESSIONS = SESSION_MANAGER.sessions
SESSION_LOCK = SESSION_MANAGER.lock
BRAIN_CONNECTION_METADATA_KEY = "brain_connection"
BRAIN_CREDENTIALS_KEY = "brain_credentials"
_BRAIN_CREDENTIAL_FIELDS = ("username", "password", "token")

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
        safe_metadata = redact_data(dict(row.get("metadata") or {}), key_fragments=("account_id", "user_id"))
        safe_user_id = redact_data({"user_id": row.get("user_id", "")}, key_fragments=("user_id",)).get("user_id")
        return {
            "id": session_id,
            "csrf_token": str(row.get("csrf", "")),
            "created_at": float(row.get("created_at", 0.0) or 0.0),
            "expires_at": float(row.get("expires_at", 0.0) or 0.0),
            "last_accessed": float(row.get("last_accessed", row.get("created_at", 0.0)) or 0.0),
            "metadata": safe_metadata,
            **({"user_id": safe_user_id} if "user_id" in row else {}),
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


# P3-27 note: prune is called on-demand at read time.  For servers
# that stay alive for extended periods, consider a background daemon
# thread that periodically calls SESSION_MANAGER.prune() to prevent
# orphaned sessions from accumulating indefinitely.
def prune_sessions(now: float | None = None) -> None:
    SESSION_MANAGER.prune(now)

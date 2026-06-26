"""Global session policy facade for the local web console."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from brain_alpha_ops.web.dispatch.web_post_handlers import session_end_payload  # noqa: F401  # re-export
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.web_security import (
    DEFAULT_SESSION_TTL_SECONDS,
    LOCAL_HOSTS,
    SESSION_COOKIE_NAME,
    LocalSessionManager,
    admin_token_from_headers,
    is_allowed_local_request,
    parse_cookies,
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


def session_status(session_id: str | None) -> dict[str, Any]:
    """Return sanitized local and BRAIN connection state for the browser."""
    info = SESSION_MANAGER.session_info(str(session_id or ""))
    if not info:
        return {
            "ok": True,
            "authenticated": False,
            "connected": False,
            "brain_connection_verified": False,
            "credential_source": "none",
            "session_credentials_available": False,
            "ttl_seconds": SESSION_MANAGER.ttl_seconds,
            "remaining_ttl_seconds": 0,
        }
    metadata = dict(info.get("metadata") or {})
    brain = metadata.get(BRAIN_CONNECTION_METADATA_KEY)
    if not isinstance(brain, dict):
        brain = {}
    current = time.time()
    remaining_ttl = max(0, int(float(info.get("expires_at", 0.0) or 0.0) - current))
    connected = bool(brain.get("verified"))
    session_credentials_available = bool(brain_session_credentials(str(session_id or "")))
    return {
        "ok": True,
        "authenticated": True,
        "connected": connected,
        "brain_connection_verified": connected,
        "session_id": str(info.get("id", ""))[:8],
        "credential_source": str(brain.get("credential_source") or ("managed" if connected else "none")),
        "session_credentials_available": session_credentials_available,
        "auth_mode": str(brain.get("auth_mode") or ""),
        "environment": str(brain.get("environment") or ""),
        "last_verified_at": brain.get("verified_at"),
        "verified_at": brain.get("verified_at"),
        "ttl_seconds": SESSION_MANAGER.ttl_seconds,
        "remaining_ttl_seconds": remaining_ttl,
        "expires_at": float(info.get("expires_at", 0.0) or 0.0),
    }


def mark_brain_connection_verified(
    session_id: str | None,
    result: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Store only non-secret BRAIN connection proof in server-side session metadata."""
    session_id = str(session_id or "")
    if not session_id:
        return session_status(session_id)
    result = result if isinstance(result, dict) else {}
    metadata = {
        "verified": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "environment": str(result.get("environment") or "production"),
        "auth_mode": str(result.get("auth") or result.get("auth_mode") or ""),
        "credential_source": _credential_source(payload),
    }
    SESSION_MANAGER.update_metadata(session_id, {BRAIN_CONNECTION_METADATA_KEY: metadata})
    store_brain_session_credentials(session_id, payload)
    return session_status(session_id)


def clear_brain_connection_verified(session_id: str | None) -> dict[str, Any]:
    clear_brain_session_credentials(session_id)
    SESSION_MANAGER.update_metadata(str(session_id or ""), {BRAIN_CONNECTION_METADATA_KEY: None})
    return session_status(session_id)


def store_brain_session_credentials(session_id: str | None, payload: dict[str, Any] | None) -> bool:
    """Keep page-entered BRAIN credentials in the server session only.

    The vault is an in-memory field on the local session row.  It is not part
    of metadata returned to the browser and is removed with the session.
    """
    session_id = str(session_id or "")
    credentials = _credentials_from_payload(payload)
    if not session_id or not credentials:
        return False
    SESSION_MANAGER.prune()
    with SESSION_MANAGER.lock:
        row = SESSION_MANAGER.sessions.get(session_id)
        if not row:
            return False
        row[BRAIN_CREDENTIALS_KEY] = credentials
        current = time.time()
        absolute_expires_at = float(row.get("absolute_expires_at", row.get("expires_at", 0.0)) or 0.0)
        row["last_accessed"] = current
        row["expires_at"] = min(current + SESSION_MANAGER.ttl_seconds, absolute_expires_at)
    return True


# P1-12 note: credentials are stored in-memory only (never persisted to
# disk).  For production deployments consider integrating with the system
# keychain (keyring / macOS Keychain) instead of in-memory storage.
# In-memory storage is acceptable for local single-user usage.
def brain_session_credentials(session_id: str | None) -> dict[str, str]:
    session_id = str(session_id or "")
    if not session_id:
        return {}
    SESSION_MANAGER.prune()
    with SESSION_MANAGER.lock:
        row = SESSION_MANAGER.sessions.get(session_id)
        if not row:
            return {}
        raw = row.get(BRAIN_CREDENTIALS_KEY)
        if not isinstance(raw, dict):
            return {}
        current = time.time()
        absolute_expires_at = float(row.get("absolute_expires_at", row.get("expires_at", 0.0)) or 0.0)
        if absolute_expires_at <= current:
            SESSION_MANAGER.sessions.pop(session_id, None)
            return {}
        row["last_accessed"] = current
        row["expires_at"] = min(current + SESSION_MANAGER.ttl_seconds, absolute_expires_at)
        return {
            key: str(raw.get(key) or "")
            for key in _BRAIN_CREDENTIAL_FIELDS
            if str(raw.get(key) or "")
        }


def clear_brain_session_credentials(session_id: str | None) -> bool:
    session_id = str(session_id or "")
    if not session_id:
        return False
    SESSION_MANAGER.prune()
    with SESSION_MANAGER.lock:
        row = SESSION_MANAGER.sessions.get(session_id)
        if not row:
            return False
        existed = BRAIN_CREDENTIALS_KEY in row
        row.pop(BRAIN_CREDENTIALS_KEY, None)
        return existed


def payload_with_brain_session_credentials(session_id: str | None, payload: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(payload or {})
    if _has_payload_credentials(merged):
        return merged
    credentials = brain_session_credentials(session_id)
    if credentials:
        merged.update(credentials)
    return merged


def _credential_source(payload: dict[str, Any] | None) -> str:
    payload = payload if isinstance(payload, dict) else {}
    if str(payload.get("token") or "").strip():
        return "page"
    if str(payload.get("username") or "").strip() or str(payload.get("password") or "").strip():
        return "page"
    return "managed"


def _credentials_from_payload(payload: dict[str, Any] | None) -> dict[str, str]:
    payload = payload if isinstance(payload, dict) else {}
    token = str(payload.get("token") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if username and password.strip():
        return {"username": username, "password": password}
    if token:
        return {"token": token}
    return {}


def _has_payload_credentials(payload: dict[str, Any] | None) -> bool:
    payload = payload if isinstance(payload, dict) else {}
    return any(str(payload.get(key) or "").strip() for key in _BRAIN_CREDENTIAL_FIELDS)


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

from .web_security import header_hostname  # noqa: F401  # backward-compat

from .web_security import header_port  # noqa: F401

from .web_security import path_requires_session  # noqa: F401


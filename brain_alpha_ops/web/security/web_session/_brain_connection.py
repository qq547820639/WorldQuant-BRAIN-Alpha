"""BRAIN connection verification and per-session credential vault.

Split out of the former ``web_session.py`` monolith (Phase 12 / Task B9).
Holds the ``session_status`` / ``mark_brain_connection_verified`` /
``store_brain_session_credentials`` family of helpers that store and
retrieve non-secret BRAIN connection proof plus the in-memory credential
vault keyed off the local session row.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ._state import (
    BRAIN_CONNECTION_METADATA_KEY,
    BRAIN_CREDENTIALS_KEY,
    _BRAIN_CREDENTIAL_FIELDS,
    SESSION_MANAGER,
)


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

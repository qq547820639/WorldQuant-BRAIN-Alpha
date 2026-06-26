"""Session-token dispatch helpers used by the web request handlers.

Split out of the former ``web_session.py`` monolith (Phase 12 / Task B9).
These are the thin adapter functions that delegate to ``SESSION_MANAGER``
for create/expire/validate/csrf/stream-token flows plus the
request-bound helpers (``extract_session_from_request``,
``validate_request_session``, ``has_valid_request_session``,
``validate_replay_request``).
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_security import (
    SESSION_COOKIE_NAME,
    parse_cookies,
)

from ._state import SESSION_MANAGER


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

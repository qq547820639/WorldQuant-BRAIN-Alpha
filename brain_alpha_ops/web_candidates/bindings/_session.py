"""Web session policy bindings."""

from __future__ import annotations

from ._helpers import _web


def configure_session_policy(
    ttl_seconds: int | float | None = None,
    allow_multiple_sessions: bool | None = None,
    secure_cookies: bool | None = None,
) -> None:
    web = _web()
    web.web_session.configure_session_policy(ttl_seconds, allow_multiple_sessions, secure_cookies)
    web.SESSION_TTL_SECONDS = web.web_session.session_ttl_seconds()
    web.SESSION_ALLOW_MULTIPLE = web.web_session.session_allow_multiple()


def normalize_host(host: str | None) -> str:
    web = _web()
    return web.web_session.normalize_host(host, default_host=web.HOST)

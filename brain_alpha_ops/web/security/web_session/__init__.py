"""Global session policy facade for the local web console.

Subpackage split (formerly ``web_session.py`` monolith, Phase 12 / Task B9):
  - ``_state``: module-level singletons (``SESSION_MANAGER`` / ``SESSIONS`` /
    ``SESSION_LOCK``), ``WebSession`` compatibility wrapper, and the
    request/admin-token policy helpers
  - ``_brain_connection``: BRAIN connection verification and the in-memory
    per-session credential vault
  - ``_dispatch``: thin adapter helpers for create/expire/validate/csrf/
    stream-token flows plus request-bound session extraction

The legacy import paths
``from brain_alpha_ops.web.security.web_session import X`` and
``from brain_alpha_ops.web_session import X`` (the latter redirected by
``_web_bridge``) continue to resolve to this package.
"""

from __future__ import annotations

# Backward-compat re-exports — preserved verbatim from the original module
# (Phase 11 consolidated duplicate imports; this layout keeps that fix).
from brain_alpha_ops.web.dispatch.web_post_handlers import session_end_payload  # noqa: F401  # re-export
from brain_alpha_ops.web_security import (
    DEFAULT_SESSION_TTL_SECONDS,
    LOCAL_HOSTS,
    SESSION_COOKIE_NAME,
    admin_token_from_headers,
    is_allowed_local_request,
    parse_cookies,
    validate_admin_token,
)
from brain_alpha_ops.web_security import header_hostname  # noqa: F401  # backward-compat
from brain_alpha_ops.web_security import header_port  # noqa: F401
from brain_alpha_ops.web_security import path_requires_session  # noqa: F401

from ._brain_connection import (
    brain_session_credentials,
    clear_brain_connection_verified,
    clear_brain_session_credentials,
    mark_brain_connection_verified,
    payload_with_brain_session_credentials,
    session_status,
    store_brain_session_credentials,
)
from ._dispatch import (
    create_session,
    csrf_for_session,
    expire_session,
    extract_session_from_request,
    get_or_create_session,
    has_valid_request_session,
    new_session_id,
    session_id_from_cookie,
    stream_token_for_session,
    validate_replay_request,
    validate_request_session,
    validate_session,
    validate_session_token,
    validate_stream_session,
)
from ._state import (
    BRAIN_CONNECTION_METADATA_KEY,
    BRAIN_CREDENTIALS_KEY,
    DEFAULT_ADMIN_TOKEN_ENV,
    SESSION_LOCK,
    SESSION_MANAGER,
    SESSIONS,
    WebSession,
    allow_remote_requests,
    configure_session_policy,
    expired_session_cookie_header,
    has_valid_admin_token,
    is_allowed_request,
    normalize_host,
    prune_sessions,
    remote_admin_required,
    remote_admin_token_env,
    require_remote_admin_token,
    session_allow_multiple,
    session_cookie_header,
    session_ttl_seconds,
    set_remote_policy,
)

__all__ = [
    "BRAIN_CONNECTION_METADATA_KEY",
    "BRAIN_CREDENTIALS_KEY",
    "DEFAULT_ADMIN_TOKEN_ENV",
    "DEFAULT_SESSION_TTL_SECONDS",
    "LOCAL_HOSTS",
    "SESSION_COOKIE_NAME",
    "SESSION_LOCK",
    "SESSION_MANAGER",
    "SESSIONS",
    "WebSession",
    "admin_token_from_headers",
    "allow_remote_requests",
    "brain_session_credentials",
    "clear_brain_connection_verified",
    "clear_brain_session_credentials",
    "configure_session_policy",
    "create_session",
    "csrf_for_session",
    "expire_session",
    "expired_session_cookie_header",
    "extract_session_from_request",
    "get_or_create_session",
    "has_valid_admin_token",
    "has_valid_request_session",
    "header_hostname",
    "header_port",
    "is_allowed_local_request",
    "is_allowed_request",
    "mark_brain_connection_verified",
    "new_session_id",
    "normalize_host",
    "parse_cookies",
    "path_requires_session",
    "payload_with_brain_session_credentials",
    "prune_sessions",
    "remote_admin_required",
    "remote_admin_token_env",
    "require_remote_admin_token",
    "session_allow_multiple",
    "session_cookie_header",
    "session_end_payload",
    "session_id_from_cookie",
    "session_status",
    "session_ttl_seconds",
    "set_remote_policy",
    "store_brain_session_credentials",
    "stream_token_for_session",
    "validate_admin_token",
    "validate_replay_request",
    "validate_request_session",
    "validate_session",
    "validate_session_token",
    "validate_stream_session",
]

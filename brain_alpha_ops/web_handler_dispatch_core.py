"""Core dispatch primitives for the local web console.

P1-5 refactor: extracted the route-dispatch core loop and its
helper-agnostic utilities from ``web_handler_dispatch.py`` (1094 lines)
into a dedicated module so the heavy per-route handler definitions can
stay co-located without bloating the top-level file.

This module contains:
  - ``dispatch_get_core`` / ``dispatch_post_core`` thin wrappers
  - ``dispatch_route`` — the central route dispatcher
  - ``apply_rate_limit`` and friends
  - ``_rate_limit_key`` helper

It does NOT define the per-route handlers (those stay in
``web_handler_dispatch.py`` because they share many private helpers
with that module).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.redaction import redact_text

logger = logging.getLogger(__name__)

# Constant copied from web_handler_dispatch.py so this module is
# self-sufficient.  Kept verbatim to preserve behaviour.
_LEGACY_FALLBACK_DISABLED_POST_PATHS = frozenset({"/api/pipeline/start"})

def error_response(payload: dict, *, fallback_kind: str | None = None) -> dict:
    """Return error payload with state-contract enrichment.

    Imported lazily by web_handler_dispatch to avoid hard-coupling.
    """
    from brain_alpha_ops.web_state_contract import enrich_error_payload

    return enrich_error_payload(payload, fallback_kind=fallback_kind)

def rate_limit_key(handler: Any) -> str:
    """Derive the per-handler rate-limit key.

    Order: session_id → client_address → host.  Mirrors the original
    implementation in web_handler_dispatch.py.
    """
    session_getter = getattr(handler, "_session_id_from_cookie", None)
    if callable(session_getter):
        session_id = str(session_getter() or "").strip()
        if session_id:
            return f"session:{session_id}"
    client_address = getattr(handler, "client_address", ("local", 0))
    if isinstance(client_address, tuple) and client_address:
        return f"client:{client_address[0]}"
    headers = getattr(handler, "headers", {}) or {}
    return f"host:{headers.get('Host', 'local')}"

def apply_rate_limit(handler: Any, ctx: Any, method: str, path: str) -> bool:
    """Apply the configured per-bucket rate limit. Returns False if rejected."""
    from brain_alpha_ops.web_state_contract import enrich_error_payload

    rate_result = ctx.rate_limit_request(rate_limit_key(handler), method, path)
    if rate_result.get("ok"):
        return True
    retry_value = rate_result.get("retry_after") or 1
    try:
        retry_after = str(int(float(retry_value)))
    except (TypeError, ValueError):
        retry_after = "1"
    handler._json(
        error_response({"ok": False, **rate_result}, fallback_kind="web_rate_limited"),
        status=429,
        extra_headers=[("Retry-After", retry_after)],
    )
    return False

def dispatch_route(
    method: str,
    handler: Any,
    parsed: Any,
    ctx: Any,
    handlers: dict[str, Callable[..., None]],
    *,
    error_response_fn: Callable[..., dict] = error_response,
) -> None:
    """Route a single request to the right handler.

    Mirrors the original ``_dispatch_route`` in ``web_handler_dispatch.py``
    byte-for-byte except for taking ``error_response_fn`` as an injected
    dependency so this module doesn't have to import that file's private
    helper.
    """
    if not handler._is_allowed_local_request():
        handler._json(
            error_response_fn(
                {"ok": False, "error_code": "ORIGIN_FORBIDDEN", "error": "forbidden local request origin"}
            ),
            status=403,
        )
        return
    route = ctx.route_for(method, parsed.path)
    if not route:
        if method == "POST" and parsed.path in _LEGACY_FALLBACK_DISABLED_POST_PATHS:
            handler._json(
                error_response_fn(
                    {"ok": False, "error_code": "LEGACY_ROUTE_DISABLED", "error": "legacy pipeline route is disabled; use /api/run"}
                ),
                status=404,
            )
            return
        # P0-4 fix: extend session validation to unknown GET API routes
        # as well.  Previously only POST fell through to the session check;
        # an unregistered GET /api/* path could reach the legacy dispatch
        # without any session validation.
        if method not in {"GET", "HEAD", "OPTIONS"} or (
            method in {"GET", "HEAD"} and parsed.path.startswith("/api/")
        ):
            if not handler._has_valid_session(parsed.query):
                handler._json(
                    error_response_fn({"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}),
                    status=403,
                )
                return
            replay_validator = getattr(handler, "_validate_replay_request", None)
            if callable(replay_validator):
                replay_result = replay_validator()
                if not replay_result.get("ok"):
                    status = 409 if replay_result.get("error_code") == "REPLAY_DETECTED" else 400
                    handler._json(error_response_fn({"ok": False, **replay_result}), status=status)
                    return
            if not apply_rate_limit(handler, ctx, method, parsed.path):
                return
        try:
            from brain_alpha_ops.web import dispatch_post as _legacy_dispatch

            body = handler._read_json() if method == "POST" else None
            _legacy_dispatch(handler, parsed.path, body)
            return
        except ImportError:
            logger.debug("Legacy dispatch not available for %s %s", method, redact_text(str(parsed.path)))
        except Exception as _legacy_exc:
            logger.error(
                "Legacy dispatch fallback failed for %s %s: %s",
                method,
                redact_text(str(parsed.path)),
                redact_text(str(_legacy_exc)),
                exc_info=True,
            )
        handler._json(error_response_fn({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}), status=404)
        return
    if route.requires_session and not handler._has_valid_session(parsed.query):
        handler._json(
            error_response_fn({"ok": False, "error_code": "SESSION_INVALID", "error": "invalid local session"}),
            status=403,
        )
        return
    if method not in {"GET", "HEAD", "OPTIONS"} and route.requires_session:
        replay_validator = getattr(handler, "_validate_replay_request", None)
        if callable(replay_validator):
            replay_result = replay_validator()
            if not replay_result.get("ok"):
                status = 409 if replay_result.get("error_code") == "REPLAY_DETECTED" else 400
                handler._json(error_response_fn({"ok": False, **replay_result}), status=status)
                return
    if getattr(route, "category", "api") == "api" and not apply_rate_limit(handler, ctx, method, parsed.path):
        return
    route_handler = handlers.get(str(route.handler))
    if route_handler is None:
        handler._json(error_response_fn({"ok": False, "error_code": "NOT_FOUND", "error": "not found"}), status=404)
        return
    try:
        route_handler(handler, parsed, ctx)
    except (BrokenPipeError, ConnectionResetError):
        logger.info("web client disconnected before response completed: %s %s", method, redact_text(parsed.path))
        return
    except Exception as exc:
        logger.error("web route dispatch failed: %s %s", method, redact_text(parsed.path), exc_info=True)
        handler._json(error_response_fn(ctx.web_error(exc, f"{method}_ROUTE_ERROR")), status=500)

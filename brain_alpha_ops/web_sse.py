"""Server-Sent Events (SSE) routing for the BRAIN Alpha Ops web console.

P1-6 (2026-06-13) final form: this module is now a *routing shim*. The
canonical implementation lives in
``web_http_handler.create_handler_class._handle_sse_stream`` and the
compatibility symbols (SSEEventType / SSEWriter / SSEStreamHandler /
is_terminal_status / sse_event_type_for_status) live in
``web_sse_compat``. This module re-exports the compatibility symbols
and exposes the only routing entry point
``handle_sse_request`` which forwards to the bound method on the
supplied ``BaseHTTPRequestHandler`` subclass.

History
-------
Originally ``web_sse.py`` defined its own SSEWriter / SSEStreamHandler
classes that duplicated ``web_http_handler._handle_sse_stream``. Phase 3
(2026-06-13) turned the module into a shim and Phase 4 (2026-06-13)
moved the compatibility classes to ``web_sse_compat`` so the SSE
routing has a single source of truth in ``web_http_handler`` and the
compatibility layer is isolated.
"""

from __future__ import annotations

from typing import Any

# Compatibility re-exports. Tests and third-party tooling import these
# names from ``brain_alpha_ops.web_sse``; keep them available here so
# nothing breaks.
from brain_alpha_ops.web_sse_compat import (  # noqa: F401
    SSE_DEFAULT_TIMEOUT,
    SSE_POLL_INTERVAL,
    SSEEventType,
    SSEStreamHandler,
    SSEWriter,
    is_terminal_status,
    sse_event_type_for_status,
)


def handle_sse_request(handler: Any, query: dict) -> None:
    """Forward an SSE request to the canonical handler on ``handler``.

    The canonical implementation is the closure built by
    ``web_http_handler.create_handler_class`` and bound to the
    active ``BaseHTTPRequestHandler`` subclass — it owns session
    validation, the ``text/event-stream`` handshake, the
    max-duration cap (default 10 min) and the ``stream_timeout``
    reconnect signal. We simply forward.

    For the rare case where ``handler`` does not have a bound
    ``_handle_sse_stream`` method (third-party test fixtures that
    mount a stand-alone handler), we fall back to the historical
    ``SSEStreamHandler`` path so those callers keep working.
    """
    bound = getattr(handler, "_handle_sse_stream", None)
    if bound is not None:
        from urllib.parse import urlencode

        if isinstance(query, dict):
            query_string = urlencode(
                [
                    (k, v)
                    for k, vs in query.items()
                    for v in (vs if isinstance(vs, list) else [vs])
                ]
            )
        else:
            query_string = ""
        bound(query_string)
        return

    # Legacy fallback for third-party test handlers.
    job_id = ""
    if isinstance(query, dict):
        values = query.get("job_id") or []
        job_id = str(values[0] if values else "")
    stream_handler = SSEStreamHandler(handler, job_id)
    stream_handler._send_headers()
    stream_handler.handle()


# Backward-compat helpers that historically lived here. They are thin
# wrappers around the canonical classes and exist only so existing
# ``from brain_alpha_ops.web_sse import _handle_sse`` and
# ``from brain_alpha_ops.web_sse import _write_sse`` calls keep
# working without modification.
def _handle_sse(handler: Any, query: dict) -> None:
    """Handle SSE request (backward compatible)."""
    handle_sse_request(handler, query)


def _write_sse(handler: Any, payload: dict) -> None:
    """Write SSE event (backward compatible)."""
    writer = SSEWriter(handler)
    event_type = payload.get("type", "progress")
    writer.write_event(event_type, payload)


__all__ = [
    "handle_sse_request",
    "_handle_sse",
    "_write_sse",
    "SSEEventType",
    "SSEWriter",
    "SSEStreamHandler",
    "SSE_DEFAULT_TIMEOUT",
    "SSE_POLL_INTERVAL",
    "is_terminal_status",
    "sse_event_type_for_status",
]

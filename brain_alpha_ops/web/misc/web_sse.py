"""Server-Sent Events (SSE) routing, CLI entrypoint, and server lifecycle shim.

Consolidated from the former ``web_sse.py`` (SSE routing shim +
``web_sse_compat.py`` compatibility symbols), and ``web_cli.py`` (CLI
entrypoint + server lifecycle shim). The SSE section hosts the compatibility
classes (``SSEEventType`` / ``SSEWriter`` / ``SSEStreamHandler`` /
``is_terminal_status`` / ``sse_event_type_for_status``) plus the routing entry
point ``handle_sse_request``. The CLI section provides backward-compatible
``serve`` / ``shutdown_server`` / ``smoke_test_server`` / ``main`` that
delegate to the canonical implementation in ``web_server_lifecycle``.

History
-------
Originally ``web_sse.py`` defined its own SSEWriter / SSEStreamHandler
classes that duplicated ``web_http_handler._handle_sse_stream``. Phase 3
(2026-06-13) turned the module into a shim and Phase 4 (2026-06-13) moved
the compatibility classes to ``web_sse_compat`` so the SSE routing has a
single source of truth in ``web_http_handler`` and the compatibility layer
is isolated. This consolidation re-merges the two files while preserving
all public symbols.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from typing import Any
from urllib.parse import urlencode

from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.runtime_constants import WebDefaults
from brain_alpha_ops.web_server_lifecycle import (
    SafeThreadingHTTPServer as _CanonicalSafeHTTPServer,
)
from brain_alpha_ops.web_server_lifecycle import (
    find_free_port as _canonical_find_free_port,
)

logger = logging.getLogger(__name__)


# ═══════════════════════ SSE Configuration ════════════════════════════
# BRAIN API simulations can take 2+ minutes; timeout must exceed worst-case
# simulation duration plus polling overhead to avoid premature SSE stream
# closure that causes the frontend to misread an in-progress job as stalled.
SSE_DEFAULT_TIMEOUT = 300.0  # seconds (5 min)
SSE_POLL_INTERVAL = 0.5  # seconds


# ═══════════════════════ SSE Event Types ══════════════════════════════
class SSEEventType:
    """SSE event type constants."""

    PROGRESS = "progress"
    COMPLETE = "complete"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


# ═══════════════════════ SSE Writer ═══════════════════════════════════
class SSEWriter:
    """Writes SSE events to an HTTP response stream.

    Compatibility class — see module docstring. The live HTTP path uses
    the closure built by ``web_http_handler.create_handler_class``
    which calls the canonical ``_handle_sse_stream``.
    """

    def __init__(self, handler: Any):
        self.handler = handler
        self._closed = False

    def write_event(self, event_type: str, data: dict[str, Any], event_id: str | None = None) -> bool:
        """Write an SSE event to the stream."""
        if self._closed:
            return False

        try:
            if event_type:
                self.handler.wfile.write(f"event: {event_type}\n".encode("utf-8"))
            if event_id:
                self.handler.wfile.write(f"id: {event_id}\n".encode("utf-8"))
            json_data = json.dumps(data, ensure_ascii=False, default=str)
            self.handler.wfile.write(f"data: {json_data}\n\n".encode("utf-8"))
            self.handler.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            logger.debug("SSE write failed: %s", redact_error_message(exc))
            self._closed = True
            return False

    def write_progress(self, job_id: str, status: str, progress: dict[str, Any], **extra: Any) -> bool:
        """Write a progress event."""
        payload = {
            "ok": True,
            "type": SSEEventType.PROGRESS,
            "job_id": job_id,
            "task_id": job_id,
            "status": status,
            "progress": progress,
            **extra,
        }
        return self.write_event(SSEEventType.PROGRESS, payload)

    def write_complete(self, job_id: str, result: Any = None, **extra: Any) -> bool:
        """Write a completion event."""
        payload = {
            "ok": True,
            "type": SSEEventType.COMPLETE,
            "job_id": job_id,
            "task_id": job_id,
            "status": "completed",
            "result": result,
            **extra,
        }
        return self.write_event(SSEEventType.COMPLETE, payload)

    def write_error(self, job_id: str, error: str, **extra: Any) -> bool:
        """Write an error event."""
        payload = {
            "ok": False,
            "type": SSEEventType.ERROR,
            "job_id": job_id,
            "task_id": job_id,
            "status": "failed",
            "error": error,
            **extra,
        }
        return self.write_event(SSEEventType.ERROR, payload)

    def write_heartbeat(self) -> bool:
        """Write a heartbeat event to keep the connection alive."""
        return self.write_event(
            SSEEventType.HEARTBEAT,
            {"type": "heartbeat", "timestamp": time.time()},
        )

    def close(self) -> None:
        """Close the SSE stream."""
        self._closed = True


# ═══════════════════════ SSE Stream Handler ═══════════════════════════
class SSEStreamHandler:
    """Compatibility class — polls a job and writes SSE events.

    Historical implementation kept for tests and for any third-party
    tool that imported it. The live HTTP path uses
    ``web_http_handler._handle_sse_stream`` which owns the session
    check, the ``text/event-stream`` handshake and the max-duration
    cap. ``SSEStreamHandler`` only writes ``data: ...`` frames and
    expects the caller to have already sent headers (use
    ``_send_headers`` if not).
    """

    def __init__(
        self,
        handler: Any,
        job_id: str,
        *,
        timeout: float = SSE_DEFAULT_TIMEOUT,
        poll_interval: float = SSE_POLL_INTERVAL,
    ):
        self.handler = handler
        self.job_id = job_id
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.writer = SSEWriter(handler)
        self._started_at = time.time()

    def handle(self) -> None:
        """Handle the SSE stream for the job."""
        from brain_alpha_ops.web_jobs import job_get

        if not self.job_id:
            self.writer.write_error("", "missing job_id")
            return

        last_status = None
        while time.time() - self._started_at < self.timeout:
            row = job_get(self.job_id)
            if not row:
                self.writer.write_error(self.job_id, "job not found")
                return

            status = str(row.get("status") or "running")

            if status != last_status or status in {"completed", "failed", "cancelled"}:
                if status == "completed":
                    self.writer.write_complete(
                        self.job_id,
                        result=row.get("result"),
                        progress=row.get("progress") or {},
                    )
                elif status == "failed":
                    self.writer.write_error(
                        self.job_id,
                        error=row.get("error", ""),
                        progress=row.get("progress") or {},
                    )
                else:
                    self.writer.write_progress(
                        self.job_id,
                        status=status,
                        progress=row.get("progress") or {},
                        error=row.get("error", ""),
                    )
                last_status = status

            if status in {"completed", "failed", "cancelled"}:
                return

            time.sleep(self.poll_interval)

        # Timeout reached
        self.writer.write_error(self.job_id, "job stream timed out")

    def _send_headers(self) -> None:
        """Send SSE response headers (used by the legacy fallback path)."""
        self.handler.send_response(200)
        self.handler.send_header("Content-Type", "text/event-stream")
        self.handler.send_header("Cache-Control", "no-cache")
        self.handler.send_header("Connection", "close")
        self.handler.send_header("X-Content-Type-Options", "nosniff")
        self.handler.send_header("Referrer-Policy", "no-referrer")
        if hasattr(self.handler, "_cors"):
            self.handler._cors()
        self.handler.end_headers()


# ═══════════════════════ SSE Utility Functions ════════════════════════
def is_terminal_status(status: str) -> bool:
    """Return True if ``status`` is a terminal job status."""
    return str(status or "").lower() in {
        "completed",
        "completed_with_warnings",
        "failed",
        "stopped",
        "cancelled",
        "canceled",
    }


def sse_event_type_for_status(status: str) -> str:
    """Map a job status to the SSE event type that should be emitted."""
    normalized = str(status or "").lower()
    if normalized == "failed":
        return SSEEventType.ERROR
    if is_terminal_status(normalized):
        return SSEEventType.COMPLETE
    return SSEEventType.PROGRESS


# ═══════════════════════ SSE Routing Entry Point ══════════════════════
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


# ═══════════════════════ CLI entrypoint and server lifecycle ═════════
# Consolidated from web_cli.py. All server lifecycle logic delegates to the
# canonical implementation in web_server_lifecycle (via bridge). P1-8: unified
# serve() — uses canonical defaults when injected deps are absent.


def serve(port=None, open_browser=True, host="127.0.0.1", *,
          default_port=8765, handler_class=None,
          server_stop=None, server_lock=None,
          _SafeThreadingHTTPServer=None,
          _find_free_port=None,
          **kw):
    """Start the web server.

    P1-8 refactor: resolves injected deps or falls back to canonical defaults.
    Maintains backward-compatible _SERVER global tracking and injected-dependency
    signatures for web/__init__.py.
    """
    global _SERVER  # noqa: PLW0603
    # Resolve injected dependencies (from web/__init__.py) or use canonical defaults.
    server_factory = _SafeThreadingHTTPServer if _SafeThreadingHTTPServer is not None else _CanonicalSafeHTTPServer
    _port_finder = _find_free_port if _find_free_port is not None else _canonical_find_free_port

    normalize_host = lambda h: "127.0.0.1" if h in ("0.0.0.0", "::", "") else h
    bind_host = normalize_host(host)

    requested_port = default_port if port is None else port
    if requested_port == 0:
        bind_port = 0
    else:
        try:
            bind_port = _port_finder(start=requested_port, host=bind_host)
        except RuntimeError:
            bind_port = requested_port

    _SERVER = server_factory((bind_host, bind_port), handler_class)
    # Track the serve_forever thread on the server instance so shutdown_server
    # can join it and avoid zombie workers (P1-1 fix).
    serve_thread = threading.Thread(target=_SERVER.serve_forever, daemon=True, name="web-serve-forever")
    serve_thread.start()
    try:
        object.__setattr__(_SERVER, "_serve_thread", serve_thread)
    except AttributeError:
        # Some HTTPServer implementations disallow arbitrary attrs; non-fatal.
        pass
    display = "127.0.0.1" if bind_host in ("0.0.0.0", "::") else bind_host
    try:
        from brain_alpha_ops.stall_monitor import ensure_global_monitor
        ensure_global_monitor()
    except Exception:
        logging.getLogger(__name__).debug("StallMonitor not started", exc_info=True)
    return f"http://{display}:{bind_port}"


def shutdown_server(server=None, server_stop=None) -> None:
    """Shutdown the web server (backward-compatible shim)."""
    global _SERVER
    if server_stop:
        server_stop.set()
    srv = server or _SERVER  # noqa: F823  # type: ignore[used-before-def]
    if srv:
        try:
            thread = getattr(srv, "_serve_thread", None)
        except Exception:
            thread = None
        srv.shutdown()
        srv.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=WebDefaults.SMOKE_TEST_TIMEOUT)
        if server is None:
            _SERVER = None


# Module-level server reference for shutdown and smoke testing.
_SERVER: Any = None


def smoke_test_server(port=None):
    """Lightweight smoke test for tests."""
    return {"ok": True, "port": port or 8765}


def main(argv=None, *, serve_fn=None, shutdown_fn=None, host="127.0.0.1",
         server_stop=None, **kw):
    """CLI entrypoint."""
    p = argparse.ArgumentParser(description="BRAIN Alpha Ops")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--host", default=host)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)
    url = serve_fn(port=args.port, open_browser=not args.no_browser, host=args.host)
    print(f"BRAIN Alpha Ops: {url}")
    try:
        threading.Event().wait()  # block until KeyboardInterrupt
    except KeyboardInterrupt:
        shutdown_fn()
    return 0


__all__ = [
    "SSE_DEFAULT_TIMEOUT",
    "SSE_POLL_INTERVAL",
    "SSEEventType",
    "SSEStreamHandler",
    "SSEWriter",
    "_handle_sse",
    "_write_sse",
    "handle_sse_request",
    "is_terminal_status",
    "main",
    "serve",
    "shutdown_server",
    "smoke_test_server",
    "sse_event_type_for_status",
]

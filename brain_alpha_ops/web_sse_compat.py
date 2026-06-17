"""SSE compatibility shim for the BRAIN Alpha Ops web console.

P1-6 (2026-06-13): The historical ``web_sse.py`` previously defined its
own ``SSEEventType`` / ``SSEWriter`` / ``SSEStreamHandler`` classes that
duplicated the canonical ``web_http_handler._handle_sse_stream``
implementation. Phase 4 splits those into this module so that:

* ``web_http_handler.create_handler_class._handle_sse_stream`` is the
  *single* source of truth for the live HTTP path (handles session
  validation, the ``text/event-stream`` handshake, the max-duration
  cap and the ``stream_timeout`` reconnect signal).
* This module hosts the *compatibility* symbols that tests and
  third-party tooling import (``SSEEventType``, ``SSEWriter``,
  ``SSEStreamHandler``, ``is_terminal_status``,
  ``sse_event_type_for_status``).
* ``web_sse.py`` re-exports everything from here so existing
  ``from brain_alpha_ops.web_sse import ...`` statements keep working
  unchanged.

The behaviour of every symbol here is identical to the previous
``web_sse.py`` definitions — the only change is *where* the code lives.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

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


__all__ = [
    "SSEEventType",
    "SSEWriter",
    "SSEStreamHandler",
    "SSE_DEFAULT_TIMEOUT",
    "SSE_POLL_INTERVAL",
    "is_terminal_status",
    "sse_event_type_for_status",
]

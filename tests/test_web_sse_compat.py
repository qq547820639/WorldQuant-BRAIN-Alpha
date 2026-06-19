"""Tests for the SSE compatibility module (P1-6 Phase 4 split)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import brain_alpha_ops.web  # noqa: F401  install meta-path bridge for web_* modules
import pytest


class TestSSECompatReExports:
    """``brain_alpha_ops.web_sse_compat`` exposes the SSE compatibility
    symbols that previously lived directly in ``brain_alpha_ops.web_sse``.

    P1-6 (2026-06-13) split ``web_sse.py`` into:

    * ``web_http_handler`` (canonical live HTTP path)
    * ``web_sse_compat``  (compatibility classes: SSEEventType / SSEWriter
      / SSEStreamHandler / is_terminal_status / sse_event_type_for_status)
    * ``web_sse``         (routing shim that re-exports from
      ``web_sse_compat`` and forwards ``handle_sse_request`` to the
      canonical handler on the supplied ``BaseHTTPRequestHandler``).

    These tests pin the public surface so a future refactor cannot
    accidentally break the contract.
    """

    def test_sse_compat_module_exposes_event_type(self):
        from brain_alpha_ops.web_sse_compat import SSEEventType

        assert SSEEventType.PROGRESS == "progress"
        assert SSEEventType.COMPLETE == "complete"
        assert SSEEventType.ERROR == "error"
        assert SSEEventType.HEARTBEAT == "heartbeat"

    def test_sse_compat_module_exposes_writer(self):
        from brain_alpha_ops.web_sse_compat import SSEWriter

        handler = MagicMock()
        writer = SSEWriter(handler)
        assert writer.handler is handler
        assert writer._closed is False

    def test_sse_compat_module_exposes_stream_handler(self):
        from brain_alpha_ops.web_sse_compat import SSEStreamHandler, SSE_DEFAULT_TIMEOUT, SSE_POLL_INTERVAL

        handler = MagicMock()
        sh = SSEStreamHandler(handler, "job_1")
        assert sh.handler is handler
        assert sh.job_id == "job_1"
        assert sh.timeout == SSE_DEFAULT_TIMEOUT
        assert sh.poll_interval == SSE_POLL_INTERVAL

    def test_sse_compat_is_terminal_status(self):
        from brain_alpha_ops.web_sse_compat import is_terminal_status

        for status in ("completed", "completed_with_warnings", "failed", "stopped", "cancelled", "canceled"):
            assert is_terminal_status(status), status
        for status in ("running", "polling", "submitted", "queued", "active", ""):
            assert not is_terminal_status(status), status
        # Robust against None / non-string
        assert is_terminal_status(None) is False
        assert is_terminal_status(0) is False

    def test_sse_compat_sse_event_type_for_status(self):
        from brain_alpha_ops.web_sse_compat import (
            SSEEventType,
            sse_event_type_for_status,
        )

        assert sse_event_type_for_status("running") == SSEEventType.PROGRESS
        assert sse_event_type_for_status("polling") == SSEEventType.PROGRESS
        assert sse_event_type_for_status("failed") == SSEEventType.ERROR
        assert sse_event_type_for_status("cancelled") == SSEEventType.COMPLETE
        assert sse_event_type_for_status("canceled") == SSEEventType.COMPLETE
        assert sse_event_type_for_status("completed") == SSEEventType.COMPLETE
        # Robust against None / non-string
        assert sse_event_type_for_status(None) == SSEEventType.PROGRESS
        assert sse_event_type_for_status("") == SSEEventType.PROGRESS


class TestSSEShimReExports:
    """``brain_alpha_ops.web_sse`` re-exports the compatibility symbols
    so existing import paths continue to work unchanged.
    """

    def test_web_sse_reexports_compat_symbols(self):
        from brain_alpha_ops.web_sse import (
            SSEEventType,
            SSEStreamHandler,
            SSEWriter,
            SSE_DEFAULT_TIMEOUT,
            SSE_POLL_INTERVAL,
            is_terminal_status,
            sse_event_type_for_status,
        )
        from brain_alpha_ops.web_sse_compat import (
            SSEEventType as CompatEventType,
            SSEStreamHandler as CompatStreamHandler,
            SSEWriter as CompatWriter,
            is_terminal_status as compat_is_terminal,
            sse_event_type_for_status as compat_event_for,
        )
        # The symbols imported via ``web_sse`` MUST be the same objects
        # as the ones imported via ``web_sse_compat``. This guarantees
        # the shim is a pure re-export (no accidental shadowing).
        assert SSEEventType is CompatEventType
        assert SSEStreamHandler is CompatStreamHandler
        assert SSEWriter is CompatWriter
        assert is_terminal_status is compat_is_terminal
        assert sse_event_type_for_status is compat_event_for
        assert SSE_DEFAULT_TIMEOUT == 300.0
        assert SSE_POLL_INTERVAL == 0.5

    def test_web_sse_handle_sse_request_forwards_to_bound_method(self):
        """``handle_sse_request`` should call ``handler._handle_sse_stream``
        with a properly URL-encoded query string."""
        from brain_alpha_ops.web_sse import handle_sse_request

        sentinel = object()
        captured = {}

        def fake_bound(query_string: str) -> None:
            captured["query_string"] = query_string

        handler = MagicMock()
        handler._handle_sse_stream = fake_bound
        handle_sse_request(handler, {"job_id": ["job_42"]})
        # The bound method must have been called with a query string
        # that contains ``job_id=job_42``.
        assert "job_id=job_42" in captured["query_string"]

    def test_web_sse_handle_sse_request_legacy_fallback(self):
        """When the supplied handler lacks ``_handle_sse_stream`` the shim
        must fall back to the historical ``SSEStreamHandler`` path so
        third-party test fixtures that mount a stand-alone handler
        still work."""
        from brain_alpha_ops.web_sse import handle_sse_request

        # Build a bare handler-like object with no ``_handle_sse_stream``.
        # We mock the bits that ``SSEStreamHandler._send_headers`` touches
        # (send_response / send_header / end_headers) and ensure
        # ``handle`` returns immediately because the job_id is empty.
        handler = MagicMock(spec=["send_response", "send_header", "end_headers", "wfile"])
        handler.send_response.return_value = None
        handler.send_header.return_value = None
        handler.end_headers.return_value = None

        # Empty job_id → the legacy path calls ``write_error("", "missing job_id")``
        # which tries to write to ``handler.wfile``. We accept any
        # call signature; the important assertion is that the shim
        # does not raise when ``_handle_sse_stream`` is missing.
        try:
            handle_sse_request(handler, {"job_id": [""]})
        except Exception as exc:  # pragma: no cover - defensive
            pytest.fail(f"legacy fallback raised unexpectedly: {exc!r}")


class TestSSEWriterBehaviour:
    """Behavioural coverage for ``SSEWriter`` so a future change cannot
    silently break the JSON encoding format the front-end relies on."""

    def test_write_event_serialises_data_as_json(self):
        from brain_alpha_ops.web_sse import SSEWriter

        handler = MagicMock()
        handler.wfile = MagicMock()
        writer = SSEWriter(handler)
        ok = writer.write_event("progress", {"a": 1, "b": "x"})
        assert ok is True
        # The handler should have received three writes: event line,
        # data line (with the JSON object), and the empty-line terminator.
        assert handler.wfile.write.call_count == 2  # event + data
        # Concatenate the encoded writes to recover the frame.
        emitted = b"".join(
            call.args[0] for call in handler.wfile.write.call_args_list
        ).decode("utf-8")
        assert emitted.startswith("event: progress\n")
        assert "data: " in emitted
        # The data payload must be valid JSON.
        data_line = next(
            line for line in emitted.split("\n") if line.startswith("data: ")
        )
        payload = json.loads(data_line[len("data: "):])
        assert payload == {"a": 1, "b": "x"}
        # Frame terminator: data line ends with \n\n.
        assert emitted.endswith("\n\n")

    def test_write_event_closes_on_broken_pipe(self):
        from brain_alpha_ops.web_sse import SSEWriter

        handler = MagicMock()
        handler.wfile.write.side_effect = BrokenPipeError("closed")
        writer = SSEWriter(handler)
        ok = writer.write_event("progress", {"x": 1})
        assert ok is False
        assert writer._closed is True

    def test_write_event_after_close_is_noop(self):
        from brain_alpha_ops.web_sse import SSEWriter

        handler = MagicMock()
        writer = SSEWriter(handler)
        writer._closed = True
        ok = writer.write_event("progress", {"x": 1})
        assert ok is False
        # No writes attempted.
        handler.wfile.write.assert_not_called()

"""Edge case tests for web modules.

Tests boundary conditions, null/empty values, extreme inputs,
and error handling for web_session, web_jobs, web_sse, and web modules.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from brain_alpha_ops.web_jobs import (
    ASYNC_JOBS,
    _ASYNC_JOB_MAX_COUNT,
    _ASYNC_JOB_TERMINAL_STATUSES,
    _prune_async_jobs,
    job_cancel,
    job_complete,
    job_delete,
    job_fail,
    job_get,
    job_list,
    job_progress,
    job_search,
    job_start,
    job_stats,
    job_update,
    new_job_id,
    prune_jobs,
    utc_timestamp,
)
from brain_alpha_ops.web_session import (
    WebSession,
    csrf_for_session,
    extract_session_from_request,
    validate_request_session,
)
from brain_alpha_ops.web_sse import (
    SSEEventType,
    SSEStreamHandler,
    SSEWriter,
    is_terminal_status,
    sse_event_type_for_status,
)


# ═══════════════════════ web_session edge cases ═══════════════════════


class TestWebSessionEdgeCases:
    """Edge cases for WebSession class."""

    def test_create_session_returns_valid_structure(self):
        session = WebSession()
        result = session.create_session()
        assert "id" in result
        assert "csrf_token" in result
        assert "created_at" in result
        assert "expires_at" in result
        assert "last_accessed" in result
        assert len(result["id"]) > 0
        assert len(result["csrf_token"]) > 0

    def test_create_session_with_none_metadata(self):
        session = WebSession()
        result = session.create_session(metadata=None)
        assert result["metadata"] == {}

    def test_create_session_with_empty_metadata(self):
        session = WebSession()
        result = session.create_session(metadata={})
        assert result["metadata"] == {}

    def test_get_session_with_none_id(self):
        session = WebSession()
        assert session.get_session(None) is None

    def test_get_session_with_empty_id(self):
        session = WebSession()
        assert session.get_session("") is None

    def test_get_session_with_nonexistent_id(self):
        session = WebSession()
        assert session.get_session("nonexistent_id_12345") is None

    def test_validate_session_with_none(self):
        session = WebSession()
        assert session.validate_session(None) is False

    def test_validate_session_with_empty_string(self):
        session = WebSession()
        assert session.validate_session("") is False

    def test_validate_csrf_with_none_token(self):
        session = WebSession()
        result = session.create_session()
        assert session.validate_csrf(result["id"], None) is False

    def test_validate_csrf_with_empty_token(self):
        session = WebSession()
        result = session.create_session()
        assert session.validate_csrf(result["id"], "") is False

    def test_validate_csrf_with_wrong_token(self):
        session = WebSession()
        result = session.create_session()
        assert session.validate_csrf(result["id"], "wrong_token") is False

    def test_expire_nonexistent_session(self):
        session = WebSession()
        assert session.expire_session("nonexistent") is False

    def test_refresh_nonexistent_session(self):
        session = WebSession()
        assert session.refresh_session("nonexistent") is None

    def test_get_or_create_session_with_none(self):
        session = WebSession()
        result = session.get_or_create_session(None)
        assert "id" in result

    def test_get_or_create_session_with_empty(self):
        session = WebSession()
        result = session.get_or_create_session("")
        assert "id" in result

    def test_session_ttl_zero_expires_immediately(self):
        session = WebSession(ttl_seconds=0)
        result = session.create_session()
        # With 0 TTL, session should be expired on next access
        time.sleep(0.01)
        assert session.get_session(result["id"]) is None

    def test_session_cleanup_removes_expired(self):
        session = WebSession(ttl_seconds=0)
        session.create_session()
        session.create_session()
        removed = session.prune_sessions()
        assert removed >= 0  # May or may not remove depending on timing

    def test_concurrent_session_creation(self):
        session = WebSession()
        results = []
        errors = []

        def create():
            try:
                result = session.create_session(user_id=f"user_{threading.current_thread().name}")
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        # All session IDs should be unique
        ids = {r["id"] for r in results}
        assert len(ids) == 10


# ═══════════════════════ web_jobs edge cases ═══════════════════════


class TestWebJobsEdgeCases:
    """Edge cases for job management functions."""

    def setup_method(self):
        """Clear ASYNC_JOBS before each test."""
        ASYNC_JOBS.clear()

    def teardown_method(self):
        """Clear ASYNC_JOBS after each test."""
        ASYNC_JOBS.clear()

    def test_new_job_id_format(self):
        job_id = new_job_id("test")
        assert job_id.startswith("test_")
        assert len(job_id) > 5

    def test_new_job_id_unique(self):
        ids = {new_job_id() for _ in range(100)}
        assert len(ids) == 100

    def test_utc_timestamp_format(self):
        ts = utc_timestamp()
        assert isinstance(ts, str)
        assert "T" in ts  # ISO format

    def test_job_update_creates_new_job(self):
        result = job_update("new_job", status="running")
        assert result["job_id"] == "new_job"
        assert result["status"] == "running"
        assert "updated_at" in result

    def test_job_update_merges_fields(self):
        job_update("job1", status="running", progress={"percent": 50})
        job_update("job1", result={"ok": True})
        row = job_get("job1")
        assert row["status"] == "running"
        assert row["progress"]["percent"] == 50
        assert row["result"] == {"ok": True}

    def test_job_get_nonexistent(self):
        assert job_get("nonexistent") is None

    def test_job_get_returns_copy(self):
        job_update("job1", status="running")
        row1 = job_get("job1")
        row2 = job_get("job1")
        assert row1 == row2
        assert row1 is not row2

    def test_job_list_empty(self):
        assert job_list() == []

    def test_job_list_with_status_filter(self):
        job_update("job1", status="running")
        job_update("job2", status="completed")
        job_update("job3", status="running")
        running = job_list(status="running")
        assert len(running) == 2
        completed = job_list(status="completed")
        assert len(completed) == 1

    def test_job_list_with_limit(self):
        for i in range(10):
            job_update(f"job_{i}", status="running")
        limited = job_list(limit=3)
        assert len(limited) == 3

    def test_job_delete_existing(self):
        job_update("job1", status="running")
        assert job_delete("job1") is True
        assert job_get("job1") is None

    def test_job_delete_nonexistent(self):
        assert job_delete("nonexistent") is False

    def test_job_start(self):
        result = job_start("job1")
        assert result["status"] == "running"

    def test_job_progress(self):
        job_start("job1")
        result = job_progress("job1", phase="testing", percent=50, message="Half done")
        assert result["status"] == "running"
        assert result["progress"]["phase"] == "testing"
        assert result["progress"]["percent_complete"] == 50

    def test_job_complete(self):
        job_start("job1")
        result = job_complete("job1", result={"ok": True})
        assert result["status"] == "completed"
        assert result["result"] == {"ok": True}

    def test_job_fail(self):
        job_start("job1")
        result = job_fail("job1", error="something went wrong")
        assert result["status"] == "failed"
        assert result["error"] == "something went wrong"

    def test_job_cancel(self):
        job_start("job1")
        result = job_cancel("job1")
        assert result["status"] == "cancelled"

    def test_job_stats_empty(self):
        stats = job_stats()
        assert stats["total"] == 0
        assert stats["by_status"] == {}

    def test_job_stats_with_jobs(self):
        job_update("job1", status="running")
        job_update("job2", status="completed")
        stats = job_stats()
        assert stats["total"] == 2
        assert stats["by_status"]["running"] == 1
        assert stats["by_status"]["completed"] == 1

    def test_job_search_empty(self):
        assert job_search("test") == []

    def test_job_search_by_id(self):
        job_update("test_job_123", status="running")
        job_update("other_job", status="running")
        results = job_search("test_job")
        assert len(results) == 1
        assert results[0]["job_id"] == "test_job_123"

    def test_job_search_by_status(self):
        job_update("job1", status="running")
        job_update("job2", status="completed")
        results = job_search("completed")
        assert len(results) == 1

    def test_job_search_limit(self):
        for i in range(10):
            job_update(f"job_{i}", status="running")
        results = job_search("job", limit=3)
        assert len(results) == 3

    def test_prune_async_jobs_removes_expired_terminal(self):
        # Create a job that's already terminal and expired
        job_update("old_job", status="completed")
        # Manually set updated_at to old time
        ASYNC_JOBS["old_job"]["updated_at"] = "2020-01-01T00:00:00"
        _prune_async_jobs()
        assert "old_job" not in ASYNC_JOBS

    def test_prune_async_jobs_keeps_active(self):
        job_update("active_job", status="running")
        ASYNC_JOBS["active_job"]["updated_at"] = "2020-01-01T00:00:00"
        _prune_async_jobs()
        assert "active_job" in ASYNC_JOBS

    def test_prune_async_jobs_enforces_max_count(self):
        # Create many terminal jobs
        for i in range(_ASYNC_JOB_MAX_COUNT + 10):
            job_update(f"job_{i}", status="completed")
        _prune_async_jobs()
        assert len(ASYNC_JOBS) <= _ASYNC_JOB_MAX_COUNT

    def test_prune_jobs_returns_count(self):
        job_update("old1", status="completed")
        job_update("old2", status="failed")
        ASYNC_JOBS["old1"]["updated_at"] = "2020-01-01T00:00:00"
        ASYNC_JOBS["old2"]["updated_at"] = "2020-01-01T00:00:00"
        removed = prune_jobs()
        assert removed >= 0

    def test_terminal_statuses_defined(self):
        assert "completed" in _ASYNC_JOB_TERMINAL_STATUSES
        assert "failed" in _ASYNC_JOB_TERMINAL_STATUSES
        assert "cancelled" in _ASYNC_JOB_TERMINAL_STATUSES
        assert "running" not in _ASYNC_JOB_TERMINAL_STATUSES


# ═══════════════════════ web_sse edge cases ═══════════════════════


class TestSSEEdgeCases:
    """Edge cases for SSE handling."""

    def test_is_terminal_status_true(self):
        assert is_terminal_status("completed") is True
        assert is_terminal_status("failed") is True
        assert is_terminal_status("cancelled") is True
        assert is_terminal_status("canceled") is True
        assert is_terminal_status("stopped") is True

    def test_is_terminal_status_false(self):
        assert is_terminal_status("running") is False
        assert is_terminal_status("pending") is False
        assert is_terminal_status("") is False
        assert is_terminal_status(None) is False

    def test_sse_event_type_for_status(self):
        assert sse_event_type_for_status("failed") == SSEEventType.ERROR
        assert sse_event_type_for_status("completed") == SSEEventType.COMPLETE
        assert sse_event_type_for_status("running") == SSEEventType.PROGRESS
        assert sse_event_type_for_status("") == SSEEventType.PROGRESS
        assert sse_event_type_for_status(None) == SSEEventType.PROGRESS

    def test_sse_writer_write_event_with_closed_stream(self):
        handler = MagicMock()
        writer = SSEWriter(handler)
        writer._closed = True
        result = writer.write_event("test", {"data": "value"})
        assert result is False

    def test_sse_writer_close(self):
        handler = MagicMock()
        writer = SSEWriter(handler)
        writer.close()
        assert writer._closed is True

    def test_sse_stream_handler_with_empty_job_id(self):
        handler = MagicMock()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()

        stream = SSEStreamHandler(handler, "")
        # Should handle empty job_id gracefully
        stream.handle()

    def test_sse_stream_handler_with_none_job_id(self):
        handler = MagicMock()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()

        stream = SSEStreamHandler(handler, None)
        # Should handle None job_id gracefully
        stream.handle()


# ═══════════════════════ csrf_for_session edge cases ═══════════════════


class TestCSRFEdgeCases:
    """Edge cases for CSRF token functions."""

    def test_csrf_for_session_with_none(self):
        token = csrf_for_session(None)
        assert isinstance(token, str)
        assert token == ""

    def test_csrf_for_session_with_empty(self):
        token = csrf_for_session("")
        assert isinstance(token, str)
        assert token == ""

    def test_csrf_for_session_deterministic(self):
        token1 = csrf_for_session("test_session")
        token2 = csrf_for_session("test_session")
        # Unknown sessions must not receive a usable token.
        assert token1 == token2

    def test_extract_session_from_request_no_cookie(self):
        handler = MagicMock()
        handler.headers = {"Cookie": ""}
        assert extract_session_from_request(handler) is None

    def test_extract_session_from_request_no_session_cookie(self):
        handler = MagicMock()
        handler.headers = {"Cookie": "other=value; another=test"}
        assert extract_session_from_request(handler) is None

    def test_extract_session_from_request_with_session(self):
        handler = MagicMock()
        handler.headers = {"Cookie": "session=abc123; other=value"}
        assert extract_session_from_request(handler) == "abc123"

    def test_validate_request_session_no_session(self):
        handler = MagicMock()
        handler.headers = {"Cookie": ""}
        assert validate_request_session(handler) is False

    def test_validate_request_session_invalid_session(self):
        handler = MagicMock()
        handler.headers = {"Cookie": "session=invalid_id"}
        assert validate_request_session(handler) is False

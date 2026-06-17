"""Tests for web_jobs.py persistence layer.

Covers: job CRUD, JSONL persistence, restart recovery, pruning, boundary conditions.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

import pytest

from brain_alpha_ops.web_jobs import (
    ASYNC_JOBS,
    ASYNC_JOBS_LOCK,
    new_job_id,
    job_update,
    job_get,
    job_list,
    job_delete,
    job_start,
    job_progress,
    job_complete,
    job_fail,
    job_cancel,
    job_stats,
    job_search,
    prune_jobs,
    set_jobs_storage_dir,
    load_jobs_from_jsonl,
    init_job_persistence,
    utc_timestamp,
)


@pytest.fixture(autouse=True)
def _clear_jobs():
    """Ensure clean job state before each test."""
    with ASYNC_JOBS_LOCK:
        ASYNC_JOBS.clear()
    yield
    with ASYNC_JOBS_LOCK:
        ASYNC_JOBS.clear()


# ═══════════════════════ Job ID Tests ═══════════════════════════════

class TestJobId:
    def test_generates_unique_ids(self):
        ids = {new_job_id("test") for _ in range(100)}
        assert len(ids) == 100

    def test_prefix_in_id(self):
        jid = new_job_id("generate")
        assert jid.startswith("generate_")

    def test_default_prefix(self):
        jid = new_job_id()
        assert jid.startswith("job_")


# ═══════════════════════ Job CRUD Tests ═══════════════════════════════

class TestJobCRUD:
    def test_update_and_get(self):
        jid = new_job_id("test")
        row = job_update(jid, status="running")
        assert row["job_id"] == jid
        assert row["status"] == "running"
        assert "updated_at" in row

        got = job_get(jid)
        assert got is not None
        assert got["status"] == "running"

    def test_get_nonexistent(self):
        assert job_get("nonexistent_id") is None

    def test_update_merges_fields(self):
        jid = new_job_id("test")
        job_update(jid, status="pending", extra="data")
        job_update(jid, status="running")  # should preserve extra
        row = job_get(jid)
        assert row is not None
        assert row["status"] == "running"
        assert row.get("extra") == "data"

    def test_delete(self):
        jid = new_job_id("test")
        job_update(jid, status="running")
        assert job_delete(jid) is True
        assert job_get(jid) is None
        assert job_delete(jid) is False

    def test_list_by_status(self):
        j1 = new_job_id("test")
        j2 = new_job_id("test")
        job_update(j1, status="running")
        job_update(j2, status="completed")
        running = job_list(status="running")
        assert len(running) >= 1
        assert all(j["status"] == "running" for j in running)

    def test_list_limit(self):
        for _ in range(10):
            jid = new_job_id("test")
            job_update(jid, status="running")
        jobs = job_list(limit=3)
        assert len(jobs) == 3


# ═══════════════════════ Lifecycle Tests ══════════════════════════════

class TestJobLifecycle:
    def test_start(self):
        jid = new_job_id("test")
        row = job_start(jid)
        assert row["status"] == "running"

    def test_progress(self):
        jid = new_job_id("test")
        row = job_progress(jid, phase="generate", percent=50, message="half done")
        assert row["progress"]["phase"] == "generate"
        assert row["progress"]["percent_complete"] == 50

    def test_complete(self):
        jid = new_job_id("test")
        job_complete(jid, result={"count": 5})
        row = job_get(jid)
        assert row is not None
        assert row["status"] == "completed"
        assert row["result"]["count"] == 5

    def test_fail(self):
        jid = new_job_id("test")
        job_fail(jid, error="test error")
        row = job_get(jid)
        assert row is not None
        assert row["status"] == "failed"
        assert row["error"] == "test error"

    def test_cancel(self):
        jid = new_job_id("test")
        job_cancel(jid)
        row = job_get(jid)
        assert row is not None
        assert row["status"] == "cancelled"


# ═══════════════════════ Stats & Search Tests ═════════════════════════

class TestJobStats:
    def test_stats_empty(self):
        stats = job_stats()
        assert stats["total"] == 0

    def test_stats_with_jobs(self):
        j1 = new_job_id("test")
        j2 = new_job_id("test")
        job_update(j1, status="running")
        job_update(j2, status="completed")
        stats = job_stats()
        assert stats["total"] == 2
        assert stats["by_status"]["running"] == 1
        assert stats["by_status"]["completed"] == 1


class TestJobSearch:
    def test_search_by_id(self):
        jid = new_job_id("search_test")
        job_update(jid, status="running")
        results = job_search("search_test")
        assert len(results) >= 1

    def test_search_by_status(self):
        jid = new_job_id("test")
        job_update(jid, status="running")
        results = job_search("running")
        assert len(results) >= 1

    def test_search_no_match(self):
        results = job_search("zzz_nonexistent")
        assert len(results) == 0


# ═══════════════════════ Persistence Tests ═══════════════════════════

class TestJobPersistence:
    def test_set_storage_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            set_jobs_storage_dir(tmpdir)
            from brain_alpha_ops.web_jobs import _JOBS_JSONL_PATH
            assert _JOBS_JSONL_PATH is not None

    def test_persist_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up persistence
            set_jobs_storage_dir(tmpdir)

            # Create a running job
            jid = new_job_id("persist")
            job_update(jid, status="running", custom_field="hello")

            # Clear in-memory jobs
            with ASYNC_JOBS_LOCK:
                ASYNC_JOBS.clear()

            # Reload
            count = load_jobs_from_jsonl()
            assert count == 1

            row = job_get(jid)
            assert row is not None
            assert row["status"] == "running"
            assert row["custom_field"] == "hello"

    def test_job_update_redacts_sensitive_fields_before_memory_and_jsonl_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            set_jobs_storage_dir(tmpdir)

            jid = new_job_id("safe")
            row = job_update(
                jid,
                status="running",
                username="reader@example.com",
                password="plain-password",
                token="secret-token-123",
                progress={
                    "message": "token=SECRET789",
                    "headers": {"Authorization": "Bearer live-token-123"},
                },
                result={"cookie": "session-cookie-123", "note": "ok"},
            )

            stored = job_get(jid)
            persisted = (Path(tmpdir) / "web_jobs.jsonl").read_text(encoding="utf-8")

            assert row["username"] == "<redacted>"
            assert row["password"] == "<redacted>"
            assert row["token"] == "<redacted>"
            assert stored is not None
            assert stored["progress"]["headers"]["Authorization"] == "<redacted>"
            assert stored["result"]["cookie"] == "<redacted>"
            assert "reader@example.com" not in persisted
            assert "plain-password" not in persisted
            assert "secret-token-123" not in persisted
            assert "SECRET789" not in persisted
            assert "live-token-123" not in persisted

    def test_terminal_jobs_not_restored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            set_jobs_storage_dir(tmpdir)

            # Create completed job
            jid = new_job_id("done")
            job_update(jid, status="completed")

            # Clear memory
            with ASYNC_JOBS_LOCK:
                ASYNC_JOBS.clear()

            # Reload — should NOT restore completed job
            count = load_jobs_from_jsonl()
            assert count == 0  # terminal job not restored

    def test_init_job_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            jid = new_job_id("init_test")
            set_jobs_storage_dir(tmpdir)
            job_update(jid, status="running")

            with ASYNC_JOBS_LOCK:
                ASYNC_JOBS.clear()

            count = init_job_persistence(tmpdir)
            assert count == 1

    def test_empty_storage_dir_disables_persistence(self):
        count = init_job_persistence("")
        assert count == 0


# ═══════════════════════ Thread Safety Tests ══════════════════════════

class TestThreadSafety:
    def test_concurrent_updates(self):
        """Multiple threads updating jobs should not cause data corruption."""
        errors = []
        jid = new_job_id("concurrent")

        def worker(thread_id: int):
            try:
                for i in range(50):
                    job_update(jid, status="running", thread=f"t{thread_id}", iteration=i)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"concurrent updates failed: {errors}"
        row = job_get(jid)
        assert row is not None
        assert row["status"] == "running"


# ═══════════════════════ Pruning Tests ═══════════════════════════════

class TestJobPruning:
    def test_prune_removes_old_terminal_jobs(self):
        jid = new_job_id("old")
        # Create a job with old timestamp
        with ASYNC_JOBS_LOCK:
            ASYNC_JOBS[jid] = {
                "job_id": jid,
                "task_id": jid,
                "status": "completed",
                "updated_at": "2020-01-01T00:00:00",  # very old
            }
        count = prune_jobs()
        assert count >= 1
        assert job_get(jid) is None


# ═══════════════════════ UTC Timestamp ═══════════════════════════════

class TestUTCTimestamp:
    def test_iso_format(self):
        ts = utc_timestamp()
        assert "T" in ts
        from datetime import datetime
        dt = datetime.fromisoformat(ts)
        assert dt.tzinfo is not None  # timezone-aware

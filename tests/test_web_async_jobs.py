from __future__ import annotations

import threading
import time

from brain_alpha_ops.tasks import JobStore
from brain_alpha_ops.web_async_jobs import progress_update, run_simple_async_job_service


class _Store:
    def __init__(self):
        self.rows = {"job_1": {}}
        self.history = []

    def update(self, job_id, **kwargs):
        self.rows.setdefault(job_id, {}).update(kwargs)
        self.history.append((job_id, dict(kwargs)))

    def get(self, job_id):
        return dict(self.rows.get(job_id) or {})

    def is_cancelled(self, job_id):
        return bool(self.rows.get(job_id, {}).get("cancel"))


def _wait_for_jobstore_heartbeat(store: JobStore, job_id: str, source: str) -> None:
    deadline = time.time() + 1.0
    while time.time() < deadline:
        with store.lock:
            row = store.jobs.get(job_id) or {}
            progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
            if progress.get("heartbeat", {}).get("source") == source:
                return
        time.sleep(0.01)
    raise AssertionError(f"heartbeat from {source} was not recorded")


def test_run_simple_async_job_service_records_success_progress_and_result():
    store = _Store()

    run_simple_async_job_service(
        "job_1",
        {"value": 1},
        store=store,
        operation="generate_candidates",
        start_phase="candidate_generation",
        start_message="Generating.",
        worker=lambda payload: {"ok": True, "count": payload["value"]},
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    row = store.rows["job_1"]
    assert row["status"] == "completed"
    assert row["result"] == {"ok": True, "count": 1}
    assert row["progress"]["task_id"] == "job_1"
    assert row["progress"]["percent_complete"] == 100
    assert row["progress"]["status_message"] == "Task completed."


def test_run_simple_async_job_service_records_failed_payload():
    store = _Store()

    run_simple_async_job_service(
        "job_1",
        {},
        store=store,
        operation="scoring_evaluate",
        start_phase="scoring",
        start_message="Scoring.",
        worker=lambda _payload: {"ok": False, "error": "not found"},
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    row = store.rows["job_1"]
    assert row["status"] == "failed"
    assert row["error"] == "not found"
    assert row["progress"]["phase"] == "failed"


def test_run_simple_async_job_service_does_not_complete_cancelled_worker_result():
    store = _Store()

    def worker(_payload):
        store.rows["job_1"]["cancel"] = True
        store.rows["job_1"]["status"] = "stopping"
        return {"ok": True, "count": 3}

    run_simple_async_job_service(
        "job_1",
        {},
        store=store,
        operation="generate_candidates",
        start_phase="candidate_generation",
        start_message="Generating.",
        worker=worker,
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    row = store.rows["job_1"]
    assert row["status"] == "stopped"
    assert row.get("result") is None
    assert row["progress"]["status_code"] == "STOPPED"
    assert "cancel" in row["progress"]["status_message"].lower()


def test_run_simple_async_job_service_heartbeats_during_long_worker():
    store = _Store()

    def worker(_payload):
        time.sleep(0.05)
        return {"ok": True}

    run_simple_async_job_service(
        "job_1",
        {},
        store=store,
        operation="scoring_evaluate",
        start_phase="scoring",
        start_message="Scoring.",
        worker=worker,
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
        heartbeat_interval_seconds=0.01,
    )

    progress = store.rows["job_1"]["progress"]
    assert store.rows["job_1"]["status"] == "completed"
    assert progress["percent_complete"] == 100
    assert any(
        isinstance(update.get("progress"), dict)
        and update["progress"].get("heartbeat", {}).get("source") == "web_async_jobs"
        for _job_id, update in store.history
    )


def test_run_simple_async_job_service_passes_optional_cancel_callback():
    store = _Store()
    seen = []

    def worker(_payload, *, cancel_callback):
        seen.append(cancel_callback())
        store.rows["job_1"]["cancel"] = True
        store.rows["job_1"]["status"] = "stopping"
        seen.append(cancel_callback())
        return {"ok": True}

    run_simple_async_job_service(
        "job_1",
        {},
        store=store,
        operation="generate_candidates",
        start_phase="candidate_generation",
        start_message="Generating.",
        worker=worker,
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
    )

    assert seen == [False, True]
    assert store.rows["job_1"]["status"] == "stopped"
    assert store.rows["job_1"].get("result") is None


def test_run_simple_async_job_service_heartbeat_preserves_stopping_status():
    store = _Store()

    def worker(_payload):
        store.rows["job_1"]["status"] = "stopping"
        time.sleep(0.03)
        store.rows["job_1"]["cancel"] = True
        return {"ok": True}

    run_simple_async_job_service(
        "job_1",
        {},
        store=store,
        operation="scoring_evaluate",
        start_phase="scoring",
        start_message="Scoring.",
        worker=worker,
        safe_error_message=str,
        error_payload=lambda exc, **kwargs: {"error": str(exc), **kwargs},
        heartbeat_interval_seconds=0.01,
    )

    assert any(
        update.get("status") == "stopping"
        and isinstance(update.get("progress"), dict)
        and update["progress"].get("heartbeat", {}).get("source") == "web_async_jobs"
        for _job_id, update in store.history
    )


def test_run_simple_async_job_service_heartbeat_does_not_mask_watchdog_timeout(tmp_path):
    store = JobStore(tmp_path / "async_jobs.json", watchdog_timeout_seconds=0.05)
    job_id = store.create()
    release_worker = threading.Event()

    def worker(_payload):
        release_worker.wait(timeout=0.3)
        return {"ok": True}

    thread = threading.Thread(
        target=run_simple_async_job_service,
        args=(job_id, {}),
        kwargs={
            "store": store,
            "operation": "scoring_evaluate",
            "start_phase": "remote_wait",
            "start_message": "Waiting for official response.",
            "worker": worker,
            "safe_error_message": str,
            "error_payload": lambda exc, **kwargs: {"error": str(exc), **kwargs},
            "heartbeat_interval_seconds": 0.01,
        },
        daemon=True,
    )
    thread.start()
    _wait_for_jobstore_heartbeat(store, job_id, "web_async_jobs")
    time.sleep(0.06)

    store.watchdog_sweep()
    row = store.get(job_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["progress"]["phase"] == "watchdog_failed"
    assert row["progress"].get("heartbeat", {}).get("source") == "web_async_jobs"

    release_worker.set()
    thread.join(timeout=1.0)
    row = store.get(job_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["progress"]["phase"] == "watchdog_failed"


def test_progress_update_records_unified_task_fields():
    store = _Store()

    progress_update(
        store,
        "job_1",
        100.0,
        operation="submit_batch",
        phase="submitting",
        message="Submitting 1/2.",
        done=1,
        total=2,
    )

    progress = store.rows["job_1"]["progress"]
    assert progress["task_id"] == "job_1"
    assert progress["operation"] == "submit_batch"
    assert progress["status_message"] == "Submitting 1/2."
    assert progress["done"] == 1
    assert progress["total"] == 2

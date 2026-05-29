from __future__ import annotations

from brain_alpha_ops.web_async_jobs import progress_update, run_simple_async_job_service


class _Store:
    def __init__(self):
        self.rows = {"job_1": {}}

    def update(self, job_id, **kwargs):
        self.rows.setdefault(job_id, {}).update(kwargs)


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

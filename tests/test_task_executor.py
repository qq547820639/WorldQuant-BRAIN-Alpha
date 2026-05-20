import time

from brain_alpha_ops.task_executor import ThreadTaskExecutor, run_job
from brain_alpha_ops.tasks import JobStore


def _ok(value):
    return {"value": value}


def _boom():
    raise ValueError("bad task")


def _slow():
    time.sleep(0.2)
    return {"late": True}


def test_thread_task_executor_records_success(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    executor = ThreadTaskExecutor(max_workers=1)
    try:
        result = run_job(store, executor, _ok, 7)
    finally:
        executor.shutdown()

    assert result.status == "completed"
    assert result.result == {"value": 7}
    assert store.get(result.job_id)["status"] == "completed"
    assert store.get(result.job_id)["progress"]["phase"] == "completed"


def test_thread_task_executor_records_failure(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    executor = ThreadTaskExecutor(max_workers=1)
    try:
        result = run_job(store, executor, _boom)
    finally:
        executor.shutdown()

    assert result.status == "failed"
    assert "bad task" in result.error
    assert store.get(result.job_id)["progress"]["phase"] == "failed"


def test_thread_task_executor_records_timeout(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    executor = ThreadTaskExecutor(max_workers=1)
    try:
        result = run_job(store, executor, _slow, timeout=0.01)
    finally:
        executor.shutdown()

    assert result.status == "failed"
    assert result.error == "task timed out"
    assert store.get(result.job_id)["progress"]["phase"] == "timeout"


def test_task_executor_respects_existing_cancel_state(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    job_id = store.create()
    store.cancel(job_id)
    executor = ThreadTaskExecutor(max_workers=1)
    try:
        result = run_job(store, executor, _ok, 1, job_id=job_id)
    finally:
        executor.shutdown()

    assert result.status == "cancelled"
    assert store.get(job_id)["status"] == "cancelled"

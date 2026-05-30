import threading
import json

from brain_alpha_ops.tasks import DEFAULT_RECOVERY_ERROR, JobStore, _compact_runtime_result


def test_job_store_persists_completed_jobs(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path)

    job_id = store.create()
    store.update(job_id, status="running", progress={"phase": "simulation", "percent": 40})
    store.update(job_id, status="completed", result={"ok": True})

    restored = JobStore(path)
    job = restored.get(job_id)

    assert job is not None
    assert job["status"] == "completed"
    assert job["result"] == {"ok": True}
    assert restored.latest_active() is None
    assert restored.latest_any()[0] == job_id


def test_job_store_recovers_interrupted_active_jobs_as_failed(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path)

    job_id = store.create()
    store.update(job_id, status="running", progress={"phase": "official_simulation", "percent": 25})

    restored = JobStore(path)
    job = restored.get(job_id)

    assert job is not None
    assert job["status"] == "failed"
    assert job["error"] == DEFAULT_RECOVERY_ERROR
    assert job["progress"]["phase"] == "failed"
    assert restored.latest_active() is None


def test_job_store_cancel_sets_stopping_and_persists(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path)

    job_id = store.create()

    assert store.cancel(job_id) is True
    assert store.is_cancelled(job_id) is True
    assert store.latest_active()[0] == job_id

    restored = JobStore(path, recover_active_as="")
    assert restored.get(job_id)["status"] == "stopping"


def test_job_store_redacts_sensitive_payloads_before_persisting(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path)

    job_id = store.create({"credentials": {"username": "user", "password": "pw", "token": "secret-token-123"}})
    store.update(
        job_id,
        error="secret-token-456 failed",
        progress={"message": "token=SECRET789", "headers": {"Authorization": "Bearer live-token-123"}},
        result={"cookie": "session-cookie-123", "note": "ok"},
    )

    job = store.get(job_id)
    persisted = path.read_text(encoding="utf-8")

    assert job["credentials"]["username"] == "<redacted>"
    assert job["credentials"]["password"] == "<redacted>"
    assert job["credentials"]["token"] == "<redacted>"
    assert "secret-token-456" not in job["error"]
    assert "SECRET789" not in job["progress"]["message"]
    assert job["progress"]["headers"]["Authorization"] == "<redacted>"
    assert job["result"]["cookie"] == "<redacted>"
    assert "secret-token-123" not in persisted
    assert "secret-token-456" not in persisted
    assert "SECRET789" not in persisted
    assert "live-token-123" not in persisted


def test_job_store_concurrent_create_update_cancel_stays_bounded(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path, max_jobs=75)
    errors: list[BaseException] = []

    def worker(worker_id: int) -> None:
        try:
            for index in range(25):
                job_id = store.create({"worker": worker_id, "index": index})
                store.update(job_id, status="running", progress={"phase": "worker", "percent": index})
                if index % 3 == 0:
                    assert store.cancel(job_id) is True
                else:
                    store.update(job_id, status="completed", result={"ok": True, "worker": worker_id})
        except BaseException as exc:  # pragma: no cover - defensive for thread failures
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(worker_id,)) for worker_id in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows = store.all()
    restored = JobStore(path, max_jobs=75, recover_active_as="")

    assert errors == []
    assert 1 <= len(rows) <= 75
    assert len(restored.all()) <= 75
    assert all(job_id.startswith("job_") for job_id, _job in rows)


def test_job_store_load_prunes_large_history_before_redaction(tmp_path):
    path = tmp_path / "jobs.json"
    jobs = {}
    for index in range(20):
        jobs[f"job_{index:04d}"] = {
            "status": "completed",
            "updated_at": index,
            "result": {"rows": [{"token": f"secret-token-{index}-{inner}"} for inner in range(20)]},
        }
    path.write_text(json.dumps({"version": 1, "jobs": jobs}), encoding="utf-8")

    restored = JobStore(path, max_jobs=5, recover_active_as="")
    rows = restored.all()

    assert len(rows) == 5
    assert [job_id for job_id, _job in rows] == [
        "job_0019",
        "job_0018",
        "job_0017",
        "job_0016",
        "job_0015",
    ]
    assert all(job["result"]["rows"]["items_count"] == 20 for _job_id, job in rows)
    assert all(
        item["token"] == "<redacted>"
        for _job_id, job in rows
        for item in job["result"]["rows"]["items_preview"]
    )


def test_compact_runtime_result_replaces_heavy_runtime_lists_with_counts_and_preview():
    result = {
        "ok": True,
        "alphas": [{"id": f"a{index}", "nested": [{"token": f"secret-token-{index}-{inner}"} for inner in range(8)]} for index in range(12)],
        "candidates": [{"alpha_id": "c1"}],
    }

    compact = _compact_runtime_result(result, preview_rows=3)

    assert "alphas" not in compact
    assert compact["alphas_count"] == 12
    assert len(compact["alphas_preview"]) == 3
    assert compact["alphas_preview"][0]["nested"]["items_count"] == 8
    assert len(compact["alphas_preview"][0]["nested"]["items_preview"]) == 3
    assert compact["candidates_count"] == 1
    assert compact["candidates_preview"] == [{"alpha_id": "c1"}]

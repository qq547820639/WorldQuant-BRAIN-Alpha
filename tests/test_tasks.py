from __future__ import annotations
import json
import threading
import time

from brain_alpha_ops.tasks import DEFAULT_RECOVERY_ERROR, DEFAULT_WATCHDOG_ERROR, JobStore, _compact_runtime_result


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


def test_job_store_watchdog_fails_stalled_active_job(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path, watchdog_timeout_seconds=5)

    job_id = store.create()
    store.update(job_id, status="running", updated_at=10.0, progress={"phase": "official_simulation", "percent": 20})

    job = store.jobs[job_id]
    assert job is not None
    assert job["status"] == "running"

    swept = store.watchdog_sweep(now=16.1)
    job = store.get(job_id)

    assert swept == 1
    assert job is not None
    assert job["status"] == "failed"
    assert job["cancel"] is True
    assert job["error"] == DEFAULT_WATCHDOG_ERROR
    assert job["progress"]["phase"] == "watchdog_failed"
    assert job["progress"]["watchdog"]["triggered"] is True
    assert store.is_cancelled(job_id) is True
    assert store.latest_active() is None


def test_job_store_watchdog_fails_unknown_status_without_waiting(tmp_path):
    store = JobStore(tmp_path / "jobs.json", watchdog_timeout_seconds=300)

    job_id = store.create()
    store.update(job_id, status="mystery", progress={"phase": "unknown", "percent": 10})

    job = store.get(job_id)

    assert job is not None
    assert job["status"] == "failed"
    assert job["cancel"] is True
    assert "status was unclear" in job["error"]
    assert job["progress"]["watchdog"]["previous_status"] == "mystery"


def test_job_store_treats_pending_and_starting_as_active_until_timeout(tmp_path):
    store = JobStore(tmp_path / "jobs.json", watchdog_timeout_seconds=10)
    base = time.time()

    pending_id = store.create()
    starting_id = store.create()
    store.update(pending_id, status="pending", updated_at=base, progress={"phase": "pending", "percent": 0})
    store.update(starting_id, status="starting", updated_at=base, progress={"phase": "simulation_starting", "percent": 0})

    assert store.watchdog_sweep(now=base + 5) == 0
    assert store.get(pending_id)["status"] == "pending"
    assert store.get(starting_id)["status"] == "starting"
    assert {job_id for job_id, _job in store.all()} >= {pending_id, starting_id}
    assert store.latest_active() is not None

    assert store.watchdog_sweep(now=base + 11) == 2
    assert store.get(pending_id)["error"] == DEFAULT_WATCHDOG_ERROR
    assert store.get(starting_id)["error"] == DEFAULT_WATCHDOG_ERROR
    assert store.get(starting_id)["progress"]["watchdog"]["previous_status"] == "starting"


def test_job_store_rejects_late_worker_updates_after_watchdog_failed(tmp_path):
    store = JobStore(tmp_path / "jobs.json", watchdog_timeout_seconds=5)

    job_id = store.create()
    store.update(job_id, status="running", updated_at=10.0, progress={"phase": "remote", "percent": 20})
    assert store.watchdog_sweep(now=16.1) == 1

    store.update(job_id, status="completed", result={"ok": True}, progress={"phase": "done", "percent": 100})
    store.update(job_id, status="running", progress={"phase": "late_retry", "percent": 50})
    job = store.get(job_id)

    assert job is not None
    assert job["status"] == "failed"
    assert job["cancel"] is True
    assert job["error"] == DEFAULT_WATCHDOG_ERROR
    assert job["progress"]["phase"] == "watchdog_failed"
    assert job.get("result") is None

    store.update(job_id, status="completed", result={"ok": True}, allow_terminal_overwrite=True)

    assert store.get(job_id)["status"] == "completed"


def test_job_store_rejects_late_failed_update_after_watchdog_failed(tmp_path):
    store = JobStore(tmp_path / "jobs.json", watchdog_timeout_seconds=5)

    job_id = store.create()
    store.update(job_id, status="running", updated_at=10.0, progress={"phase": "remote", "percent": 20})
    assert store.watchdog_sweep(now=16.1) == 1

    store.update(job_id, status="failed", error="late worker failure", progress={"phase": "failed", "percent": 100})
    job = store.get(job_id)

    assert job is not None
    assert job["status"] == "failed"
    assert job["error"] == DEFAULT_WATCHDOG_ERROR
    assert job["progress"]["phase"] == "watchdog_failed"
    assert job["progress"]["watchdog"]["triggered"] is True


def test_job_store_heartbeat_preserves_real_progress_clock(tmp_path):
    store = JobStore(tmp_path / "jobs.json", watchdog_timeout_seconds=5)
    base = time.time()

    job_id = store.create()
    store.update(job_id, status="running", updated_at=base, progress={"phase": "remote", "percent": 20})
    assert store.heartbeat(
        job_id,
        operation="sync_alphas",
        heartbeat_count=1,
        source="test",
        heartbeat_at=base + 1,
    ) is True

    first = store.get(job_id)
    assert first is not None
    assert first["updated_at"] == base
    assert first["progress"]["phase"] == "remote"
    assert first["progress"]["heartbeat"]["updated_at"] == base + 1

    store.update(job_id, status="running", updated_at=base + 2, progress={"phase": "official_progress", "percent": 60})
    assert store.heartbeat(
        job_id,
        operation="sync_alphas",
        heartbeat_count=2,
        source="test",
        heartbeat_at=base + 3,
    ) is True

    latest = store.get(job_id)
    assert latest is not None
    assert latest["updated_at"] == base + 2
    assert latest["progress"]["phase"] == "official_progress"
    assert latest["progress"]["heartbeat"]["count"] == 2


def test_job_store_cancel_sets_stopping_and_persists(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path)

    job_id = store.create()

    assert store.cancel(job_id) is True
    assert store.is_cancelled(job_id) is True
    assert store.latest_active()[0] == job_id

    restored = JobStore(path, recover_active_as="")
    assert restored.get(job_id)["status"] == "stopping"


def test_job_store_cancel_does_not_reopen_watchdog_terminal_job(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path, watchdog_timeout_seconds=5)

    job_id = store.create()
    store.update(job_id, status="running", updated_at=10.0, progress={"phase": "official_context", "percent": 10})
    assert store.watchdog_sweep(now=16.1) == 1

    assert store.cancel(job_id) is True

    job = store.get(job_id)
    assert job is not None
    assert job["status"] == "failed"
    assert job["cancel"] is True
    assert job["error"] == DEFAULT_WATCHDOG_ERROR
    assert job["progress"]["phase"] == "watchdog_failed"

    restored = JobStore(path, recover_active_as="")
    restored_job = restored.get(job_id)
    assert restored_job is not None
    assert restored_job["status"] == "failed"
    assert restored_job["progress"]["phase"] == "watchdog_failed"


def test_job_store_clear_does_not_persist_by_default(tmp_path):
    path = tmp_path / "jobs.json"
    store = JobStore(path)
    job_id = store.create()

    store.clear()

    assert store.all() == []
    assert JobStore(path, recover_active_as="").get(job_id) is not None

    store.clear(persist=True)

    assert JobStore(path, recover_active_as="").all() == []


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


def test_job_store_recovers_persistence_after_oversized_load(tmp_path):
    # F-023: persistence must NOT be permanently disabled after a single
    # oversized-load skip. When jobs change, _persist_locked retries writing
    # and resets persistence_load_skipped.
    path = tmp_path / "jobs.json"
    original = json.dumps({"version": 1, "jobs": {"job_0001": {"status": "completed"}}})
    path.write_text(original + (" " * 64), encoding="utf-8")

    store = JobStore(path, max_load_bytes=32)

    # Load was skipped because the file is oversized.
    assert store.all() == []
    assert store.persistence_load_skipped is True
    assert "too large to load safely" in store.last_persist_error

    store.create({"status": "completed", "result": {"ok": True}})

    # Persistence retried and overwrote the unreadable oversized file.
    assert store.persistence_load_skipped is False
    assert store.last_persist_error == ""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["jobs"]) == 1  # only the new job, old unreadable data replaced
    new_job = next(iter(data["jobs"].values()))
    assert new_job["result"] == {"ok": True}


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


def test_compact_runtime_result_keeps_submission_evidence_outside_preview():
    candidates = [
        {"alpha_id": f"local_{index}", "scorecard": {"decision_band": "research_only"}}
        for index in range(5)
    ]
    candidates.append(
        {
            "alpha_id": "local_hidden",
            "lifecycle_status": "generated",
            "scorecard": {"total_score": 62.0, "decision_band": "research_only"},
            "debug_payload": {"large": "not needed for submit audit"},
        }
    )
    candidates.append(
        {
            "alpha_id": "ready_hidden",
            "official_alpha_id": "official_ready_hidden",
            "lifecycle_status": "submission_ready",
            "gate": {"submission_ready": True},
            "official_metrics": {"pass_fail": "PASS"},
            "scorecard": {"decision_band": "submit_candidate"},
            "cloud_correlation_risk": {"level": "low", "max_similarity": 0.1},
        }
    )

    compact = _compact_runtime_result({"candidates": candidates}, preview_rows=5)

    assert compact["candidates_count"] == 7
    assert [item["alpha_id"] for item in compact["candidates_preview"]] == [
        "local_0",
        "local_1",
        "local_2",
        "local_3",
        "local_4",
    ]
    assert [item["alpha_id"] for item in compact["candidates_submission_evidence"]] == [
        "local_hidden",
        "ready_hidden",
    ]
    assert compact["candidates_submission_evidence"][0]["scorecard"] == {
        "total_score": 62.0,
        "decision_band": "research_only",
    }
    assert "debug_payload" not in compact["candidates_submission_evidence"][0]

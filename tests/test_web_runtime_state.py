from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from brain_alpha_ops.web_runtime_state import (
    active_auxiliary_operation,
    compute_run_stats,
    lifecycle_from_job,
    load_check_results,
    match_preset_id,
    maybe_archive_lifecycle,
    status_category,
)


class _Store:
    def __init__(self, active=None):
        self.active = active

    def latest_active(self):
        return self.active


class _Lock:
    def __init__(self, locked=False):
        self._locked = locked

    def locked(self):
        return self._locked


def test_active_auxiliary_operation_reports_first_conflict():
    conflict = active_auxiliary_operation(
        production_store=_Store(("job_1", {})),
        sync_store=_Store(("job_2", {})),
        check_store=_Store(),
        submit_lock=_Lock(True),
    )

    assert conflict[0] == "production"

    sync_conflict = active_auxiliary_operation(
        production_store=_Store(("job_1", {})),
        sync_store=_Store(("job_2", {})),
        check_store=_Store(),
        submit_lock=_Lock(True),
        allow_production=True,
    )

    assert sync_conflict[0] == "sync"


def test_compute_run_stats_counts_ready_candidates_and_active_backtests():
    stats = compute_run_stats(
        {
            "summary": {
                "produced_count": 5,
                "ready_results_count": 2,
                "official_validation_passed": 3,
                "official_validation_attempted": 4,
            },
            "candidates": [
                {"lifecycle_status": "submission_ready"},
                {"gate": {"submission_ready": True}},
                {"gate": {"submission_ready": False}},
            ],
            "backtests": [{"status": "RUNNING"}, {"status": "FAILED"}, {"status": "submitted"}],
        },
        run_config=None,
    )

    assert stats == {
        "produced_count": 5,
        "passed_count": 2,
        "active_backtests": 2,
        "ready_results_count": 2,
        "validation_tile": "3/4",
    }


def test_lifecycle_from_job_merges_dedupes_and_classifies_rows():
    stored = [
        {"run_id": "run_1", "alpha_id": "a1", "stage": "simulation", "status": "PASSED", "note": "ok"},
        {"run_id": "run_1", "alpha_id": "a2", "stage": "submission_blocked", "status": "BLOCKED", "note": "dup"},
    ]
    job = {
        "result": {
            "summary": {
                "lifecycle_records": [
                    {"run_id": "run_1", "alpha_id": "a1", "stage": "simulation", "status": "PASSED", "note": "ok"},
                    {"run_id": "run_1", "alpha_id": "a3", "stage": "submit", "status": "SUBMITTED", "note": "cloud"},
                ]
            }
        }
    }

    rows = lifecycle_from_job(job, read_storage_jsonl=lambda *_args, **_kwargs: stored)

    assert [row["alpha_id"] for row in rows] == ["a1", "a2", "a3"]
    assert [row["status_category"] for row in rows] == ["passed", "blocked", "submitted"]
    assert status_category({"status": "REJECTED"}) == "failed"


def test_load_check_results_filters_invalid_rows_and_marks_stale():
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    payload = load_check_results(
        read_storage_jsonl=lambda *_args, **_kwargs: [
            {"alpha_id": "fresh", "checked_at": (now - timedelta(hours=1)).isoformat()},
            {"alpha_id": "old", "checked_at": (now - timedelta(days=2)).isoformat()},
            {"alpha_id": "bad", "checked_at": "not-a-date"},
            {"checked_at": now.isoformat()},
        ],
        now=now,
    )

    assert payload["count"] == 3
    assert [row["is_stale"] for row in payload["items"]] == [False, True, True]


def test_load_check_results_recovers_with_warning(caplog):
    def fail(*_args, **_kwargs):
        raise OSError("boom")

    log = logging.getLogger("tests.web_runtime_state")
    with caplog.at_level("WARNING", logger="tests.web_runtime_state"):
        payload = load_check_results(read_storage_jsonl=fail, safe_error_message=lambda exc: "redacted", log=log)

    assert payload == {"items": [], "count": 0, "warning": "redacted"}
    assert "failed to load check results" in caplog.text


def test_match_preset_id_compares_settings_as_strings():
    presets = {
        "usa": {"settings": {"region": "USA", "delay": 1}},
        "china": {"settings": {"region": "CHN", "delay": 0}},
    }

    assert match_preset_id({"region": "USA", "delay": "1"}, presets) == "usa"
    assert match_preset_id({"region": "EUR", "delay": "1"}, presets) == ""


def test_maybe_archive_lifecycle_throttles_and_returns_updated_timestamp(tmp_path):
    calls = []

    class Repo:
        def __init__(self, storage_dir):
            self.storage_dir = storage_dir

        def maybe_archive(self, filename, *, max_size_mb):
            calls.append((self.storage_dir, filename, max_size_mb))

    config = type("Config", (), {"ops": type("Ops", (), {"storage_dir": str(tmp_path)})()})()

    unchanged = maybe_archive_lifecycle(
        last_archive_check=100.0,
        interval_seconds=3600.0,
        load_config=lambda: config,
        repository_factory=Repo,
        now=200.0,
    )
    updated = maybe_archive_lifecycle(
        last_archive_check=100.0,
        interval_seconds=3600.0,
        load_config=lambda: config,
        repository_factory=Repo,
        now=4000.0,
    )

    assert unchanged == 100.0
    assert updated == 4000.0
    assert calls == [(str(tmp_path), "lifecycle.jsonl", 50)]

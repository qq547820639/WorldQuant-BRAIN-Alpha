from brain_alpha_ops.research.contracts import (
    backtest_record,
    recoverable_backtest_candidates,
)
from brain_alpha_ops.models import PipelineEvent
from brain_alpha_ops.research.repository import ResearchRepository


def test_backtest_contract_adds_schema_and_correlation_id():
    row = backtest_record(
        "run_1",
        {
            "action": "submitted",
            "alpha_id": "a1",
            "simulation_id": "sim_1",
            "status": "SUBMITTED",
            "expression": "rank(close)",
        },
    )

    assert row["schema_version"] == "backtest_record.v1"
    assert row["run_id"] == "run_1"
    assert row["correlation_id"].startswith("corr_")


def test_recoverable_backtest_candidates_uses_latest_active_rows():
    rows = [
        {
            "action": "submitted",
            "slot": 1,
            "alpha_id": "old",
            "simulation_id": "sim_old",
            "status": "SUBMITTED",
            "expression": "rank(close)",
        },
        {
            "action": "completed",
            "slot": 1,
            "alpha_id": "old",
            "simulation_id": "sim_old",
            "status": "COMPLETED",
            "expression": "rank(close)",
        },
        {
            "action": "running",
            "slot": 2,
            "alpha_id": "active",
            "simulation_id": "sim_active",
            "status": "RUNNING",
            "expression": "rank(ts_delta(close, 20))",
            "poll_count": 3,
        },
    ]

    recovered = recoverable_backtest_candidates(rows, max_slots=3)

    assert len(recovered) == 1
    assert recovered[0].alpha_id == "active"
    assert recovered[0].simulation_id == "sim_active"
    assert recovered[0].submission["backtest_slot"] == 2
    assert recovered[0].submission["recovered_from_persistence"] is True


def test_repository_internal_filename_api_rejects_path_traversal(tmp_path):
    repo = ResearchRepository(str(tmp_path))

    for filename in ("../outside.jsonl", "nested/candidates.jsonl", "unknown.jsonl"):
        try:
            repo._append(filename, {"ok": True})
        except ValueError as exc:
            assert "repository" in str(exc)
        else:
            raise AssertionError(f"{filename} should be rejected")

    try:
        repo.maybe_archive("../candidates.jsonl", max_size_mb=0)
    except ValueError as exc:
        assert "repository" in str(exc)
    else:
        raise AssertionError("archive traversal should be rejected")

    assert not (tmp_path.parent / "outside.jsonl").exists()


def test_repository_allows_known_jsonl_files(tmp_path):
    repo = ResearchRepository(str(tmp_path))

    repo._append("events.jsonl", {"event": "ok"})

    assert (tmp_path / "events.jsonl").is_file()
    assert (tmp_path / "events.jsonl.lock").exists() is False


def test_repository_redacts_user_profile_event_payloads(tmp_path):
    repo = ResearchRepository(str(tmp_path))

    repo.save_event(
        "run_1",
        PipelineEvent(
            event="runtime_progress",
            message="profile loaded",
            data={
                "user_profile": {
                    "username": "researcher@example.com",
                    "raw": {
                        "email": "researcher@example.com",
                        "telephone": "+1234567890",
                        "firstName": "Research",
                        "fullName": "Research User",
                        "employment": {"employer": "Example Capital"},
                    },
                }
            },
        ),
    )

    persisted = (tmp_path / "events.jsonl").read_text(encoding="utf-8")

    assert "researcher@example.com" not in persisted
    assert "+1234567890" not in persisted
    assert "Research User" not in persisted
    assert "Example Capital" not in persisted
    assert "<redacted>" in persisted

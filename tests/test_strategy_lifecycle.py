import json

from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.strategy_lifecycle import StrategyLifecycleTracker, profile_id


def _profile(name: str, region: str = "USA") -> dict:
    return {
        "name": name,
        "region": region,
        "universe": "TOP3000",
        "delay": 1,
        "neutralization": "SUBINDUSTRY",
    }


def test_strategy_lifecycle_tracks_propose_validate_mutate_retire_and_reward():
    tracker = StrategyLifecycleTracker()
    first = _profile("usa_standard")
    second = _profile("europe_standard", "EUR")

    tracker.propose(first, index=0, cycle=0, reason="initial")
    tracker.validate(first, index=0, cycle=3, ready_rate=0.1, official_results=12, pool_size=2, trigger="chronic_official_fail")
    tracker.retire(first, index=0, cycle=3, reason="chronic_official_fail")
    tracker.mutate(first, second, parent_index=0, child_index=1, cycle=3, reason="explore")
    tracker.record_reward(second, index=1, cycle=4, reward=1.25, metrics={"avg_sharpe": 1.5})

    first_id = profile_id(first, 0)
    second_id = profile_id(second, 1)
    summary = tracker.summary(active_profile=second, active_index=1)

    assert summary["schema_version"] == "strategy_lifecycle.v1"
    assert summary["active_profile_id"] == second_id
    assert summary["lineage"][second_id] == first_id
    assert first_id in summary["retired_profile_ids"]
    assert summary["reward_summary"][second_id]["count"] == 1
    assert summary["reward_summary"][second_id]["average_reward"] == 1.25
    assert [row["action"] for row in summary["records"]] == ["propose", "validate", "retire", "mutate", "reward"]


def test_strategy_lifecycle_records_can_persist_to_repository(tmp_path):
    repo = ResearchRepository(tmp_path)
    tracker = StrategyLifecycleTracker(
        record_sink=lambda row: repo.save_strategy_lifecycle_record("run_strategy", row)
    )

    row = tracker.propose(_profile("usa_standard"), index=0, cycle=0, reason="initial")
    persisted = json.loads((tmp_path / "strategy_lifecycle.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert row["schema_version"] == "strategy_lifecycle.v1"
    assert persisted["schema_version"] == "strategy_lifecycle_record.v1"
    assert persisted["run_id"] == "run_strategy"
    assert persisted["action"] == "propose"
    assert persisted["profile_id"] == row["profile_id"]
    assert persisted["correlation_id"].startswith("corr_")

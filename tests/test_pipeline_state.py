from __future__ import annotations

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.pipeline_state import (
    CycleState,
    bandit_runtime_summary,
    compute_strategy_reward,
    record_strategy_reward,
)


def _candidate(alpha_id: str, *, sharpe: float | None = None, ready: bool = False) -> Candidate:
    candidate = Candidate(
        alpha_id=alpha_id,
        expression=f"rank({alpha_id})",
        family="test",
        hypothesis="pipeline state test",
    )
    if sharpe is not None:
        candidate.official_metrics = {"sharpe": sharpe}
    if ready:
        candidate.gate = {"submission_ready": True}
    return candidate


def test_cycle_state_defaults_are_isolated():
    first = CycleState()
    second = CycleState()

    first.archive_stats["local_rejected"] = 1
    first.blocked_expressions.add("rank(close)")

    assert second.archive_stats == {}
    assert second.blocked_expressions == set()


def test_compute_strategy_reward_uses_official_sharpe_and_ready_rate():
    snapshot = compute_strategy_reward(
        [
            _candidate("close", sharpe=1.2, ready=True),
            _candidate("open", sharpe=0.8),
            _candidate("volume", ready=True),
        ]
    )

    assert round(snapshot.reward, 6) == 0.833333
    assert snapshot.metrics == {"avg_sharpe": 1.0, "pass_rate": 0.666667, "pool_size": 3}


def test_record_strategy_reward_updates_bandit_maps_and_summary():
    rewards = {0: [0.25]}
    counts = {0: 1}

    snapshot = record_strategy_reward(0, [_candidate("close", sharpe=1.0, ready=True)], rewards, counts)

    assert snapshot.reward == 1.0
    assert rewards[0] == [0.25, 1.0]
    assert counts[0] == 2
    assert bandit_runtime_summary({"name": "usa"}, rewards, counts, total_switches=3) == {
        "active_profile": "usa",
        "profile_rewards": {"0": 0.625},
        "profile_counts": {0: 2},
        "total_switches": 3,
    }

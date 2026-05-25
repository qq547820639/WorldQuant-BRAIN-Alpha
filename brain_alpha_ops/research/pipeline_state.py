"""Runtime state helpers for the alpha research pipeline coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.models import Candidate


@dataclass
class CycleState:
    """Mutable containers shared across one research cycle."""

    pool_by_expression: dict[str, Candidate] = field(default_factory=dict)
    accepted_candidates: list[Candidate] = field(default_factory=list)
    archive_stats: dict[str, int] = field(default_factory=dict)
    archive_samples: list[Candidate] = field(default_factory=list)
    blocked_expressions: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class StrategyRewardSnapshot:
    """Computed reward and lifecycle metrics for one strategy profile."""

    reward: float
    metrics: dict[str, int | float]


def compute_strategy_reward(candidates: list[Candidate]) -> StrategyRewardSnapshot:
    """Compute the bandit reward from official Sharpe and submission readiness."""

    sharpe_values = [
        float(candidate.official_metrics.get("sharpe", 0.0) or 0.0)
        for candidate in candidates
        if candidate.official_metrics
    ]
    avg_sharpe = sum(sharpe_values) / max(len(sharpe_values), 1)
    pass_rate = sum(1 for candidate in candidates if candidate.gate.get("submission_ready")) / max(len(candidates), 1)
    reward = avg_sharpe * (0.5 + 0.5 * pass_rate)
    return StrategyRewardSnapshot(
        reward=reward,
        metrics={
            "avg_sharpe": round(avg_sharpe, 6),
            "pass_rate": round(pass_rate, 6),
            "pool_size": len(candidates),
        },
    )


def record_strategy_reward(
    profile_index: int,
    candidates: list[Candidate],
    rewards: dict[int, list[float]],
    counts: dict[int, int],
) -> StrategyRewardSnapshot:
    """Append a profile reward and update selection counts in place."""

    snapshot = compute_strategy_reward(candidates)
    rewards.setdefault(profile_index, []).append(snapshot.reward)
    counts[profile_index] = counts.get(profile_index, 0) + 1
    return snapshot


def bandit_runtime_summary(
    active_profile: dict[str, Any],
    rewards: dict[int, list[float]],
    counts: dict[int, int],
    *,
    total_switches: int,
) -> dict[str, Any]:
    """Return the Web/API runtime payload for adaptive strategy bandit state."""

    return {
        "active_profile": active_profile.get("name", "unknown"),
        "profile_rewards": {
            str(index): round(sum(values) / max(len(values), 1), 3)
            for index, values in rewards.items()
        },
        "profile_counts": counts,
        "total_switches": total_switches,
    }

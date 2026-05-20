"""Adaptive strategy switch selection helpers."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Callable


@dataclass(frozen=True)
class StrategySwitchApplication:
    """Resolved side effects for applying a selected strategy profile."""

    old_index: int
    next_index: int
    old_profile: dict[str, Any]
    next_profile: dict[str, Any]
    retained: bool
    settings: dict[str, Any]


class StrategySwitchService:
    """Pure selection logic for adaptive strategy switching."""

    def __init__(
        self,
        *,
        epsilon: float = 0.20,
        random_func: Callable[[], float] | None = None,
        choice_func: Callable[[list[int]], int] | None = None,
    ) -> None:
        self.epsilon = max(0.0, min(1.0, float(epsilon)))
        self.random_func = random_func or random.random
        self.choice_func = choice_func or random.choice

    def select_next_index(
        self,
        *,
        current_index: int,
        eligible_profiles: list[dict[str, Any]],
        bandit_rewards: dict[int, list[float]],
        bandit_counts: dict[int, int],
    ) -> dict[str, Any]:
        n_profiles = max(1, len(eligible_profiles))
        mean_rewards = _mean_rewards(n_profiles, bandit_rewards)
        if self.random_func() < self.epsilon:
            next_index = self._explore(n_profiles, current_index=current_index, bandit_counts=bandit_counts)
            mode = "explore"
        else:
            next_index = self._exploit(n_profiles, current_index=current_index, mean_rewards=mean_rewards)
            mode = "exploit" if bandit_rewards.get(next_index) else "cold-start"
        return {
            "schema_version": "strategy_switch_decision.v1",
            "current_index": current_index,
            "next_index": next_index,
            "mode": mode,
            "mean_rewards": mean_rewards,
        }

    def _explore(self, n_profiles: int, *, current_index: int, bandit_counts: dict[int, int]) -> int:
        max_count = max(bandit_counts.values()) if bandit_counts else 1
        weights = [1.0 / max(bandit_counts.get(index, 1) / max_count, 0.1) for index in range(n_profiles)]
        total_weight = sum(weights)
        threshold = self.random_func() * total_weight
        cumulative = 0.0
        next_index = current_index
        for index, weight in enumerate(weights):
            cumulative += weight
            if threshold <= cumulative:
                next_index = index
                break
        return next_index

    def _exploit(self, n_profiles: int, *, current_index: int, mean_rewards: dict[int, float]) -> int:
        if not mean_rewards:
            return current_index
        best_reward = max(mean_rewards.values())
        best_candidates = [index for index, reward in mean_rewards.items() if reward >= best_reward * 0.95]
        return self.choice_func(best_candidates) if best_candidates else current_index

    def build_application(
        self,
        *,
        current_index: int,
        next_index: int,
        eligible_profiles: list[dict[str, Any]],
    ) -> StrategySwitchApplication:
        n_profiles = max(1, len(eligible_profiles))
        old_profile = dict(eligible_profiles[current_index % n_profiles])
        next_profile = dict(eligible_profiles[next_index % n_profiles])
        return StrategySwitchApplication(
            old_index=current_index,
            next_index=next_index,
            old_profile=old_profile,
            next_profile=next_profile,
            retained=next_index == current_index,
            settings={
                "region": str(next_profile["region"]),
                "universe": str(next_profile["universe"]),
                "delay": int(next_profile["delay"]),
                "neutralization": str(next_profile["neutralization"]),
            },
        )

    def retained_candidate_ids(self, candidates: list[Any]) -> list[str]:
        ids: list[str] = []
        for candidate in candidates:
            if getattr(candidate, "simulation_id", "") or getattr(candidate, "official_metrics", None):
                continue
            alpha_id = str(getattr(candidate, "alpha_id", "") or "")
            if alpha_id:
                ids.append(alpha_id)
        return ids


def _mean_rewards(n_profiles: int, bandit_rewards: dict[int, list[float]]) -> dict[int, float]:
    means: dict[int, float] = {}
    for index in range(n_profiles):
        rewards = bandit_rewards.get(index, [])
        means[index] = sum(rewards) / max(len(rewards), 1) if rewards else 0.0
    return means

"""Lifecycle bookkeeping for adaptive strategy profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Callable, Protocol

from brain_alpha_ops.models import utc_now


STRATEGY_LIFECYCLE_SCHEMA = "strategy_lifecycle.v1"


@dataclass
class StrategyLifecycleTracker:
    record_sink: Callable[[dict[str, Any]], None] | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    rewards: dict[str, list[float]] = field(default_factory=dict)
    lineage: dict[str, str] = field(default_factory=dict)
    retired: set[str] = field(default_factory=set)

    def propose(self, profile: dict[str, Any], *, index: int, cycle: int, reason: str = "") -> dict[str, Any]:
        return self._record("propose", profile, index=index, cycle=cycle, reason=reason)

    def validate(
        self,
        profile: dict[str, Any],
        *,
        index: int,
        cycle: int,
        ready_rate: float,
        official_results: int,
        pool_size: int,
        trigger: str,
    ) -> dict[str, Any]:
        return self._record(
            "validate",
            profile,
            index=index,
            cycle=cycle,
            reason=trigger,
            metrics={
                "ready_rate": round(float(ready_rate or 0.0), 4),
                "official_results": int(official_results or 0),
                "pool_size": int(pool_size or 0),
            },
        )

    def mutate(
        self,
        parent_profile: dict[str, Any],
        child_profile: dict[str, Any],
        *,
        parent_index: int,
        child_index: int,
        cycle: int,
        reason: str,
    ) -> dict[str, Any]:
        parent_id = profile_id(parent_profile, parent_index)
        child_id = profile_id(child_profile, child_index)
        self.lineage[child_id] = parent_id
        return self._record(
            "mutate",
            child_profile,
            index=child_index,
            cycle=cycle,
            reason=reason,
            parent_profile_id=parent_id,
        )

    def retire(self, profile: dict[str, Any], *, index: int, cycle: int, reason: str) -> dict[str, Any]:
        pid = profile_id(profile, index)
        self.retired.add(pid)
        return self._record("retire", profile, index=index, cycle=cycle, reason=reason)

    def record_reward(
        self,
        profile: dict[str, Any],
        *,
        index: int,
        cycle: int,
        reward: float,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pid = profile_id(profile, index)
        value = float(reward or 0.0)
        self.rewards.setdefault(pid, []).append(value)
        payload = dict(metrics or {})
        payload["reward"] = round(value, 6)
        payload["reward_count"] = len(self.rewards[pid])
        payload["average_reward"] = round(sum(self.rewards[pid]) / len(self.rewards[pid]), 6)
        return self._record("reward", profile, index=index, cycle=cycle, metrics=payload)

    def summary(self, *, active_profile: dict[str, Any] | None = None, active_index: int = 0) -> dict[str, Any]:
        active_id = profile_id(active_profile or {}, active_index) if active_profile else ""
        reward_summary = {}
        for pid, values in self.rewards.items():
            reward_summary[pid] = {
                "count": len(values),
                "average_reward": round(sum(values) / max(len(values), 1), 6),
                "latest_reward": round(values[-1], 6) if values else 0.0,
            }
        return {
            "schema_version": STRATEGY_LIFECYCLE_SCHEMA,
            "active_profile_id": active_id,
            "reward_summary": reward_summary,
            "lineage": dict(self.lineage),
            "retired_profile_ids": sorted(self.retired),
            "records": list(self.records[-50:]),
        }

    def _record(
        self,
        action: str,
        profile: dict[str, Any],
        *,
        index: int,
        cycle: int,
        reason: str = "",
        metrics: dict[str, Any] | None = None,
        parent_profile_id: str = "",
    ) -> dict[str, Any]:
        pid = profile_id(profile, index)
        row = {
            "schema_version": STRATEGY_LIFECYCLE_SCHEMA,
            "timestamp": utc_now(),
            "action": action,
            "profile_id": pid,
            "profile_index": int(index or 0),
            "profile_name": str(profile.get("name") or "unknown"),
            "cycle": int(cycle or 0),
            "reason": str(reason or ""),
            "parent_profile_id": str(parent_profile_id or self.lineage.get(pid, "")),
            "metrics": dict(metrics or {}),
        }
        self.records.append(row)
        self.records = self.records[-500:]
        if self.record_sink:
            self.record_sink(dict(row))
        return row


class StrategyLifecyclePlugin(Protocol):
    """Optional strategy extension interface using the canonical lifecycle."""

    name: str

    def propose(self, context: dict[str, Any]) -> dict[str, Any]:
        ...

    def validate(self, profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...

    def mutate(self, profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...

    def retire(self, profile: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...


def profile_id(profile: dict[str, Any], index: int = 0) -> str:
    name = str(profile.get("name") or "unknown")
    region = str(profile.get("region") or "")
    universe = str(profile.get("universe") or "")
    neutralization = str(profile.get("neutralization") or "")
    seed = f"{index}|{name}|{region}|{universe}|{neutralization}"
    return "strategy_" + sha256(seed.encode("utf-8")).hexdigest()[:12]

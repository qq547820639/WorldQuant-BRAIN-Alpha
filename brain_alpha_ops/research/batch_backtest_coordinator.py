"""Batch coordination helpers for official backtest slots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from brain_alpha_ops.models import Candidate


BATCH_BACKTEST_PLAN_SCHEMA_VERSION = "batch_backtest_plan.v1"

CandidateRanker = Callable[[list[Candidate]], list[Candidate]]


@dataclass(frozen=True)
class BacktestBatchPlan:
    selected: tuple[Candidate, ...]
    skipped: tuple[dict[str, Any], ...]
    capacity: int
    requested: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BATCH_BACKTEST_PLAN_SCHEMA_VERSION,
            "selected_count": len(self.selected),
            "skipped_count": len(self.skipped),
            "capacity": self.capacity,
            "requested": self.requested,
            "selected": [
                {
                    "alpha_id": candidate.alpha_id,
                    "score": float(candidate.scorecard.get("total_score", 0.0) or 0.0),
                    "expression": candidate.expression,
                }
                for candidate in self.selected
            ],
            "skipped": list(self.skipped),
        }


class BatchBacktestCoordinator:
    """Select and explain a batch of candidates for official backtest slots."""

    def __init__(
        self,
        *,
        ranker: CandidateRanker,
        min_score: float,
        batch_size: int,
    ) -> None:
        self.ranker = ranker
        self.min_score = float(min_score)
        self.batch_size = max(0, int(batch_size or 0))

    def plan(self, candidates: list[Candidate], *, capacity: int | None = None) -> BacktestBatchPlan:
        capacity_value = self.batch_size if capacity is None else max(0, int(capacity or 0))
        requested = min(self.batch_size, capacity_value)
        skipped: list[dict[str, Any]] = []
        eligible: list[Candidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = candidate.expression.strip().lower()
            score = float(candidate.scorecard.get("total_score", 0.0) or 0.0)
            if key in seen:
                skipped.append(_skip(candidate, "duplicate_expression", score))
                continue
            seen.add(key)
            if score < self.min_score:
                skipped.append(_skip(candidate, "score_below_threshold", score))
                continue
            if candidate.simulation_id or candidate.official_metrics:
                skipped.append(_skip(candidate, "already_has_official_work", score))
                continue
            eligible.append(candidate)
        selected = tuple(self.ranker(eligible)[:requested])
        return BacktestBatchPlan(
            selected=selected,
            skipped=tuple(skipped),
            capacity=capacity_value,
            requested=requested,
        )


def _skip(candidate: Candidate, reason: str, score: float) -> dict[str, Any]:
    return {
        "alpha_id": candidate.alpha_id,
        "reason": reason,
        "score": round(score, 4),
        "expression": candidate.expression,
    }

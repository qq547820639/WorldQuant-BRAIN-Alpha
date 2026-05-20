"""Candidate-pool state rules for the research pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from brain_alpha_ops.models import Candidate

from .expression_ast import expression_key


CandidateRanker = Callable[[list[Candidate]], list[Candidate]]
CandidatePredicate = Callable[[Candidate], bool]


@dataclass
class CandidatePoolService:
    """Owns local candidate pool filtering, retention, and queue selection."""

    retained_alpha_pool_size: int
    min_prior_score_for_official_validation: float
    min_prior_score_for_official_simulation: float
    ranker: CandidateRanker
    smart_ranker: CandidateRanker

    def merge_into_pool(
        self,
        pool_by_expression: dict[str, Candidate],
        candidates: Iterable[Candidate],
        blocked_expressions: set[str],
    ) -> list[Candidate]:
        skipped: list[Candidate] = []
        for candidate in candidates:
            key = expr_key(candidate)
            if key in blocked_expressions:
                candidate.lifecycle_status = "previously_rejected_expression_skipped"
                candidate.gate = blocked_gate(
                    "PREVIOUSLY_REJECTED_EXPRESSION_SKIPPED",
                    ["same expression was already rejected by local or official standards in this run"],
                )
                skipped.append(candidate)
                continue
            existing = pool_by_expression.get(key)
            if not existing or ranking_score(candidate) > ranking_score(existing):
                candidate.lifecycle_status = "candidate_pool_retained"
                pool_by_expression[key] = candidate
            else:
                candidate.lifecycle_status = "duplicate_expression_skipped"
                candidate.gate = blocked_gate(
                    "DUPLICATE_EXPRESSION_SKIPPED",
                    ["candidate pool already has a higher-ranked identical expression"],
                )
                skipped.append(candidate)
        return skipped

    def remove_below_local_standard(self, pool_by_expression: dict[str, Candidate]) -> list[Candidate]:
        removed: list[Candidate] = []
        threshold = self.min_prior_score_for_official_validation
        for key, candidate in list(pool_by_expression.items()):
            if candidate.simulation_id and not candidate.official_metrics:
                continue
            score = candidate.scorecard.get("total_score", 0.0)
            if score < threshold:
                candidate.lifecycle_status = "local_standard_rejected"
                candidate.gate = blocked_gate(
                    "LOCAL_STANDARD_REJECTED",
                    [f"local score {score:.2f} below retained-pool threshold {threshold:.2f}"],
                )
                removed.append(candidate)
                del pool_by_expression[key]
        return removed

    def prune_pool(
        self,
        pool_by_expression: dict[str, Candidate],
        *,
        is_active_backtest_candidate: CandidatePredicate,
    ) -> list[Candidate]:
        retained_limit = max(1, int(self.retained_alpha_pool_size or 1))
        ranked = self.ranker(list(pool_by_expression.values()))
        active = [candidate for candidate in ranked if is_active_backtest_candidate(candidate)]
        pending = self.pending_backtest_candidates(ranked)
        pending_limit = max(50, retained_limit * 5)
        reserved_keys = {expr_key(candidate) for candidate in active + pending[:pending_limit]}
        available = [candidate for candidate in ranked if expr_key(candidate) not in reserved_keys]
        keep_keys = reserved_keys | {expr_key(candidate) for candidate in available[:retained_limit]}
        pruned = [candidate for candidate in ranked if expr_key(candidate) not in keep_keys]
        for candidate in pruned:
            candidate.lifecycle_status = "candidate_pool_pruned"
            candidate.gate = blocked_gate(
                "CANDIDATE_POOL_PRUNED",
                [f"outside retained top {retained_limit} local alpha pool"],
            )
            pool_by_expression.pop(expr_key(candidate), None)
        return pruned

    def validation_targets(self, pool: list[Candidate]) -> list[Candidate]:
        threshold = self.min_prior_score_for_official_validation
        return [
            candidate
            for candidate in pool
            if not candidate.validation
            and not candidate.official_metrics
            and candidate.scorecard.get("total_score", 0.0) >= threshold
        ]

    def backtest_targets(self, pool: list[Candidate], *, batch_size: int) -> list[Candidate]:
        ready = self.pending_backtest_candidates(pool, threshold=self.min_prior_score_for_official_simulation)
        return self.smart_ranker(ready)[:max(0, int(batch_size or 0))]

    def pending_backtest_candidates(self, pool: list[Candidate], threshold: float | None = None) -> list[Candidate]:
        ready = [candidate for candidate in pool if self.is_pending_backtest_candidate(candidate, threshold)]
        return self.smart_ranker(ready)

    def is_pending_backtest_candidate(self, candidate: Candidate, threshold: float | None = None) -> bool:
        threshold = self.min_prior_score_for_official_simulation if threshold is None else threshold
        status = f"{candidate.lifecycle_status} {candidate.gate.get('status', '')}".lower()
        has_precheck = (
            candidate.validation.get("status") == "PASS"
            or "backtest_batch_selected" in status
            or "backtest_slot_selected" in status
            or "simulation_deferred_concurrency_limit" in status
            or "simulation_deferred_rate_limit" in status
        )
        return (
            has_precheck
            and not candidate.simulation_id
            and not candidate.official_metrics
            and candidate.scorecard.get("total_score", 0.0) >= threshold
            and not is_hard_backtest_blocked(status)
        )

    def candidate_pool_candidates(
        self,
        pool: list[Candidate],
        *,
        is_active_backtest_candidate: CandidatePredicate,
    ) -> list[Candidate]:
        available: list[Candidate] = []
        for candidate in pool:
            status = f"{candidate.lifecycle_status} {candidate.gate.get('status', '')}".lower()
            if candidate.official_metrics or candidate.gate.get("submission_ready"):
                continue
            if is_active_backtest_candidate(candidate) or self.is_pending_backtest_candidate(candidate):
                continue
            if is_hard_backtest_blocked(status):
                continue
            available.append(candidate)
        return self.smart_ranker(available)


def expr_key(candidate: Candidate) -> str:
    return expression_key(candidate.expression)


def ranking_score(candidate: Candidate) -> float:
    return float(candidate.scorecard.get("total_score", 0.0) or 0.0)


def blocked_gate(status: str, reasons: list[str]) -> dict:
    return {
        "schema_version": "production-gate-v2.1",
        "submission_ready": False,
        "status": status,
        "failed_reasons": list(reasons),
        "warnings": [],
    }


def is_hard_backtest_blocked(status: str) -> bool:
    text = str(status or "").lower()
    if "simulation_deferred_concurrency_limit" in text or "simulation_deferred_rate_limit" in text:
        return False
    return any(
        marker in text
        for marker in (
            "official_validation_failed",
            "observability_duplicate_blocked",
            "local_standard_rejected",
            "official_standard_rejected",
            "simulation_request_failed",
            "simulation_poll_failed",
            "simulation_result_failed",
            "simulation_failed",
            "simulation_timeout",
            "rejected",
        )
    )

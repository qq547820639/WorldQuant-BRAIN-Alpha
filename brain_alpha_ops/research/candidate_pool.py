"""Candidate-pool state rules for the research pipeline.

Workstream C3 — Candidate pool production decoupled from official simulation
-----------------------------------------------------------------------------
The candidate pool is intentionally decoupled from the official 3-slot
simulation scheduler (``research.simulation_scheduler._scheduler.ThreeSlotScheduler``).
This module enforces the four decoupling invariants required by the spec:

C3.1 — Generator maintains pool capacity without being blocked by simulation.
    The main loop (``pipeline.pipeline_mixins``) runs generation BEFORE
    simulation each cycle, and ``_top_up_candidate_pool`` (in
    ``candidate_pool_service_``) refills the pool to ``retained_alpha_pool_size``
    independently of how many slots are in-flight. A full cooldown on all 3
    slots does NOT prevent the pool from accepting new candidates.

C3.2 — Local scoring + gate eliminates/ranks first.
    ``merge_into_pool`` applies the ranker and deduplicates by expression;
    ``remove_below_local_standard`` drops candidates below
    ``min_prior_score_for_official_validation`` (default 60.0);
    ``candidate_official_work_blockers`` rejects candidates that fail local
    quality / local backtest / official-context checks. Only locally-vetted
    candidates survive into the pool that official simulation reads from.

C3.3 — Official simulation consumes only TopK.
    ``backtest_targets`` filters by ``min_prior_score_for_official_simulation``
    (default 70.0 — stricter than the validation threshold), applies
    ``smart_ranker``, then slices to ``batch_size`` (capped at 3 by
    ``OFFICIAL_SIMULATION_SLOT_LIMIT``). The scheduler's ``_pick_next_candidate``
    additionally skips any candidate already in SUBMITTED/RUNNING/PENDING/QUEUED
    state, so the same expression is never double-submitted.

C3.4 — Official result writeback is non-blocking.
    The scheduler's ``tick()`` returns ``SlotOutcome`` objects immediately;
    the pipeline processes them via ``result_handler`` callbacks without
    stalling the next generation cycle. ``_handle_completed`` resets the slot
    to IDLE synchronously, so the slot is available for the next candidate
    in the same tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from brain_alpha_ops.candidate_lifecycle import (
    LifecycleState,
    _LEGACY_STATUS_MAP,
    transition,
)
from brain_alpha_ops.models import Candidate

from .fallback_generation import high_turnover_generation_risk_reasons
from .pipeline_helpers import (
    blocked_gate,
    expr_key,
    is_hard_backtest_blocked,
    ranking_score,
)

CandidateRanker = Callable[[list[Candidate]], list[Candidate]]
CandidatePredicate = Callable[[Candidate], bool]

# Inactive canonical lifecycle states for backtest purposes (Workstream B2.5).
_INACTIVE_ENUM_STATES = frozenset({
    LifecycleState.simulation_failed,
    LifecycleState.archived,
    LifecycleState.gate_rejected,
})

# Legacy strings that are inactive for backtest purposes even though their
# canonical enum state is not in ``_INACTIVE_ENUM_STATES`` (e.g.
# ``submission_ready`` → ``ready_for_review`` — no longer a simulation target).
_INACTIVE_LEGACY_EXTRAS = frozenset({"submission_ready"})

# Derived from the enum + legacy extras so all historical string statuses
# continue to be recognised as inactive.
INACTIVE_BACKTEST_STATUSES = {
    legacy for legacy, state in _LEGACY_STATUS_MAP.items()
    if state in _INACTIVE_ENUM_STATES
} | _INACTIVE_LEGACY_EXTRAS


def _is_inactive(status: "str | LifecycleState") -> bool:
    """Check if a lifecycle status (enum or legacy string) is inactive."""
    if isinstance(status, LifecycleState):
        return status in _INACTIVE_ENUM_STATES
    if status in INACTIVE_BACKTEST_STATUSES:
        return True
    state = _LEGACY_STATUS_MAP.get(status)
    return state in _INACTIVE_ENUM_STATES if state is not None else False


def is_active_backtest_candidate(candidate: Candidate) -> bool:
    if not candidate.simulation_id or candidate.official_metrics:
        return False
    return not _is_inactive(candidate.lifecycle_status)


def pending_simulation_targets(pool: list[Candidate]) -> list[Candidate]:
    return [
        candidate
        for candidate in pool
        if is_active_backtest_candidate(candidate)
    ]


def candidate_official_work_blockers(candidate: Candidate) -> list[str]:
    """Return local reasons that block any official validation or simulation work."""

    blockers: list[str] = []
    for reason in high_turnover_generation_risk_reasons(candidate.expression):
        blockers.append(f"high_turnover_generation_risk:{reason}")

    local_quality = candidate.local_quality if isinstance(candidate.local_quality, dict) else {}
    if local_quality.get("passed") is False:
        blockers.append("local_quality_failed")

    for container in (local_quality, candidate.submission, candidate.extra_fields):
        if not isinstance(container, dict):
            continue
        local_backtest = container.get("local_backtest")
        if isinstance(local_backtest, dict) and local_backtest.get("pass_local") is False:
            blockers.append("local_backtest_failed")

    gate = candidate.gate if isinstance(candidate.gate, dict) else {}
    status = f"{candidate.lifecycle_status} {gate.get('status', '')}"
    if str(gate.get("status") or "").upper() == "OFFICIAL_CONTEXT_WARNING":
        warnings = gate.get("warnings")
        for warning in warnings if isinstance(warnings, list) else []:
            if str(warning).strip():
                blockers.append(f"official_context_warning:{warning}")
        if not blockers:
            blockers.append("official_context_warning")
    if is_hard_backtest_blocked(status):
        blockers.append("hard_backtest_blocked_status")

    return sorted(set(blockers))


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
                transition(
                    candidate, LifecycleState.gate_rejected,
                    reason="previously_rejected_expression",
                    legacy_status="previously_rejected_expression_skipped",
                )
                candidate.gate = blocked_gate(
                    "PREVIOUSLY_REJECTED_EXPRESSION_SKIPPED",
                    ["same expression was already rejected by local or official standards in this run"],
                )
                skipped.append(candidate)
                continue
            existing = pool_by_expression.get(key)
            if not existing or ranking_score(candidate) > ranking_score(existing):
                transition(
                    candidate, LifecycleState.locally_scored,
                    reason="candidate_pool_retained",
                    legacy_status="candidate_pool_retained",
                )
                pool_by_expression[key] = candidate
            else:
                transition(
                    candidate, LifecycleState.gate_rejected,
                    reason="duplicate_expression_skipped",
                    legacy_status="duplicate_expression_skipped",
                )
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
                transition(
                    candidate, LifecycleState.gate_rejected,
                    reason=f"local_standard_below_threshold:{score:.2f}<{threshold:.2f}",
                    legacy_status="local_standard_rejected",
                )
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
            transition(
                candidate, LifecycleState.archived,
                reason=f"candidate_pool_pruned:outside_top_{retained_limit}",
                legacy_status="candidate_pool_pruned",
            )
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
            and not candidate_official_work_blockers(candidate)
        ]

    def backtest_targets(self, pool: list[Candidate], *, batch_size: int) -> list[Candidate]:
        """C3.3: official simulation consumes only TopK — filter by the
        stricter simulation threshold, smart-rank, then slice to batch_size.
        """
        ready = self.pending_backtest_candidates(pool, threshold=self.min_prior_score_for_official_simulation)
        return self.smart_ranker(ready)[:max(0, int(batch_size or 0))]

    def pending_backtest_candidates(self, pool: list[Candidate], threshold: float | None = None) -> list[Candidate]:
        ready = [candidate for candidate in pool if self.is_pending_backtest_candidate(candidate, threshold)]
        return self.smart_ranker(ready)

    def is_pending_backtest_candidate(self, candidate: Candidate, threshold: float | None = None) -> bool:
        threshold = self.min_prior_score_for_official_simulation if threshold is None else threshold
        gate = candidate.gate if isinstance(candidate.gate, dict) else {}
        status = f"{candidate.lifecycle_status} {gate.get('status', '')}".lower()
        validation = candidate.validation if isinstance(candidate.validation, dict) else {}
        has_precheck = (
            validation.get("status") == "PASS"
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
            and not candidate_official_work_blockers(candidate)
        )

    def candidate_pool_candidates(
        self,
        pool: list[Candidate],
        *,
        is_active_backtest_candidate: CandidatePredicate,
    ) -> list[Candidate]:
        available: list[Candidate] = []
        for candidate in pool:
            gate = candidate.gate if isinstance(candidate.gate, dict) else {}
            status = f"{candidate.lifecycle_status} {gate.get('status', '')}".lower()
            if candidate.official_metrics or gate.get("submission_ready"):
                continue
            if is_active_backtest_candidate(candidate) or self.is_pending_backtest_candidate(candidate):
                continue
            if is_hard_backtest_blocked(status):
                continue
            if candidate_official_work_blockers(candidate):
                continue
            available.append(candidate)
        return self.smart_ranker(available)

"""Snapshot builders for pipeline runtime and result payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable

from brain_alpha_ops.models import Candidate

from .pipeline_helpers import compute_gate_summary, compute_score_distribution, slot_message, slot_progress_percent
from .pipeline_state import bandit_runtime_summary


@dataclass(frozen=True)
class PipelineSnapshotServices:
    """Callbacks supplied by the pipeline coordinator for snapshot assembly."""

    candidate_pool_candidates: Callable[[list[Candidate]], list[Candidate]]
    pending_backtest_candidates: Callable[[list[Candidate]], list[Candidate]]
    validation_targets: Callable[[list[Candidate]], list[Candidate]]
    active_backtest_limit: Callable[[], int]
    poll_interval_seconds: Callable[[], float]
    slot_snapshot: Callable[[], list[dict]]
    current_strategy_profile: Callable[[], dict]
    strategy_lifecycle_summary: Callable[[dict, int], dict]
    strategy_plugin_summary: Callable[[], dict]
    observability_official_call_guard_snapshot: Callable[[], dict]
    assess_auto_submission: Callable[[Candidate, int], dict]
    smart_rank_candidates: Callable[[list[Candidate]], list[Candidate]]
    smart_ranking_score: Callable[[Candidate], float]
    cloud_correlation_risk: Callable[[Candidate], dict]


@dataclass(frozen=True)
class PipelineSnapshotState:
    """Mutable pipeline counters and records copied for snapshot rendering."""

    produced_count: int = 0
    officially_simulated_count: int = 0
    official_validation_attempted_count: int = 0
    official_validation_passed_count: int = 0
    backtests_submitted: int = 0
    recovered_backtest_slot_count: int = 0
    official_calls_halted: bool = False
    official_halt_reason: str = ""
    official_retry_remaining_seconds: float = 0.0
    observability_throttle: dict = field(default_factory=dict)
    observability_generation_guidance: dict = field(default_factory=dict)
    context_summary: dict = field(default_factory=dict)
    cloud_sync: dict = field(default_factory=dict)
    cloud_alphas: list[dict] = field(default_factory=list)
    lifecycle_records: list[dict] = field(default_factory=list)
    backtest_records: list[dict] = field(default_factory=list)
    convergence: dict = field(default_factory=dict)
    user_profile: dict = field(default_factory=dict)
    bandit_rewards: dict[int, list[float]] = field(default_factory=dict)
    bandit_counts: dict[int, int] = field(default_factory=dict)
    strategy_switch_count: int = 0
    strategy_profile_index: int = 0
    active_dataset_id: str = ""
    auto_calibrator_status: Any = "ready"
    scoring_calibrated: bool = False


class PipelineSnapshotBuilder:
    """Build Web/CLI-facing snapshots without owning pipeline orchestration."""

    def __init__(self, *, config: Any, services: PipelineSnapshotServices) -> None:
        self.config = config
        self.services = services

    def runtime_data(
        self,
        cycle: int,
        pool: list[Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        state: PipelineSnapshotState,
        extra: dict | None = None,
    ) -> dict:
        candidate_pool = self.services.candidate_pool_candidates(pool)
        pending_backtests = self.services.pending_backtest_candidates(pool)
        pending_validation = len(self.services.validation_targets(pool))
        active_backtest_limit = self.services.active_backtest_limit()
        current_profile = self.services.current_strategy_profile()
        data = {
            "cycle": cycle,
            "candidates": self.candidate_snapshot(candidate_pool),
            "candidate_pool_available_count": len(candidate_pool),
            "candidate_pool_source_count": len(pool),
            "candidate_pool_excludes_waiting_backtests": True,
            "pending_backtest_candidates": self.candidate_snapshot(pending_backtests, limit=50, retained=False),
            "pending_backtest_count": len(pending_backtests),
            "passed_candidates": self.candidate_snapshot(accepted_candidates, limit=50, retained=False),
            "produced_count": state.produced_count,
            "ready_results_count": len(accepted_candidates),
            "official_validation_attempted": state.official_validation_attempted_count,
            "official_validation_passed": state.official_validation_passed_count,
            "pending_validation_count": pending_validation,
            "simulation_retry_pending": sum(1 for candidate in pool if candidate.lifecycle_status == "simulation_retry_pending"),
            "secondary_fusion_candidates": sum(1 for candidate in pool if candidate.mutation_type == "secondary_fusion"),
            "rejected_count": sum(archive_stats.values()),
            "rejected_stats": archive_stats,
            "archive_count": sum(archive_stats.values()),
            "archive_stats": archive_stats,
            "backtest_slot_limit": active_backtest_limit,
            "recovered_backtest_slot_count": state.recovered_backtest_slot_count,
            "backtests": self.services.slot_snapshot(),
            "official_call_policy": self._official_call_policy(active_backtest_limit),
            "strategy_profile": current_profile,
            "strategy_switch_count": state.strategy_switch_count,
            "official_calls_halted": state.official_calls_halted,
            "official_halt_reason": state.official_halt_reason,
            "official_retry_remaining_seconds": state.official_retry_remaining_seconds,
            "observability_throttle": dict(state.observability_throttle),
            "observability_generation_guidance": dict(state.observability_generation_guidance),
            "observability_official_call_guard": self.services.observability_official_call_guard_snapshot(),
            "cloud_sync": state.cloud_sync,
            "cloud_alphas": state.cloud_alphas,
            "lifecycle_records": state.lifecycle_records,
            "backtest_records": state.backtest_records[-50:],
            "convergence": state.convergence,
            "user_profile": state.user_profile,
            "bandit": bandit_runtime_summary(
                current_profile,
                state.bandit_rewards,
                state.bandit_counts,
                total_switches=state.strategy_switch_count,
            ),
            "strategy_lifecycle": self.services.strategy_lifecycle_summary(current_profile, state.strategy_profile_index),
            "strategy_plugins": self.services.strategy_plugin_summary(),
            "active_dataset_id": state.active_dataset_id,
            "auto_calibrator_status": state.auto_calibrator_status,
            "scoring_calibrated": state.scoring_calibrated,
        }
        data.update(extra or {})
        return data

    def summary(
        self,
        candidates: list[Candidate],
        submitted_this_run: int,
        pool_by_expression: dict[str, Candidate],
        archive_stats: dict[str, int],
        state: PipelineSnapshotState,
    ) -> dict:
        ready = [candidate for candidate in candidates if candidate.gate.get("submission_ready")]
        pool_values = list(pool_by_expression.values())
        candidate_pool = self.services.candidate_pool_candidates(pool_values)
        pending_backtests = self.services.pending_backtest_candidates(pool_values)
        auto_allowed = [
            candidate
            for candidate in ready
            if not self.services.assess_auto_submission(candidate, 0)["failed_reasons"]
        ]
        active_backtest_limit = self.services.active_backtest_limit()
        current_profile = self.services.current_strategy_profile()
        return {
            "total_candidates": state.produced_count,
            "produced_count": state.produced_count,
            "retained_pool_size": len(candidate_pool),
            "candidate_pool_available_count": len(candidate_pool),
            "candidate_pool_source_count": len(pool_values),
            "candidate_pool_excludes_waiting_backtests": True,
            "retained_pool_limit": self.config.budget.retained_alpha_pool_size,
            "rejected_count": sum(archive_stats.values()),
            "rejected_stats": dict(archive_stats),
            "archive_count": sum(archive_stats.values()),
            "archive_stats": dict(archive_stats),
            "backtest_batch_size": self.config.budget.official_backtest_batch_size,
            "backtest_slot_limit": active_backtest_limit,
            "backtests_submitted": state.backtests_submitted,
            "recovered_backtest_slot_count": state.recovered_backtest_slot_count,
            "local_ranked": sum(1 for candidate in candidates if candidate.scorecard.get("score_basis") == "local_prior"),
            "official_validation_attempted": state.official_validation_attempted_count,
            "official_validation_passed": state.official_validation_passed_count,
            "pending_validation_count": len(self.services.validation_targets(pool_values)),
            "officially_simulated": state.officially_simulated_count,
            "official_deferred": sum(1 for candidate in candidates if str(candidate.lifecycle_status).startswith("simulation_deferred")),
            "simulation_retry_pending": sum(1 for candidate in pool_values if candidate.lifecycle_status == "simulation_retry_pending"),
            "secondary_fusion_candidates": sum(1 for candidate in pool_values if candidate.mutation_type == "secondary_fusion"),
            "pending_backtest_count": len(pending_backtests),
            "submission_ready": len(ready),
            "ready_results_count": len(ready),
            "auto_submit_ready": len(auto_allowed),
            "submitted_this_run": submitted_this_run,
            "best_score": max((candidate.scorecard.get("total_score", 0.0) for candidate in candidates), default=0.0),
            "operating_mode": "local_autonomous_loop_top10_top3",
            "run_forever": self.config.budget.run_forever,
            "official_calls_halted": state.official_calls_halted,
            "official_halt_reason": state.official_halt_reason,
            "observability_throttle": dict(state.observability_throttle),
            "observability_generation_guidance": dict(state.observability_generation_guidance),
            "observability_official_call_guard": self.services.observability_official_call_guard_snapshot(),
            "official_context": dict(state.context_summary),
            "backtest_slots": self.services.slot_snapshot(),
            "strategy_profile": current_profile,
            "strategy_switch_count": state.strategy_switch_count,
            "strategy_lifecycle": self.services.strategy_lifecycle_summary(current_profile, state.strategy_profile_index),
            "strategy_plugins": self.services.strategy_plugin_summary(),
            "cloud_sync": dict(state.cloud_sync),
            "cloud_alphas": list(state.cloud_alphas),
            "lifecycle_records": list(state.lifecycle_records),
            "backtest_records": list(state.backtest_records[-50:]),
            "convergence": state.convergence,
            "candidates": self.candidate_snapshot(candidate_pool),
            "passed_candidates": self.candidate_snapshot(ready, limit=50, retained=False),
            "pending_backtest_candidates": self.candidate_snapshot(pending_backtests, limit=50, retained=False),
            "official_call_policy": self._official_call_policy(active_backtest_limit),
            "can_complete_goal": {
                "local_production_evaluation_ranking_loop": True,
                "retains_top_10_before_backtest": True,
                "submits_top_3_backtests_per_cycle": True,
                "waits_for_backtest_results": True,
                "screen_progress_updates": True,
                "caveat": "Official rate limits can still defer a batch; deferred candidates are not treated as alpha-quality failures.",
            },
            "user_profile": state.user_profile,
            "score_distribution": compute_score_distribution(candidates),
            "gate_summary": compute_gate_summary(candidates),
            "auto_submitted": submitted_this_run,
        }

    def candidate_snapshot(self, pool: list[Candidate], *, limit: int | None = None, retained: bool = True) -> list[dict]:
        limit = self.config.budget.retained_alpha_pool_size if limit is None else max(0, int(limit))
        return [
            {
                **candidate.to_dict(),
                "pool_rank": index,
                "in_retained_pool": retained,
                "smart_rank_score": self.services.smart_ranking_score(candidate),
                "cloud_correlation_risk": self.services.cloud_correlation_risk(candidate),
            }
            for index, candidate in enumerate(self.services.smart_rank_candidates(pool)[:limit], start=1)
        ]

    def backtest_snapshot(self, candidates: list[Candidate]) -> list[dict]:
        return [
            {
                "alpha_id": candidate.alpha_id,
                "simulation_id": candidate.simulation_id,
                "status": candidate.submission.get("simulation_status") or candidate.lifecycle_status,
                "official_alpha_id": candidate.official_alpha_id,
                "score": candidate.scorecard.get("total_score", 0.0),
            }
            for candidate in candidates
        ]

    def _official_call_policy(self, active_backtest_limit: int) -> dict:
        budget = self.config.budget
        return {
            "local_first": True,
            "retained_alpha_pool_size": budget.retained_alpha_pool_size,
            "official_backtest_batch_size": budget.official_backtest_batch_size,
            "max_official_validations_per_cycle": budget.max_official_validations_per_cycle,
            "max_official_simulations_per_cycle": budget.max_official_simulations_per_cycle,
            "max_official_concurrent_simulations": budget.max_official_concurrent_simulations,
            "active_backtest_slot_limit": active_backtest_limit,
            "max_simulation_retries": budget.max_simulation_retries,
            "enable_secondary_fusion": budget.enable_secondary_fusion,
            "resume_persisted_backtests": getattr(budget, "resume_persisted_backtests", True),
            "poll_interval_seconds": self.services.poll_interval_seconds(),
            "poll_attempt_limit": None,
            "min_prior_score_for_official_validation": budget.min_prior_score_for_official_validation,
            "min_prior_score_for_official_simulation": budget.min_prior_score_for_official_simulation,
        }


def backtest_slot_snapshot(
    *,
    active_limit: int,
    candidate_at_slot: Callable[[int], Candidate | None],
    official_calls_halted: bool,
    official_halt_reason: str,
    cloud_correlation_risk: Callable[[Candidate], dict],
    now: float | None = None,
) -> list[dict]:
    """Render current backtest slots for progress and Web payloads."""

    current_time = time.monotonic() if now is None else float(now)
    rows = []
    for slot in range(1, active_limit + 1):
        candidate = candidate_at_slot(slot)
        if not candidate:
            status = "CAPACITY_WAIT" if official_calls_halted else "EMPTY"
            rows.append(
                {
                    "slot": slot,
                    "alpha_id": "",
                    "simulation_id": "",
                    "status": status,
                    "official_alpha_id": "",
                    "score": 0.0,
                    "poll_count": 0,
                    "progress_percent": 0,
                    "next_poll_seconds": 0,
                    "message": (
                        f"Official calls paused: {official_halt_reason}"
                        if official_calls_halted
                        else "Waiting for candidate backfill."
                    ),
                }
            )
            continue
        status = candidate.submission.get("simulation_status") or candidate.lifecycle_status
        next_poll_at = float(candidate.submission.get("next_poll_at", 0.0) or 0.0)
        rows.append(
            {
                "slot": slot,
                "alpha_id": candidate.alpha_id,
                "simulation_id": candidate.simulation_id,
                "status": status,
                "lifecycle_status": candidate.lifecycle_status,
                "official_alpha_id": candidate.official_alpha_id,
                "score": candidate.scorecard.get("total_score", 0.0),
                "family": candidate.family,
                "hypothesis": candidate.hypothesis,
                "expression": candidate.expression,
                "scorecard": candidate.scorecard,
                "local_quality": candidate.local_quality,
                "validation": candidate.validation,
                "official_metrics": candidate.official_metrics,
                "gate": candidate.gate,
                "cloud_correlation_risk": cloud_correlation_risk(candidate),
                "poll_count": candidate.submission.get("poll_count", 0),
                "progress_percent": slot_progress_percent(status),
                "next_poll_seconds": round(max(0.0, next_poll_at - current_time), 1),
                "message": slot_message(status),
            }
        )
    return rows

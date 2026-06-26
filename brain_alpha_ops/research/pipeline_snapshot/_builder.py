"""Pipeline snapshot builder for Web/CLI-facing runtime and summary payloads."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.models import Candidate

from ..alpha_quality import (
    build_alpha_output_config,
    diagnose_alpha_candidate,
    summarize_quality_diagnostics,
)
from ..pipeline_helpers import (
    compute_gate_summary,
    compute_score_distribution,
)
from ..pipeline_state import bandit_runtime_summary
from ._state import PipelineSnapshotServices, PipelineSnapshotState


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
        candidate_rows = self.candidate_snapshot(candidate_pool)
        pending_rows = self.candidate_snapshot(pending_backtests, limit=50, retained=False)
        passed_rows = self.candidate_snapshot(accepted_candidates, limit=50, retained=False)
        data = {
            "cycle": cycle,
            "candidates": candidate_rows,
            "candidate_pool_available_count": len(candidate_pool),
            "candidate_pool_source_count": len(pool),
            "candidate_pool_excludes_waiting_backtests": True,
            "pending_backtest_candidates": pending_rows,
            "pending_backtest_count": len(pending_backtests),
            "passed_candidates": passed_rows,
            "produced_count": state.produced_count,
            "alpha_output_config": self._alpha_output_config(
                dataset_id=state.active_dataset_id,
                official_api_called=(
                    state.official_validation_attempted_count > 0
                    or state.backtests_submitted > 0
                    or state.officially_simulated_count > 0
                ),
            ),
            "quality_summary": self._quality_summary(
                list(candidate_pool) + list(pending_backtests) + list(accepted_candidates)
            ),
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
        backtest_slots = self.services.slot_snapshot()
        current_profile = self.services.current_strategy_profile()
        candidate_rows = self.candidate_snapshot(candidate_pool)
        ready_rows = self.candidate_snapshot(ready, limit=50, retained=False)
        pending_rows = self.candidate_snapshot(pending_backtests, limit=50, retained=False)
        official_api_called = (
            state.official_validation_attempted_count > 0
            or state.backtests_submitted > 0
            or state.officially_simulated_count > 0
        )
        return {
            "total_candidates": state.produced_count,
            "produced_count": state.produced_count,
            "alpha_output_config": self._alpha_output_config(
                dataset_id=state.active_dataset_id,
                official_api_called=official_api_called,
            ),
            "quality_summary": self._quality_summary(candidates),
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
            "backtest_slots": backtest_slots,
            "strategy_profile": current_profile,
            "strategy_switch_count": state.strategy_switch_count,
            "strategy_lifecycle": self.services.strategy_lifecycle_summary(current_profile, state.strategy_profile_index),
            "strategy_plugins": self.services.strategy_plugin_summary(),
            "cloud_sync": dict(state.cloud_sync),
            "cloud_alphas": list(state.cloud_alphas),
            "lifecycle_records": list(state.lifecycle_records),
            "backtest_records": list(state.backtest_records[-50:]),
            "convergence": state.convergence,
            "candidates": candidate_rows,
            "passed_candidates": ready_rows,
            "pending_backtest_candidates": pending_rows,
            "official_call_policy": self._official_call_policy(active_backtest_limit),
            "can_complete_goal": {
                "local_production_evaluation_ranking_loop": True,
                "retains_top_10_before_backtest": True,
                "submits_configured_backtests_per_cycle": True,
                "submits_top_3_backtests_per_cycle": active_backtest_limit >= 3,
                "official_backtest_capacity": active_backtest_limit,
                "visible_three_independent_backtest_slots": len(backtest_slots) >= 3,
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
                **self.prepare_candidate_for_snapshot(candidate),
                "pool_rank": index,
                "in_retained_pool": retained,
                "smart_rank_score": self.services.smart_ranking_score(candidate),
                "cloud_correlation_risk": self.services.cloud_correlation_risk(candidate),
            }
            for index, candidate in enumerate(self.services.smart_rank_candidates(pool)[:limit], start=1)
        ]

    def prepare_candidate_for_snapshot(self, candidate: Candidate) -> dict:
        if self._supports_alpha_quality():
            output_config = self._candidate_alpha_output_config(candidate)
            candidate.alpha_output_config = output_config
            candidate.quality_diagnosis = diagnose_alpha_candidate(
                candidate,
                run_config=self.config,
                output_config=output_config,
            )
        return candidate.to_dict()

    def backtest_snapshot(self, candidates: list[Candidate]) -> list[dict]:
        return [
            {
                "alpha_id": candidate.alpha_id,
                "simulation_id": candidate.simulation_id,
                "status": candidate.submission.get("simulation_status") or candidate.lifecycle_status,
                "official_alpha_id": candidate.official_alpha_id,
                "score": candidate.scorecard.get("total_score", 0.0),
                "alpha_output_config": candidate.alpha_output_config,
                "quality_diagnosis": candidate.quality_diagnosis,
            }
            for candidate in candidates
        ]

    def _supports_alpha_quality(self) -> bool:
        return all(
            hasattr(self.config, name)
            for name in ("settings", "budget", "thresholds", "scoring", "submission_policy")
        )

    def _candidate_alpha_output_config(self, candidate: Candidate) -> dict:
        return self._alpha_output_config(
            dataset_id=candidate.dataset_id or getattr(self.config.settings, "dataset", ""),
            official_api_called=bool(
                candidate.validation
                or candidate.simulation_id
                or candidate.official_alpha_id
                or candidate.official_metrics
            ),
        )

    def _alpha_output_config(self, *, dataset_id: str = "", official_api_called: bool = False) -> dict:
        if not self._supports_alpha_quality():
            return {}
        return build_alpha_output_config(
            self.config,
            dataset_id=dataset_id,
            generation_args={
                "mode": "production_pipeline",
                "local_only": False,
                "official_api_called": official_api_called,
                "allow_submit": False,
            },
        )

    def _quality_summary(self, candidates: list[Candidate]) -> dict:
        if not self._supports_alpha_quality():
            return {}
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = (
                candidate.official_alpha_id
                or candidate.simulation_id
                or candidate.alpha_id
                or candidate.expression
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(self.prepare_candidate_for_snapshot(candidate))
        return summarize_quality_diagnostics(rows)

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

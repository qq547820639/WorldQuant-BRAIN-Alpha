"""Runtime snapshot helpers for AlphaResearchPipeline."""

from __future__ import annotations

from brain_alpha_ops.models import Candidate

from .pipeline_snapshot import (
    PipelineSnapshotBuilder,
    PipelineSnapshotServices,
    PipelineSnapshotState,
    backtest_slot_snapshot,
)


class PipelineSnapshotMixin:
    def _runtime_data(
        self,
        cycle: int,
        pool: list[Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        extra: dict | None = None,
    ) -> dict:
        return self._snapshot_builder().runtime_data(
            cycle,
            pool,
            accepted_candidates,
            archive_stats,
            self._snapshot_state(),
            extra=extra,
        )

    def _snapshot_builder(self) -> PipelineSnapshotBuilder:
        return PipelineSnapshotBuilder(
            config=self.config,
            services=PipelineSnapshotServices(
                candidate_pool_candidates=self._candidate_pool_candidates,
                pending_backtest_candidates=self._pending_backtest_candidates,
                validation_targets=self._validation_targets,
                active_backtest_limit=self._active_backtest_limit,
                poll_interval_seconds=self._poll_interval_seconds,
                slot_snapshot=self._slot_snapshot,
                current_strategy_profile=self._current_strategy_profile,
                strategy_lifecycle_summary=lambda profile, index: self.strategy_lifecycle.summary(
                    active_profile=profile,
                    active_index=index,
                ),
                strategy_plugin_summary=self._strategy_plugin_summary,
                observability_official_call_guard_snapshot=self._observability_official_call_guard_snapshot,
                assess_auto_submission=self._assess_auto_submission,
                smart_rank_candidates=self._smart_rank_candidates,
                smart_ranking_score=self._smart_ranking_score,
                cloud_correlation_risk=self._cloud_correlation_risk,
            ),
        )

    def _snapshot_state(self) -> PipelineSnapshotState:
        return PipelineSnapshotState(
            produced_count=self.produced_count,
            officially_simulated_count=self.officially_simulated_count,
            official_validation_attempted_count=self.official_validation_attempted_count,
            official_validation_passed_count=self.official_validation_passed_count,
            backtests_submitted=self.backtests_submitted,
            recovered_backtest_slot_count=self.recovered_backtest_slot_count,
            official_calls_halted=self.official_calls_halted,
            official_halt_reason=self.official_halt_reason,
            official_retry_remaining_seconds=self._official_retry_remaining_seconds(),
            observability_throttle=dict(self.observability_throttle),
            observability_generation_guidance=dict(self.observability_generation_guidance),
            context_summary=dict(self.context_summary),
            cloud_sync=self.cloud_sync,
            cloud_alphas=self.cloud_alphas,
            lifecycle_records=self.lifecycle_records,
            backtest_records=self.backtest_records,
            convergence=self.convergence.summary(),
            user_profile=self.user_profile,
            bandit_rewards=self._bandit_rewards,
            bandit_counts=self._bandit_counts,
            strategy_switch_count=self.strategy_switch_count,
            strategy_profile_index=self.strategy_profile_index,
            active_dataset_id=self._active_dataset_id,
            auto_calibrator_status=(
                self.auto_calibrator.calibrate.__doc__[:1] if hasattr(self.auto_calibrator, "calibrate") else "ready"
            ),
            scoring_calibrated=bool(getattr(self.config.scoring, "prior_weights_override", None)),
        )

    def _summary(
        self,
        candidates: list[Candidate],
        submitted_this_run: int,
        pool_by_expression: dict[str, Candidate],
        archive_stats: dict[str, int],
    ) -> dict:
        return self._snapshot_builder().summary(
            candidates,
            submitted_this_run,
            pool_by_expression,
            archive_stats,
            self._snapshot_state(),
        )

    def _candidate_snapshot(self, pool: list[Candidate], *, limit: int | None = None, retained: bool = True) -> list[dict]:
        return self._snapshot_builder().candidate_snapshot(pool, limit=limit, retained=retained)

    def _slot_snapshot(self) -> list[dict]:
        return backtest_slot_snapshot(
            active_limit=self._active_backtest_limit(),
            candidate_at_slot=self.backtest_slot_manager.get,
            official_calls_halted=self.official_calls_halted,
            official_halt_reason=self.official_halt_reason,
            cloud_correlation_risk=self._cloud_correlation_risk,
        )

    def _active_backtest_limit(self) -> int:
        return min(
            max(1, int(self.config.budget.official_backtest_batch_size)),
            max(1, int(self.config.budget.max_official_simulations_per_cycle)),
            max(1, int(self.config.budget.max_official_concurrent_simulations)),
        )

    def _backtest_snapshot(self, candidates: list[Candidate]) -> list[dict]:
        return self._snapshot_builder().backtest_snapshot(candidates)

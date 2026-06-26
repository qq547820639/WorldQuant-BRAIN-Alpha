"""Candidate pool top-up and management mixin for ``PipelineCandidatePoolMixin``.

Extracted from the original ``pipeline_candidates.py`` monolith. Holds the
``_CandidatePoolManagementMixin`` carrying pool top-up, merge/prune,
validation target/quota planning, backtest slot selection, and pending
candidate bookkeeping methods.
"""

from __future__ import annotations

from brain_alpha_ops.models import Candidate

from ..candidate_pool import is_active_backtest_candidate, pending_simulation_targets
from ..pipeline_helpers import rank_candidates


class _CandidatePoolManagementMixin:
    """Candidate pool top-up, prune, and validation/backtest planning methods."""

    def _top_up_candidate_pool(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        fields: list[dict],
        operators: list[dict],
        accepted_candidates: list[Candidate],
    ):
        retained_limit = max(1, self.config.budget.retained_alpha_pool_size)
        attempts = 0
        while (
            len(self._candidate_pool_candidates(list(pool_by_expression.values()))) < retained_limit
            and attempts < 2
            and not self._should_stop()
        ):
            available = len(self._candidate_pool_candidates(list(pool_by_expression.values())))
            deficit = retained_limit - available
            batch_size = min(
                max(int(deficit * 2), retained_limit),
                max(1, int(self.config.budget.max_candidates_per_cycle)),
            )
            generated = self.generator.generate(batch_size, dataset_id=self._active_dataset_id)
            attempts += 1
            if not generated:
                break
            self._attach_active_assistant_guidance(generated)
            self.produced_count += len(generated)
            for candidate in generated:
                self._record_lifecycle(candidate, "generated", "候选池补位生成")
            self._event("candidates_top_up_generated", f"Cycle {cycle}: generated {len(generated)} top-up candidates.")
            locally_passed = self._local_prefilter(generated, cycle, fields, operators)
            self._archive(
                archive_stats,
                archive_samples,
                [
                    candidate
                    for candidate in generated
                    if candidate.lifecycle_status == "local_prefilter_rejected"
                ],
            )
            self._archive(archive_stats, archive_samples, self._merge_into_pool(pool_by_expression, locally_passed, blocked_expressions))
            self._archive(archive_stats, archive_samples, self._remove_below_local_standard(pool_by_expression))
            self._archive(archive_stats, archive_samples, self._prune_pool(pool_by_expression))

        if attempts:
            pool = rank_candidates(list(pool_by_expression.values()))
            available = len(self._candidate_pool_candidates(pool))
            self._progress(
                "candidate_pool",
                available,
                retained_limit,
                f"候选池补位完成：可见候选 {available}/{retained_limit}；等待回测 Alpha 已从候选池视图移出。",
                data=self._runtime_data(cycle, pool, accepted_candidates, archive_stats),
            )

    def _merge_into_pool(
        self,
        pool_by_expression: dict[str, Candidate],
        candidates: list[Candidate],
        blocked_expressions: set[str],
    ) -> list[Candidate]:
        return self._candidate_pool_service().merge_into_pool(
            pool_by_expression,
            candidates,
            blocked_expressions,
        )

    def _remove_below_local_standard(self, pool_by_expression: dict[str, Candidate]) -> list[Candidate]:
        return self._candidate_pool_service().remove_below_local_standard(pool_by_expression)

    def _prune_pool(self, pool_by_expression: dict[str, Candidate]) -> list[Candidate]:
        return self._candidate_pool_service().prune_pool(
            pool_by_expression,
            is_active_backtest_candidate=self._is_active_backtest_candidate,
        )

    def _validation_targets(self, pool: list[Candidate]) -> list[Candidate]:
        targets = self._candidate_pool_service().validation_targets(pool)
        filtered: list[Candidate] = []
        for candidate in targets:
            if self.services.official_validation._block_observability_duplicate_before_official(candidate, phase="official_validation"):
                continue
            if self._reject_high_cloud_similarity_before_official(candidate):
                continue
            filtered.append(candidate)
        return filtered

    def _validation_quota(self, pool: list[Candidate]) -> int:
        active_limit = self._active_backtest_limit()
        active_count = self.backtest_slot_manager.active_count()
        self._preflight_pending_backtest_candidates(pool)
        pending_count = len(self._pending_backtest_candidates(pool))
        needed_for_slots = max(0, active_limit - active_count - pending_count)
        return min(
            max(0, int(self.config.budget.max_official_validations_per_cycle)),
            needed_for_slots,
        )

    def _pending_backtest_plan(self, pool: list[Candidate]):
        candidates = self._candidate_pool_service().pending_backtest_candidates(
            pool,
            threshold=self.config.budget.min_prior_score_for_official_simulation,
        )
        plan = self._batch_backtest_coordinator().plan(
            candidates,
            capacity=self._active_backtest_limit(),
        )
        self.last_runtime_data["backtest_batch_plan"] = plan.to_dict()
        return plan

    def _preflight_pending_backtest_candidates(self, pool: list[Candidate]) -> None:
        self._pending_backtest_plan(pool)

    def _backtest_targets(self, pool: list[Candidate]) -> list[Candidate]:
        plan = self._pending_backtest_plan(pool)
        return list(plan.selected)

    def _pending_backtest_candidates(self, pool: list[Candidate], threshold: float | None = None) -> list[Candidate]:
        return self._candidate_pool_service().pending_backtest_candidates(pool, threshold=threshold)

    def _is_pending_backtest_candidate(self, candidate: Candidate, threshold: float | None = None) -> bool:
        return self._candidate_pool_service().is_pending_backtest_candidate(candidate, threshold)

    def _is_active_backtest_candidate(self, candidate: Candidate) -> bool:
        return is_active_backtest_candidate(candidate)

    def _candidate_pool_candidates(self, pool: list[Candidate]) -> list[Candidate]:
        return self._candidate_pool_service().candidate_pool_candidates(
            pool,
            is_active_backtest_candidate=self._is_active_backtest_candidate,
        )

    def _pending_simulation_targets(self, pool: list[Candidate]) -> list[Candidate]:
        return pending_simulation_targets(pool)

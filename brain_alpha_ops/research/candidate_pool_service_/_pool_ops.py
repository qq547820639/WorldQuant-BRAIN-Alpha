"""Pool-management mixin for ``CandidatePoolService_``.

Extracted from the original ``candidate_pool_service_.py`` monolith. Carries
the pool top-up loop, the official-context refresh helpers, and the thin
delegation wrappers around ``pipeline._candidate_pool_service()`` /
``pipeline._batch_backtest_coordinator()``. These methods all operate on the
``pool_by_expression`` / ``pool`` data structures rather than on individual
candidates, which is why they live together here.
"""

from __future__ import annotations

from brain_alpha_ops.models import Candidate

from brain_alpha_ops.research.candidate_pool import (
    is_active_backtest_candidate,
    pending_simulation_targets,
)
from brain_alpha_ops.research.pipeline_helpers import rank_candidates
from brain_alpha_ops.research.pipeline_official_context import (
    active_dataset_field_names,
    official_context_reasons,
    refresh_context_validation_cache,
)


class _PoolOpsMixin:
    """Pool top-up, official-context refresh, and pool delegation helpers.

    The mixin is consumed by ``CandidatePoolService_`` in ``_service``. It
    relies on ``self._pipeline`` being set by the assembling class and on
    ``_LocalPrefilterMixin._local_prefilter`` being available for the top-up
    loop.
    """

    def _top_up_candidate_pool(self, cycle: int, pool_by_expression: dict[str, Candidate], blocked_expressions: set[str], archive_stats: dict[str, int], archive_samples: list[Candidate], fields: list[dict], operators: list[dict], accepted_candidates: list[Candidate]):
        p = self._pipeline
        retained_limit = max(1, p.config.budget.retained_alpha_pool_size)
        attempts = 0
        while (
            len(self._candidate_pool_candidates(list(pool_by_expression.values()))) < retained_limit
            and attempts < 2
            and not p.services.runtime._should_stop()
        ):
            available = len(self._candidate_pool_candidates(list(pool_by_expression.values())))
            deficit = retained_limit - available
            batch_size = min(
                max(int(deficit * 2), retained_limit),
                max(1, int(p.config.budget.max_candidates_per_cycle)),
            )
            generated = p.generator.generate(batch_size, dataset_id=p._active_dataset_id)
            attempts += 1
            if not generated:
                break
            p._attach_active_assistant_guidance(generated)
            p.produced_count += len(generated)
            for candidate in generated:
                p.services.runtime._record_lifecycle(candidate, "generated", "候选池补位生成")
            p.services.runtime._event("candidates_top_up_generated", f"Cycle {cycle}: generated {len(generated)} top-up candidates.")
            locally_passed = self._local_prefilter(generated, cycle, fields, operators)
            p.services.runtime._archive(
                archive_stats,
                archive_samples,
                [candidate for candidate in generated if candidate.lifecycle_status == "local_prefilter_rejected"],
            )
            p.services.runtime._archive(archive_stats, archive_samples, self._merge_into_pool(pool_by_expression, locally_passed, blocked_expressions))
            p.services.runtime._archive(archive_stats, archive_samples, self._remove_below_local_standard(pool_by_expression))
            p.services.runtime._archive(archive_stats, archive_samples, self._prune_pool(pool_by_expression))

        if attempts:
            pool = rank_candidates(list(pool_by_expression.values()))
            available = len(self._candidate_pool_candidates(pool))
            p.services.runtime._progress(
                "candidate_pool",
                available,
                retained_limit,
                f"候选池补位完成：可见候选 {available}/{retained_limit}；等待回测 Alpha 已从候选池视图移出。",
                data=p._runtime_data(cycle, pool, accepted_candidates, archive_stats),
            )

    def _refresh_context_validation_cache(self, fields: list[dict], operators: list[dict]) -> None:
        p = self._pipeline
        state = refresh_context_validation_cache(fields, operators)
        p._context_field_names = state.field_names
        p._context_operator_names = state.operator_names
        p._dataset_field_names_cache = state.dataset_field_names_cache

    def _active_dataset_field_names(self) -> set[str]:
        p = self._pipeline
        return active_dataset_field_names(p._active_dataset_id, p._mapper, p._dataset_field_names_cache)

    def _official_context_reasons(self, candidate: Candidate, fields: list[dict], operators: list[dict]) -> list[str]:
        p = self._pipeline
        if (fields and not p._context_field_names) or (operators and not p._context_operator_names):
            self._refresh_context_validation_cache(fields, operators)
        return official_context_reasons(
            candidate,
            available_fields=p._context_field_names,
            available_operators=p._context_operator_names,
            active_dataset_id=p._active_dataset_id,
            mapper=p._mapper,
            dataset_field_names_cache=p._dataset_field_names_cache,
        )

    def _merge_into_pool(self, pool_by_expression: dict[str, Candidate], candidates: list[Candidate], blocked_expressions: set[str]) -> list[Candidate]:
        return self._pipeline._candidate_pool_service().merge_into_pool(pool_by_expression, candidates, blocked_expressions)

    def _remove_below_local_standard(self, pool_by_expression: dict[str, Candidate]) -> list[Candidate]:
        return self._pipeline._candidate_pool_service().remove_below_local_standard(pool_by_expression)

    def _prune_pool(self, pool_by_expression: dict[str, Candidate]) -> list[Candidate]:
        return self._pipeline._candidate_pool_service().prune_pool(pool_by_expression, is_active_backtest_candidate=self._is_active_backtest_candidate)

    def _validation_targets(self, pool: list[Candidate]) -> list[Candidate]:
        p = self._pipeline
        targets = p._candidate_pool_service().validation_targets(pool)
        filtered: list[Candidate] = []
        for candidate in targets:
            if p.services.official_validation._block_observability_duplicate_before_official(candidate, phase="official_validation"):
                continue
            if self._reject_high_cloud_similarity_before_official(candidate):
                continue
            filtered.append(candidate)
        return filtered

    def _validation_quota(self, pool: list[Candidate]) -> int:
        p = self._pipeline
        active_limit = p._active_backtest_limit()
        active_count = p.backtest_slot_manager.active_count()
        self._preflight_pending_backtest_candidates(pool)
        pending_count = len(self._pending_backtest_candidates(pool))
        needed_for_slots = max(0, active_limit - active_count - pending_count)
        return min(max(0, int(p.config.budget.max_official_validations_per_cycle)), needed_for_slots)

    def _pending_backtest_plan(self, pool: list[Candidate]):
        p = self._pipeline
        candidates = p._candidate_pool_service().pending_backtest_candidates(pool, threshold=p.config.budget.min_prior_score_for_official_simulation)
        plan = p._batch_backtest_coordinator().plan(candidates, capacity=p._active_backtest_limit())
        p.last_runtime_data["backtest_batch_plan"] = plan.to_dict()
        return plan

    def _preflight_pending_backtest_candidates(self, pool: list[Candidate]) -> None:
        self._pending_backtest_plan(pool)

    def _backtest_targets(self, pool: list[Candidate]) -> list[Candidate]:
        plan = self._pending_backtest_plan(pool)
        return list(plan.selected)

    def _pending_backtest_candidates(self, pool: list[Candidate], threshold: float | None = None) -> list[Candidate]:
        return self._pipeline._candidate_pool_service().pending_backtest_candidates(pool, threshold=threshold)

    def _is_pending_backtest_candidate(self, candidate: Candidate, threshold: float | None = None) -> bool:
        return self._pipeline._candidate_pool_service().is_pending_backtest_candidate(candidate, threshold)

    def _is_active_backtest_candidate(self, candidate: Candidate) -> bool:
        return is_active_backtest_candidate(candidate)

    def _candidate_pool_candidates(self, pool: list[Candidate]) -> list[Candidate]:
        return self._pipeline._candidate_pool_service().candidate_pool_candidates(pool, is_active_backtest_candidate=self._is_active_backtest_candidate)

    def _pending_simulation_targets(self, pool: list[Candidate]) -> list[Candidate]:
        return pending_simulation_targets(pool)

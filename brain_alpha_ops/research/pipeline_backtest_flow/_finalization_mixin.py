"""Backtest finalization, retry, and fusion helpers for ``PipelineBacktestMixin``.

Extracted from the original ``pipeline_backtest_flow.py`` monolith. The
candidate finalization (``_finalize_backtest_candidate``), simulation
retry logic (``_simulation_retry_count`` / ``_retry_simulation_candidate``)
and the fusion-candidate factories (``_create_secondary_fusion_candidate``
/ ``_try_fusion_top_candidates``) live here and are mixed into
``PipelineBacktestMixin`` (see ``_mixin``) to keep the public class API
unchanged while respecting the per-submodule line budget.
"""

from __future__ import annotations

from brain_alpha_ops.models import Candidate

from brain_alpha_ops.research.pipeline_helpers import blocked_gate as _blocked_gate
from brain_alpha_ops.research.pipeline_helpers import expr_key as _expr_key


class _BacktestFinalizationMixin:
    def _finalize_backtest_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        blocked_expressions: set[str],
        submitted_this_run: int,
        auto_submit: bool,
    ) -> int:
        outcome = self._backtest_finalization_service().finalize(
            candidate,
            pool_by_expression=pool_by_expression,
            accepted_candidates=accepted_candidates,
            archive_stats=archive_stats,
            archive_samples=archive_samples,
            blocked_expressions=blocked_expressions,
            submitted_this_run=submitted_this_run,
            auto_submit=auto_submit,
        )
        self.ready_since_strategy_switch += outcome.ready_increment
        self.official_rejections_since_strategy_switch += outcome.rejection_increment
        return outcome.submitted_this_run

    def _simulation_retry_count(self, candidate: Candidate) -> int:
        try:
            return max(0, int(candidate.submission.get("simulation_retry_count", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def _retry_simulation_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        reason: str,
    ) -> bool:
        max_retries = max(0, int(self.config.budget.max_simulation_retries or 0))
        retry_count = self._simulation_retry_count(candidate)
        if candidate.official_metrics or retry_count >= max_retries:
            return False

        # P0-5 fix: preserve original state before clearing so that if the
        # retry also fails the pipeline still has the first attempt's data
        # for diagnostics and scoring fallback.
        if candidate.official_alpha_id:
            candidate.submission["previous_official_alpha_id"] = candidate.official_alpha_id
        if candidate.simulation_id:
            candidate.submission["previous_simulation_id"] = candidate.simulation_id
        candidate.simulation_id = ""
        candidate.official_alpha_id = ""
        candidate.lifecycle_status = "simulation_retry_pending"
        candidate.submission["simulation_retry_count"] = retry_count + 1
        candidate.submission["simulation_status"] = "RETRY_PENDING"
        candidate.submission["next_poll_at"] = 0.0
        candidate.submission["poll_count"] = 0
        candidate.gate = _blocked_gate("SIMULATION_RETRY_PENDING", [reason])
        pool_by_expression[_expr_key(candidate)] = candidate
        self._record_lifecycle(candidate, "simulation_retry_pending", reason)
        self._event(
            "simulation_retry_scheduled",
            f"Retry {retry_count + 1}/{max_retries} scheduled after official simulation failure.",
            candidate.alpha_id,
            data={"retry_count": retry_count + 1, "max_retries": max_retries},
            level="WARN",
        )
        return True

    def _create_secondary_fusion_candidate(
        self,
        candidate: Candidate,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        reason: str,
    ) -> Candidate | None:
        outcome = self._secondary_fusion_service().create(
            candidate,
            pool_by_expression=pool_by_expression,
            blocked_expressions=blocked_expressions,
            reason=reason,
        )
        self.produced_count += outcome.produced_increment
        return outcome.candidate

    def _try_fusion_top_candidates(
        self,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        cycle: int,
    ) -> int:
        outcome = self._fusion_candidate_service().create_top_candidate_fusions(
            pool_by_expression,
            blocked_expressions,
            cycle=cycle,
        )
        self.produced_count += outcome.created_count
        return outcome.created_count

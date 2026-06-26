"""Finalization, retry, and fusion mixin for ``BacktestFlowService``.

Extracted from the original ``backtest_flow_service.py`` monolith. Carries
the post-poll finalization delegation, the simulation-retry bookkeeping,
and the secondary-fusion / top-candidate-fusion delegation helpers. These
methods all deal with the lifecycle transitions that happen after a
backtest slot is resolved (accepted, rejected, retried, or fused).
"""

from __future__ import annotations

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.pipeline_helpers import (
    blocked_gate as _blocked_gate,
)
from brain_alpha_ops.research.pipeline_helpers import (
    expr_key as _expr_key,
)


class _FinalizationMixin:
    """Backtest finalization, retry, and fusion helpers.

    The mixin is consumed by ``BacktestFlowService`` in ``_service``. It
    assumes the host class exposes ``self._pipeline`` (an
    ``AlphaResearchPipeline`` instance).
    """

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
        p = self._pipeline
        outcome = p._backtest_finalization_service().finalize(
            candidate,
            pool_by_expression=pool_by_expression,
            accepted_candidates=accepted_candidates,
            archive_stats=archive_stats,
            archive_samples=archive_samples,
            blocked_expressions=blocked_expressions,
            submitted_this_run=submitted_this_run,
            auto_submit=auto_submit,
        )
        p.ready_since_strategy_switch += outcome.ready_increment
        p.official_rejections_since_strategy_switch += outcome.rejection_increment
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
        p = self._pipeline
        max_retries = max(0, int(p.config.budget.max_simulation_retries or 0))
        retry_count = self._simulation_retry_count(candidate)
        if candidate.official_metrics or retry_count >= max_retries:
            return False

        if candidate.official_alpha_id:
            candidate.submission["previous_official_alpha_id"] = candidate.official_alpha_id
        if candidate.simulation_id:
            candidate.submission["previous_simulation_id"] = candidate.simulation_id
        candidate.simulation_id = ""
        candidate.official_alpha_id = ""
        candidate.official_metrics = {}
        candidate.lifecycle_status = "simulation_retry_pending"
        candidate.submission["simulation_retry_count"] = retry_count + 1
        candidate.submission["simulation_status"] = "RETRY_PENDING"
        candidate.submission["next_poll_at"] = 0.0
        candidate.submission["poll_count"] = 0
        candidate.gate = _blocked_gate("SIMULATION_RETRY_PENDING", [reason])
        pool_by_expression[_expr_key(candidate)] = candidate
        p.services.runtime._record_lifecycle(candidate, "simulation_retry_pending", reason)
        p.services.runtime._event(
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
        p = self._pipeline
        outcome = p._secondary_fusion_service().create(
            candidate,
            pool_by_expression=pool_by_expression,
            blocked_expressions=blocked_expressions,
            reason=reason,
        )
        p.produced_count += outcome.produced_increment
        return outcome.candidate

    def _try_fusion_top_candidates(
        self,
        pool_by_expression: dict[str, Candidate],
        blocked_expressions: set[str],
        cycle: int,
    ) -> int:
        p = self._pipeline
        return p._try_fusion_top_candidates(pool_by_expression, blocked_expressions, cycle)

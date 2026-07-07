"""Slot-submission mixin for ``BacktestFlowService``.

Extracted from the original ``backtest_flow_service.py`` monolith. Carries
the backtest-slot filling loop, the next-candidate selector, and the
submit-error delegation helper. These methods all deal with submitting
candidates into open backtest slots, which is why they live together here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.pipeline_helpers import (
    expr_key as _expr_key,
)
from brain_alpha_ops.research.pipeline_helpers import rank_candidates
from brain_alpha_ops.research.pipeline_state import CycleState

if TYPE_CHECKING:
    from brain_alpha_ops.research.pipeline import AlphaResearchPipeline


class _SlotSubmissionMixin:
    """Backtest slot filling and submission helpers.

    The mixin is consumed by ``BacktestFlowService`` in ``_service``. It
    assumes the host class exposes ``self._pipeline`` (an
    ``AlphaResearchPipeline`` instance).
    """

    def _fill_backtest_slots(self, cycle: int, state: CycleState):
        p = self._pipeline
        if p.official_calls_halted:
            return
        active_limit = p._active_backtest_limit()
        open_slots = p.backtest_slot_manager.open_slots(active_limit)
        if not open_slots:
            return

        submission_service = p._backtest_submission_service()
        for slot in open_slots:
            pool = rank_candidates(list(state.pool_by_expression.values()))
            candidate = self._next_backtest_candidate(pool)
            if not candidate:
                return
            if p.services.official_validation._block_observability_duplicate_before_official(candidate, phase="official_simulation"):
                state.pool_by_expression.pop(_expr_key(candidate), None)
                state.blocked_expressions.add(_expr_key(candidate))
                p.services.runtime._archive(state.archive_stats, state.archive_samples, [candidate])
                continue
            p.services.runtime._progress(
                "simulation_submit",
                slot - 1,
                active_limit,
                f"回测槽 {slot} 准备提交：{candidate.alpha_id}",
                candidate.alpha_id,
                data=p._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
            )
            outcome = submission_service.submit_slot(slot, candidate)
            if not outcome.submitted:
                p.services.runtime._record_backtest(
                    candidate,
                    "submit_failed",
                    slot=slot,
                    note=redact_error_message(outcome.error) if outcome.error else outcome.note,
                    error_context=(
                        p.services.runtime._official_error_context(
                            outcome.error,
                            outcome.error_code or "SIMULATION_SUBMIT_ERROR",
                            phase="simulation_submit",
                            candidate=candidate,
                        )
                        if outcome.error
                        else None
                    ),
                )
                p.services.runtime._progress(
                    "official_deferred" if p.official_calls_halted else "simulation_submit",
                    slot,
                    active_limit,
                    f"回测槽 {slot} 提交延后：{candidate.lifecycle_status}",
                    candidate.alpha_id,
                    data=p._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
                )
                # F-056: skip this failed slot and try the next open slot, do
                # NOT return — returning aborts the whole loop so later slots
                # (e.g. slots 2/3 in a 3-slot cycle) are never attempted. The
                # dedupe branch above already uses `continue` for the same
                # loop, confirming continue is the intended skip semantics.
                continue

            p.backtests_submitted += 1
            p.services.runtime._record_lifecycle(candidate, "simulation_submitted", f"slot={slot}")
            p.services.runtime._record_backtest(candidate, "submitted", slot=slot, status="SUBMITTED")
            p.services.runtime._progress(
                "simulation_submit",
                slot,
                active_limit,
                f"回测槽 {slot} 已提交：{outcome.simulation_id}",
                candidate.alpha_id,
                data=p._runtime_data(cycle, rank_candidates(list(state.pool_by_expression.values())), state.accepted_candidates, state.archive_stats),
            )

    def _next_backtest_candidate(self, pool: list[Candidate]) -> Candidate | None:
        p = self._pipeline
        return p.backtest_slot_manager.next_candidate(
            p.services.candidate_pool._backtest_targets(pool),
            key_fn=_expr_key,
        )

    def _handle_slot_submit_error(self, exc, candidate: Candidate):
        self._pipeline._backtest_submission_service()._handle_submit_error(exc, candidate)

"""Backtest slot filling and submission helpers for ``PipelineBacktestMixin``.

Extracted from the original ``pipeline_backtest_flow.py`` monolith. The
slot-filling orchestration (``_fill_backtest_slots``), candidate selection
(``_next_backtest_candidate``) and submit-error handler
(``_handle_slot_submit_error``) live here and are mixed into
``PipelineBacktestMixin`` (see ``_mixin``) to keep the public class API
unchanged while respecting the per-submodule line budget.
"""

from __future__ import annotations

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from brain_alpha_ops.research.pipeline_helpers import expr_key as _expr_key
from brain_alpha_ops.research.pipeline_helpers import rank_candidates
from brain_alpha_ops.research.pipeline_state import CycleState


class _BacktestSlotMixin:
    def _fill_backtest_slots(
        self,
        cycle: int,
        state: CycleState,
    ):
        if self.official_calls_halted:
            return
        active_limit = self._active_backtest_limit()
        open_slots = self.backtest_slot_manager.open_slots(active_limit)
        if not open_slots:
            return

        submission_service = self._backtest_submission_service()
        for slot in open_slots:
            pool = rank_candidates(list(state.pool_by_expression.values()))
            candidate = self._next_backtest_candidate(pool)
            if not candidate:
                return
            if self.services.official_validation._block_observability_duplicate_before_official(candidate, phase="official_simulation"):
                state.pool_by_expression.pop(_expr_key(candidate), None)
                state.blocked_expressions.add(_expr_key(candidate))
                self._archive(state.archive_stats, state.archive_samples, [candidate])
                continue
            self._progress(
                "simulation_submit",
                slot - 1,
                active_limit,
                f"回测槽 {slot} 准备提交：{candidate.alpha_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
            )
            outcome = submission_service.submit_slot(slot, candidate)
            if not outcome.submitted:
                self._record_backtest(
                    candidate,
                    "submit_failed",
                    slot=slot,
                    note=redact_error_message(outcome.error) if outcome.error else outcome.note,
                    error_context=(
                        self._official_error_context(
                            outcome.error,
                            outcome.error_code or "SIMULATION_SUBMIT_ERROR",
                            phase="simulation_submit",
                            candidate=candidate,
                        )
                        if outcome.error
                        else None
                    ),
                )
                self._progress(
                    "official_deferred" if self.official_calls_halted else "simulation_submit",
                    slot,
                    active_limit,
                    f"回测槽 {slot} 提交延后：{candidate.lifecycle_status}",
                    candidate.alpha_id,
                    data=self._runtime_data(cycle, pool, state.accepted_candidates, state.archive_stats),
                )
                return

            self.backtests_submitted += 1
            self._record_lifecycle(candidate, "simulation_submitted", f"slot={slot}")
            self._record_backtest(candidate, "submitted", slot=slot, status="SUBMITTED")
            self._progress(
                "simulation_submit",
                slot,
                active_limit,
                f"回测槽 {slot} 已提交：{outcome.simulation_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(state.pool_by_expression.values())), state.accepted_candidates, state.archive_stats),
            )

    def _next_backtest_candidate(self, pool: list[Candidate]) -> Candidate | None:
        return self.backtest_slot_manager.next_candidate(
            self._backtest_targets(pool),
            key_fn=_expr_key,
        )

    def _handle_slot_submit_error(self, exc: BrainAPIError, candidate: Candidate):  # type: ignore[name-defined]
        self._backtest_submission_service()._handle_submit_error(exc, candidate)

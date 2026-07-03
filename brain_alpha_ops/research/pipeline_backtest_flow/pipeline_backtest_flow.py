"""``PipelineBacktestMixin`` class assembly plus submission/polling mixins.

Consolidated from the original ``pipeline_backtest_flow.py`` monolith's
split files (``_mixin`` / ``_slot_submission_mixin`` / ``_polling_mixin``).
Holds the public ``PipelineBacktestMixin`` class assembly plus the
slot-filling orchestration (``_fill_backtest_slots``), candidate
selection (``_next_backtest_candidate``), submit-error handler
(``_handle_slot_submit_error``), due-backtest polling loop
(``_poll_due_backtests``) and unified poll-interval accessor
(``_poll_interval_seconds``).

The post-simulation checks and finalization helpers live in
``pipeline_backtest_flow_mixins.py`` and are re-assembled onto
``PipelineBacktestMixin`` via multiple inheritance.
"""

from __future__ import annotations

import time

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from brain_alpha_ops.research.pipeline_helpers import expr_key as _expr_key
from brain_alpha_ops.research.pipeline_helpers import rank_candidates
from brain_alpha_ops.research.pipeline_state import CycleState

from .pipeline_backtest_flow_mixins import (
    _BacktestChecksMixin,
    _BacktestFinalizationMixin,
)


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


class _BacktestPollMixin:
    def _poll_due_backtests(
        self,
        cycle: int,
        pool_by_expression: dict[str, Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
        archive_samples: list[Candidate],
        blocked_expressions: set[str],
        submitted_this_run: int,
        auto_submit: bool,
        *,
        force_initial: bool = False,
    ) -> int:
        if not self.backtest_slots:
            return submitted_this_run
        now = time.monotonic()
        interval = self._poll_interval_seconds()
        polling_service = self._backtest_polling_service()
        poll_iteration = 0
        for slot, candidate in self.backtest_slot_manager.items_snapshot():
            # P1-3: check stop signal every 5 slot iterations so the pipeline
            # responds to user cancellation during long polling runs.
            poll_iteration += 1
            if poll_iteration % 5 == 0 and self._should_stop():
                self._event(
                    "polling_stopped",
                    f"Backtest polling stopped by user request at slot {slot}.",
                    candidate.alpha_id,
                    level="WARN",
                )
                self.backtest_slot_manager.release(slot)
                return submitted_this_run

            next_poll_at = float(candidate.submission.get("next_poll_at", 0.0) or 0.0)
            # P1-11 fix: when force_initial=True, unconditionally bypass the
            # next_poll_at gate so that pipeline recovery (e.g. after restart)
            # polls all existing backtest slots immediately regardless of
            # their prior poll timing or poll_count.
            if not force_initial:
                if now < next_poll_at:
                    continue

            candidate.submission["poll_count"] = int(candidate.submission.get("poll_count", 0) or 0) + 1
            self._progress(
                "simulation_wait",
                slot,
                self._active_backtest_limit(),
                f"轮询回测槽 {slot}：{candidate.alpha_id}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
            outcome = polling_service.poll(candidate, now=now, interval=interval)
            for record in outcome.records:
                self._record_backtest(
                    candidate,
                    record.action,
                    slot=slot,
                    status=record.status,
                    note=record.note,
                    error_context=(
                        self._official_error_context(
                            record.error,
                            record.error_code,
                            phase=record.phase,
                            candidate=candidate,
                        )
                        if record.error
                        else None
                    ),
                )

            self.officially_simulated_count += outcome.official_simulated_increment
            self.official_results_since_strategy_switch += outcome.official_result_increment
            if outcome.official_result:
                self._run_alpha_checks(candidate, outcome.result, cycle)
                self._run_robustness_checks(candidate, cycle)

            if outcome.release_slot:
                self.backtest_slot_manager.release(slot)
            if outcome.finalize:
                submitted_this_run = self._finalize_backtest_candidate(
                    candidate,
                    pool_by_expression,
                    accepted_candidates,
                    archive_stats,
                    archive_samples,
                    blocked_expressions,
                    submitted_this_run,
                    auto_submit,
                )
            if outcome.halted:
                return submitted_this_run

            self._progress(
                "simulation_wait",
                slot,
                self._active_backtest_limit(),
                f"回测槽 {slot} 状态：{candidate.submission.get('simulation_status') or candidate.lifecycle_status}",
                candidate.alpha_id,
                data=self._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
        return submitted_this_run

    def _poll_interval_seconds(self) -> float:
        """Return the poll interval from the unified config source.

        P1-1: unified to a single config source — self.config.official_api —
        to prevent silent drift when self.api.config exists but disagrees.
        """
        return max(0.1, float(self.config.official_api.poll_interval_seconds))


class PipelineBacktestMixin(
    _BacktestSlotMixin,
    _BacktestPollMixin,
    _BacktestChecksMixin,
    _BacktestFinalizationMixin,
):
    """Backtest slot, polling, finalization, and fusion helpers for
    ``AlphaResearchPipeline``.

    Assembled from the four responsibility-specific sub-mixins so the
    public class API remains identical to the original monolith.
    """

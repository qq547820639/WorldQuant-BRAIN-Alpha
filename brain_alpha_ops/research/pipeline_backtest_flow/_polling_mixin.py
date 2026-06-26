"""Backtest polling helpers for ``PipelineBacktestMixin``.

Extracted from the original ``pipeline_backtest_flow.py`` monolith. The
due-backtest polling loop (``_poll_due_backtests``) and the unified poll
interval accessor (``_poll_interval_seconds``) live here and are mixed
into ``PipelineBacktestMixin`` (see ``_mixin``) to keep the public class
API unchanged while respecting the per-submodule line budget.
"""

from __future__ import annotations

import time

from brain_alpha_ops.models import Candidate

from brain_alpha_ops.research.pipeline_helpers import rank_candidates


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

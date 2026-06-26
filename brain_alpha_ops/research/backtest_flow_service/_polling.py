"""Polling mixin for ``BacktestFlowService``.

Extracted from the original ``backtest_flow_service.py`` monolith. Carries
the due-backtest polling loop and the poll-interval helper. These methods
deal with checking the status of in-flight simulations and reacting to
poll outcomes (records, robustness/alpha checks, finalization).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.pipeline_helpers import rank_candidates

if TYPE_CHECKING:
    from brain_alpha_ops.research.pipeline import AlphaResearchPipeline


class _PollingMixin:
    """Backtest polling helpers.

    The mixin is consumed by ``BacktestFlowService`` in ``_service``. It
    assumes the host class exposes ``self._pipeline`` (an
    ``AlphaResearchPipeline`` instance) and the sibling methods
    ``_run_alpha_checks``, ``_run_robustness_checks``, and
    ``_finalize_backtest_candidate`` (provided by the other mixins).
    """

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
        p = self._pipeline
        if not p.backtest_slots:
            return submitted_this_run
        now = time.monotonic()
        interval = self._poll_interval_seconds()
        polling_service = p._backtest_polling_service()
        for slot, candidate in p.backtest_slot_manager.items_snapshot():
            next_poll_at = float(candidate.submission.get("next_poll_at", 0.0) or 0.0)
            if not force_initial:
                if now < next_poll_at:
                    continue

            candidate.submission["poll_count"] = int(candidate.submission.get("poll_count", 0) or 0) + 1
            p.services.runtime._progress(
                "simulation_wait",
                slot,
                p._active_backtest_limit(),
                f"轮询回测槽 {slot}：{candidate.alpha_id}",
                candidate.alpha_id,
                data=p._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
            outcome = polling_service.poll(candidate, now=now, interval=interval)
            for record in outcome.records:
                p.services.runtime._record_backtest(
                    candidate,
                    record.action,
                    slot=slot,
                    status=record.status,
                    note=record.note,
                    error_context=(
                        p.services.runtime._official_error_context(
                            record.error,
                            record.error_code,
                            phase=record.phase,
                            candidate=candidate,
                        )
                        if record.error
                        else None
                    ),
                )

            p.officially_simulated_count += outcome.official_simulated_increment
            p.official_results_since_strategy_switch += outcome.official_result_increment
            if outcome.official_result:
                self._run_alpha_checks(candidate, outcome.result, cycle)
                self._run_robustness_checks(candidate, cycle)

            if outcome.release_slot:
                p.backtest_slot_manager.release(slot)
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

            p.services.runtime._progress(
                "simulation_wait",
                slot,
                p._active_backtest_limit(),
                f"回测槽 {slot} 状态：{candidate.submission.get('simulation_status') or candidate.lifecycle_status}",
                candidate.alpha_id,
                data=p._runtime_data(cycle, rank_candidates(list(pool_by_expression.values())), accepted_candidates, archive_stats),
            )
        return submitted_this_run

    def _poll_interval_seconds(self) -> float:
        p = self._pipeline
        api_config = getattr(p.api, "config", None)
        return max(0.1, float(getattr(api_config, "poll_interval_seconds", p.config.official_api.poll_interval_seconds)))

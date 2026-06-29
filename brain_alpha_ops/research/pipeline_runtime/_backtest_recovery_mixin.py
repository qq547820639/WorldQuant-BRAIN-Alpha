"""Persisted backtest slot recovery helper."""

from __future__ import annotations

from brain_alpha_ops.redaction import redact_error_message


class PipelineBacktestRecoveryMixin:
    def _recover_persisted_backtest_slots(self) -> None:
        if not getattr(self.config.budget, "resume_persisted_backtests", True):
            return
        try:
            rows = self.repository.latest_backtest_records(limit=1000)
            recovered = self.backtest_slot_manager.recover_from_records(
                rows,
                max_slots=self._visible_backtest_slot_limit(),
            )
        except Exception as exc:
            message = redact_error_message(exc, max_length=160)
            self._event("backtest_recovery_failed", message, level="WARN")
            # F-034 fix: fail-closed — explicitly zero out the recovered-slot
            # count so stale values from a previous run cannot leak forward.
            self.recovered_backtest_slot_count = 0
            return
        self.recovered_backtest_slot_count = self.backtest_slot_manager.recovered_slot_count
        if self.recovered_backtest_slot_count:
            recovered_rows = [
                {
                    "slot": slot,
                    "alpha_id": candidate.alpha_id,
                    "simulation_id": candidate.simulation_id,
                    "status": candidate.submission.get("simulation_status") or candidate.lifecycle_status,
                    "correlation_id": candidate.submission.get("recovered_correlation_id", ""),
                }
                for slot, candidate in sorted(recovered)
            ]
            self._event(
                "backtest_slots_recovered",
                f"Recovered {self.recovered_backtest_slot_count} persisted backtest slot(s) for polling.",
                data={"backtests": recovered_rows},
            )

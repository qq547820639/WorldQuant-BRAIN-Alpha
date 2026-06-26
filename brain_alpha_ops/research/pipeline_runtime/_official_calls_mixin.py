"""Official-call halt/defer, error context, and retry helpers."""

from __future__ import annotations

import time

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.observability import error_payload


class PipelineOfficialCallsMixin:
    def _official_error_context(
        self,
        exc: BrainAPIError,
        error_code: str,
        *,
        phase: str,
        candidate: Candidate,
    ) -> dict:
        return error_payload(
            exc,
            error_code=error_code,
            max_length=240,
            phase=phase,
            alpha_id=candidate.alpha_id,
            simulation_id=candidate.simulation_id,
            official_alpha_id=candidate.official_alpha_id or candidate.official_metrics.get("official_alpha_id", ""),
        )

    def _defer_official_cycle(
        self,
        cycle: int,
        pool: list[Candidate],
        accepted_candidates: list[Candidate],
        archive_stats: dict[str, int],
    ) -> bool:
        self._progress(
            "official_deferred",
            0,
            1,
            f"官方调用已暂停：{self.official_halt_reason}",
            data=self._runtime_data(
                cycle,
                pool,
                accepted_candidates,
                archive_stats,
                {
                    "retry_seconds": self.config.budget.official_retry_pause_seconds,
                    "retry_remaining_seconds": self._official_retry_remaining_seconds(),
                },
            ),
        )
        remaining = self._official_retry_remaining_seconds()
        pause = min(max(0.1, float(self.config.budget.cycle_pause_seconds or 0.1)), self._poll_interval_seconds())
        if remaining:
            pause = min(pause, max(0.1, remaining))
        if not self._sleep_with_stop(pause):
            return False
        return not self._should_stop()

    def _halt_official_calls(self, reason: str, retry_seconds: float | None = None):
        self.official_calls_halted = True
        self.official_halt_reason = reason
        wait = self.config.budget.official_retry_pause_seconds if retry_seconds is None else retry_seconds
        self.official_resume_at = time.monotonic() + max(0.0, float(wait or 0.0))

    def _maybe_resume_official_calls(self):
        if self.official_calls_halted and time.monotonic() >= self.official_resume_at:
            self.official_calls_halted = False
            self.official_halt_reason = ""
            self.official_resume_at = 0.0

    def _official_retry_remaining_seconds(self) -> float:
        if not self.official_calls_halted:
            return 0.0
        return round(max(0.0, self.official_resume_at - time.monotonic()), 1)

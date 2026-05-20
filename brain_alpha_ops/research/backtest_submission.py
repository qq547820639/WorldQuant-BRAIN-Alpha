"""Official backtest slot submission service."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from .backtest_slots import BacktestSlotManager
from .candidate_pool import blocked_gate


SettingsProvider = Callable[[], dict]
PollIntervalProvider = Callable[[], float]
HaltCallback = Callable[[str, float | None], None]
EventCallback = Callable[..., None]


@dataclass
class BacktestSubmitOutcome:
    submitted: bool
    halted: bool = False
    simulation_id: str = ""
    error: BrainAPIError | None = None
    error_code: str = ""
    note: str = ""


@dataclass
class BacktestSubmissionService:
    api: BrainAPI
    slots: BacktestSlotManager
    settings_provider: SettingsProvider
    poll_interval: PollIntervalProvider
    halt_official_calls: HaltCallback
    event: EventCallback

    def submit_slot(self, slot: int, candidate: Candidate) -> BacktestSubmitOutcome:
        candidate.lifecycle_status = "backtest_slot_selected"
        candidate.submission["backtest_slot"] = slot
        settings = dict(self.settings_provider())
        candidate.submission["settings"] = settings
        try:
            sim_id = self.api.submit_simulation(candidate.expression, settings)
        except BrainAPIError as exc:
            return self._handle_submit_error(exc, candidate)

        candidate.simulation_id = sim_id
        candidate.lifecycle_status = "simulation_submitted"
        candidate.submission["simulation_status"] = "SUBMITTED"
        candidate.submission["next_poll_at"] = time.monotonic() + self.poll_interval()
        candidate.submission["poll_count"] = 0
        self.slots.assign(slot, candidate)
        return BacktestSubmitOutcome(submitted=True, simulation_id=sim_id)

    def _handle_submit_error(self, exc: BrainAPIError, candidate: Candidate) -> BacktestSubmitOutcome:
        error_text = redact_error_message(exc)
        if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in error_text:
            reason = "official concurrent simulation limit exceeded; retry after running BRAIN simulations finish"
            candidate.lifecycle_status = "simulation_deferred_concurrency_limit"
            candidate.gate = blocked_gate("SIMULATION_DEFERRED_CONCURRENCY_LIMIT", [reason])
            self.halt_official_calls(reason, None)
            return BacktestSubmitOutcome(submitted=False, halted=True, error=exc, error_code="SIMULATION_SUBMIT_ERROR", note=reason)
        if exc.status_code == 429:
            retry_after = f"; retry_after={exc.retry_after}" if exc.retry_after is not None else ""
            reason = f"official API rate limit reached{retry_after}; defer remaining official calls"
            candidate.lifecycle_status = "simulation_deferred_rate_limit"
            candidate.gate = blocked_gate("SIMULATION_DEFERRED_RATE_LIMIT", [reason])
            self.halt_official_calls(reason, exc.retry_after)
            return BacktestSubmitOutcome(submitted=False, halted=True, error=exc, error_code="SIMULATION_SUBMIT_ERROR", note=reason)

        candidate.lifecycle_status = "simulation_request_failed"
        candidate.gate = blocked_gate("SIMULATION_REQUEST_FAILED", [error_text[:240]])
        self.event("official_simulation_failed", "; ".join(candidate.gate["failed_reasons"]), candidate.alpha_id)
        return BacktestSubmitOutcome(
            submitted=False,
            halted=False,
            error=exc,
            error_code="SIMULATION_SUBMIT_ERROR",
            note=error_text,
        )

"""Official backtest polling and result-fetch state transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from .candidate_pool import blocked_gate


HaltCallback = Callable[[str, float | None], None]
EventCallback = Callable[..., None]


@dataclass
class BacktestRecordIntent:
    action: str
    status: str = ""
    note: str = ""
    error: BrainAPIError | None = None
    error_code: str = ""
    phase: str = "simulation_wait"


@dataclass
class BacktestPollOutcome:
    action: str
    status: str = ""
    result: dict = field(default_factory=dict)
    finalize: bool = False
    release_slot: bool = False
    halted: bool = False
    official_result: bool = False
    official_result_increment: int = 0
    official_simulated_increment: int = 0
    records: list[BacktestRecordIntent] = field(default_factory=list)


@dataclass
class BacktestPollingService:
    api: BrainAPI
    halt_official_calls: HaltCallback
    event: EventCallback

    def poll(self, candidate: Candidate, *, now: float, interval: float) -> BacktestPollOutcome:
        try:
            status = self.api.poll_simulation(candidate.simulation_id)
        except BrainAPIError as exc:
            return self._handle_poll_error(exc, candidate, now=now, interval=interval)

        candidate.submission["simulation_status"] = status
        outcome = BacktestPollOutcome(action="polled", status=status)
        outcome.records.append(BacktestRecordIntent(action="polled", status=status))

        if status == "COMPLETED":
            return self._fetch_completed_result(candidate, now=now, interval=interval, outcome=outcome)
        if status == "FAILED":
            candidate.lifecycle_status = "simulation_failed"
            candidate.gate = blocked_gate("SIMULATION_FAILED", [status])
            outcome.action = "failed"
            outcome.finalize = True
            outcome.release_slot = True
            outcome.official_result_increment = 1
            outcome.records.append(BacktestRecordIntent(action="failed", status=status))
            return outcome

        candidate.lifecycle_status = "simulation_running"
        candidate.submission["next_poll_at"] = now + interval
        outcome.action = "running"
        outcome.records.append(BacktestRecordIntent(action="running", status=status))
        return outcome

    def _handle_poll_error(
        self,
        exc: BrainAPIError,
        candidate: Candidate,
        *,
        now: float,
        interval: float,
    ) -> BacktestPollOutcome:
        if exc.status_code == 429:
            reason = f"official simulation polling rate limit reached; retry later: {exc}"
            self.halt_official_calls(reason, None)
            candidate.lifecycle_status = "simulation_poll_deferred_rate_limit"
            candidate.gate = blocked_gate("SIMULATION_POLL_DEFERRED_RATE_LIMIT", [reason])
            candidate.submission["next_poll_at"] = now + max(interval, float(exc.retry_after or 0.0))
            self.event("official_simulation_poll_deferred", reason, candidate.alpha_id, level="WARN")
            return BacktestPollOutcome(
                action="poll_deferred",
                halted=True,
                records=[
                    BacktestRecordIntent(
                        action="poll_deferred",
                        note=reason,
                        error=exc,
                        error_code="SIMULATION_POLL_RATE_LIMIT",
                        phase="simulation_wait",
                    )
                ],
            )

        note = redact_error_message(exc)
        candidate.lifecycle_status = "simulation_poll_failed"
        candidate.gate = blocked_gate("SIMULATION_POLL_FAILED", [note])
        return BacktestPollOutcome(
            action="poll_failed",
            finalize=True,
            release_slot=True,
            records=[
                BacktestRecordIntent(
                    action="poll_failed",
                    note=note,
                    error=exc,
                    error_code="SIMULATION_POLL_ERROR",
                    phase="simulation_wait",
                )
            ],
        )

    def _fetch_completed_result(
        self,
        candidate: Candidate,
        *,
        now: float,
        interval: float,
        outcome: BacktestPollOutcome,
    ) -> BacktestPollOutcome:
        try:
            result = self.api.fetch_result(candidate.simulation_id)
        except BrainAPIError as exc:
            if exc.status_code == 429:
                reason = f"official simulation result rate limit reached; retry later: {exc}"
                self.halt_official_calls(reason, None)
                candidate.lifecycle_status = "simulation_result_deferred_rate_limit"
                candidate.gate = blocked_gate("SIMULATION_RESULT_DEFERRED_RATE_LIMIT", [reason])
                candidate.submission["next_poll_at"] = now + max(interval, float(exc.retry_after or 0.0))
                self.event("official_simulation_result_deferred", reason, candidate.alpha_id, level="WARN")
                outcome.action = "result_deferred"
                outcome.halted = True
                outcome.records.append(
                    BacktestRecordIntent(
                        action="result_deferred",
                        note=reason,
                        error=exc,
                        error_code="SIMULATION_RESULT_RATE_LIMIT",
                        phase="simulation_result",
                    )
                )
                return outcome

            note = redact_error_message(exc)
            candidate.lifecycle_status = "simulation_result_failed"
            candidate.gate = blocked_gate("SIMULATION_RESULT_FAILED", [note])
            outcome.action = "result_failed"
            outcome.finalize = True
            outcome.release_slot = True
            outcome.records.append(
                BacktestRecordIntent(
                    action="result_failed",
                    note=note,
                    error=exc,
                    error_code="SIMULATION_RESULT_ERROR",
                    phase="simulation_result",
                )
            )
            return outcome

        candidate.official_alpha_id = result.get("alpha_id", "") or result.get("metrics", {}).get("official_alpha_id", "")
        candidate.official_metrics = result.get("metrics", {})
        candidate.lifecycle_status = "official_simulated"
        outcome.action = "completed"
        outcome.result = result
        outcome.finalize = True
        outcome.release_slot = True
        outcome.official_result = True
        outcome.official_result_increment = 1
        outcome.official_simulated_increment = 1
        outcome.records.append(BacktestRecordIntent(action="completed", status="COMPLETED"))
        return outcome

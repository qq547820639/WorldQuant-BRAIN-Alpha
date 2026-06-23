"""3-slot concurrent scheduler for official BRAIN simulations.

Replaces the sequential Top3 batch submission pattern (DEFECT-008) with a
concurrent 3-slot scheduler where each slot independently manages its lifecycle
(submit → poll → complete/fail/cooldown). Candidate pool production continues
independently of simulation throughput.

Architecture:
  - SimulationSlot: state machine per slot (idle→submitting→polling→done/failed/cooldown)
  - ThreeSlotScheduler: manages 3 slots, picks next candidates, handles cooldowns
  - Integration via callback pattern with the existing pipeline
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger(__name__)


class SlotState(enum.Enum):
    IDLE = "idle"
    SUBMITTING = "submitting"
    POLLING = "polling"
    COMPLETED = "completed"
    FAILED = "failed"
    COOLDOWN = "cooldown"


@dataclass
class SimulationSlot:
    """State machine for a single simulation slot.

    Lifecycle: IDLE → SUBMITTING → POLLING → COMPLETED/FAILED → IDLE
              COOLDOWN → IDLE (after rate limit or error)
    """

    slot_id: int
    state: SlotState = SlotState.IDLE
    candidate: Candidate | None = None
    simulation_id: str = ""
    last_poll_time: float = 0.0
    poll_count: int = 0
    cooldown_until: float = 0.0
    cooldown_reason: str = ""
    error_count: int = 0
    last_error: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    completed_at: float = 0.0

    def is_available(self) -> bool:
        if self.state != SlotState.IDLE:
            return False
        if self.cooldown_until > 0 and time.monotonic() < self.cooldown_until:
            return False
        return True

    def enter_cooldown(self, seconds: float, reason: str) -> None:
        self.state = SlotState.COOLDOWN
        self.cooldown_until = time.monotonic() + seconds
        self.cooldown_reason = reason
        self.error_count += 1
        logger.warning(
            "Slot %d entering cooldown for %.1fs: %s",
            self.slot_id, seconds, reason,
        )

    def reset(self) -> None:
        self.state = SlotState.IDLE
        self.candidate = None
        self.simulation_id = ""
        self.last_poll_time = 0.0
        self.poll_count = 0
        self.cooldown_until = 0.0
        self.cooldown_reason = ""
        self.result = {}
        self.started_at = 0.0
        self.completed_at = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "state": self.state.value,
            "candidate_alpha_id": self.candidate.alpha_id if self.candidate else None,
            "simulation_id": self.simulation_id,
            "poll_count": self.poll_count,
            "cooldown_reason": self.cooldown_reason,
            "error_count": self.error_count,
            "last_error": self.last_error,
        }


@dataclass
class SlotOutcome:
    """Result of a slot tick (one poll cycle)."""

    slot_id: int
    action: str
    candidate: Candidate | None = None
    result: dict[str, Any] = field(default_factory=dict)
    finalized: bool = False
    halted: bool = False
    error: str = ""


# Cooldown durations (seconds) for different error types
_COOLDOWN_429 = 120.0
_COOLDOWN_CONCURRENT_LIMIT = 60.0
_COOLDOWN_SERVER_ERROR = 30.0
_COOLDOWN_GENERIC = 45.0

_MAX_CONSECUTIVE_ERRORS_PER_SLOT = 5
_DEFAULT_POLL_INTERVAL = 15.0


@dataclass
class ThreeSlotScheduler:
    """Manages up to 3 concurrent simulation slots.

    Each slot independently submits, polls, and completes simulations.
    When a slot finishes (or enters cooldown), the next TopK candidate
    from the pool fills it.

    Usage:
        scheduler = ThreeSlotScheduler(api=api, settings_provider=..., ...)
        # Each cycle:
        scheduler.tick(candidates, cycle)  # polls existing + fills empty slots
        # Check results:
        for outcome in scheduler.drain_completed():
            process(outcome)
    """

    api: BrainAPI
    settings_provider: Callable[[], dict[str, Any]]
    poll_interval: Callable[[], float] = field(default=lambda: _DEFAULT_POLL_INTERVAL)
    event_callback: Callable[..., None] = field(default=lambda: lambda *a, **kw: None)
    progress_callback: Callable[..., None] | None = None
    stop_callback: Callable[[], bool] = field(default=lambda: False)
    max_slots: int = 3
    max_simulation_retries: int = 3

    _slots: list[SimulationSlot] = field(init=False, default_factory=list)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    _completed: list[SlotOutcome] = field(init=False, default_factory=list)
    _global_cooldown_until: float = field(init=False, default=0.0)
    _global_cooldown_reason: str = field(init=False, default="")
    _halted: bool = field(init=False, default=False)
    _halt_reason: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self._slots = [
            SimulationSlot(slot_id=i + 1) for i in range(self.max_slots)
        ]

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def active_count(self) -> int:
        return sum(
            1 for s in self._slots
            if s.state in (SlotState.SUBMITTING, SlotState.POLLING)
        )

    def available_slots(self) -> list[SimulationSlot]:
        now = time.monotonic()
        available = []
        for slot in self._slots:
            if slot.state == SlotState.COOLDOWN and now >= slot.cooldown_until:
                slot.reset()
            if slot.is_available():
                if self._global_cooldown_until > 0 and now < self._global_cooldown_until:
                    continue
                available.append(slot)
        return available

    def tick(
        self,
        ranked_candidates: list[Candidate],
        cycle: int,
        active_expression_keys: set[str] | None = None,
    ) -> list[SlotOutcome]:
        """Run one scheduler tick: poll active slots, fill idle slots.

        Args:
            ranked_candidates: Candidates sorted by priority (highest first).
            cycle: Current pipeline cycle number.
            active_expression_keys: Expression keys already in other subsystems
                (to avoid duplicates).

        Returns:
            List of outcomes for completed/failed slots this tick.
        """
        if self._halted:
            return []

        outcomes: list[SlotOutcome] = []
        active_keys = active_expression_keys or set()

        # 1. Poll all active slots
        for slot in self._slots:
            if slot.state == SlotState.POLLING:
                outcome = self._poll_slot(slot, cycle)
                if outcome:
                    outcomes.append(outcome)
                    if outcome.halted:
                        self._halted = True
                        self._halt_reason = f"Slot {slot.slot_id} halt: {outcome.error}"
                        return outcomes

        # 2. Fill idle slots with next candidates
        used_keys = set()
        for slot in self._slots:
            if not slot.is_available():
                continue
            if self._global_cooldown_until > 0 and time.monotonic() < self._global_cooldown_until:
                continue

            candidate = self._pick_next_candidate(
                ranked_candidates, active_keys | used_keys
            )
            if not candidate:
                break

            outcome = self._submit_slot(slot, candidate, cycle)
            if outcome:
                outcomes.append(outcome)
                if outcome.halted:
                    self._halted = True
                    self._halt_reason = f"Slot {slot.slot_id} submit halt: {outcome.error}"
                    return outcomes
            used_keys.add(self._expr_key(candidate))

        return outcomes

    def tick_loop(
        self,
        candidate_provider: Callable[[], list[Candidate]],
        result_handler: Callable[[SlotOutcome], None],
        cycle: int,
        duration_seconds: float = 0,
        active_expression_keys: Callable[[], set[str]] | None = None,
    ) -> None:
        """Run a continuous tick loop for a fixed duration or until stopped.

        Useful for the decoupled pipeline where the scheduler runs
        independently. Polls all active slots at poll_interval and fills
        idle slots as candidates become available.

        Args:
            candidate_provider: Callable returning ranked candidates.
            result_handler: Called with each SlotOutcome.
            cycle: Current cycle number.
            duration_seconds: How long to loop (0 = until stopped).
            active_expression_keys: Callable returning keys to avoid.
        """
        deadline = time.monotonic() + duration_seconds if duration_seconds > 0 else float("inf")
        while time.monotonic() < deadline:
            if self.stop_callback():
                break

            candidates = candidate_provider()
            keys = active_expression_keys() if active_expression_keys else set()
            outcomes = self.tick(candidates, cycle, keys)

            for outcome in outcomes:
                result_handler(outcome)

            # Sleep between poll rounds
            time.sleep(max(0.1, self.poll_interval()))

    def _submit_slot(
        self, slot: SimulationSlot, candidate: Candidate, cycle: int
    ) -> SlotOutcome | None:
        slot.state = SlotState.SUBMITTING
        slot.candidate = candidate
        slot.started_at = time.monotonic()

        settings = dict(self.settings_provider())
        candidate.submission["settings"] = settings
        candidate.submission["backtest_slot"] = slot.slot_id

        self._emit_event(
            "scheduler_submit",
            f"Slot {slot.slot_id}: submitting {candidate.alpha_id}",
            candidate.alpha_id,
            cycle,
        )

        try:
            sim_id = self.api.submit_simulation(candidate.expression, settings)
        except BrainAPIError as exc:
            return self._handle_submit_error(slot, exc, candidate)

        slot.simulation_id = sim_id
        slot.state = SlotState.POLLING
        slot.last_poll_time = time.monotonic()
        candidate.simulation_id = sim_id
        candidate.lifecycle_status = "simulation_submitted"
        candidate.submission["simulation_status"] = "SUBMITTED"
        candidate.submission["next_poll_at"] = time.monotonic() + self.poll_interval()
        candidate.submission["poll_count"] = 0

        self._emit_event(
            "scheduler_submitted",
            f"Slot {slot.slot_id}: submitted sim_id={sim_id}",
            candidate.alpha_id,
            cycle,
        )

        return SlotOutcome(
            slot_id=slot.slot_id,
            action="submitted",
            candidate=candidate,
        )

    def _poll_slot(self, slot: SimulationSlot, cycle: int) -> SlotOutcome | None:
        now = time.monotonic()
        next_poll_at = float(
            slot.candidate.submission.get("next_poll_at", 0.0) or 0.0
        ) if slot.candidate else 0.0

        if now < next_poll_at and slot.poll_count > 0:
            return None

        slot.poll_count += 1
        slot.last_poll_time = now

        try:
            status = self.api.poll_simulation(slot.simulation_id)
        except BrainAPIError as exc:
            return self._handle_poll_error(slot, exc, cycle)

        if slot.candidate:
            slot.candidate.submission["simulation_status"] = status
            slot.candidate.submission["poll_count"] = slot.poll_count

        if status in ("COMPLETED", "COMPLETED"):
            return self._handle_completed(slot, cycle)
        if status == "FAILED":
            return self._handle_failed(slot, cycle)

        # Still running — schedule next poll
        interval = self.poll_interval()
        if slot.candidate:
            slot.candidate.submission["next_poll_at"] = now + interval

        self._emit_event(
            "scheduler_poll_running",
            f"Slot {slot.slot_id}: still running (poll #{slot.poll_count})",
            slot.candidate.alpha_id if slot.candidate else "",
            cycle,
        )
        return None

    def _handle_completed(self, slot: SimulationSlot, cycle: int) -> SlotOutcome:
        candidate = slot.candidate
        try:
            result = self.api.fetch_result(slot.simulation_id)
        except BrainAPIError as exc:
            slot.state = SlotState.FAILED
            slot.last_error = redact_error_message(exc)
            self._emit_event(
                "scheduler_result_error",
                f"Slot {slot.slot_id}: fetch result failed: {slot.last_error}",
                candidate.alpha_id if candidate else "",
                cycle,
                level="WARN",
            )
            outcome = SlotOutcome(
                slot_id=slot.slot_id,
                action="result_error",
                candidate=candidate,
                error=slot.last_error,
            )
            slot.reset()
            return outcome

        if candidate:
            candidate.official_alpha_id = result.get("alpha_id", "") or result.get(
                "metrics", {}
            ).get("official_alpha_id", "")
            candidate.official_metrics = result.get("metrics", {})
            candidate.lifecycle_status = "official_simulated"
            candidate.submission["simulation_status"] = "COMPLETED"

        slot.state = SlotState.COMPLETED
        slot.result = result
        slot.completed_at = time.monotonic()

        self._emit_event(
            "scheduler_completed",
            f"Slot {slot.slot_id}: simulation completed for {candidate.alpha_id if candidate else '?'}",
            candidate.alpha_id if candidate else "",
            cycle,
        )

        outcome = SlotOutcome(
            slot_id=slot.slot_id,
            action="completed",
            candidate=candidate,
            result=result,
            finalized=True,
        )
        slot.reset()
        return outcome

    def _handle_failed(self, slot: SimulationSlot, cycle: int) -> SlotOutcome:
        candidate = slot.candidate
        if candidate:
            candidate.lifecycle_status = "simulation_failed"
            candidate.submission["simulation_status"] = "FAILED"

        slot.state = SlotState.FAILED
        self._emit_event(
            "scheduler_failed",
            f"Slot {slot.slot_id}: simulation failed for {candidate.alpha_id if candidate else '?'}",
            candidate.alpha_id if candidate else "",
            cycle,
            level="WARN",
        )

        outcome = SlotOutcome(
            slot_id=slot.slot_id,
            action="failed",
            candidate=candidate,
            finalized=True,
        )
        slot.reset()
        return outcome

    def _handle_submit_error(
        self, slot: SimulationSlot, exc: BrainAPIError, candidate: Candidate
    ) -> SlotOutcome | None:
        error_text = redact_error_message(exc)
        slot.last_error = error_text
        cycle = 0  # will be set by caller context

        if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in error_text:
            slot.enter_cooldown(_COOLDOWN_CONCURRENT_LIMIT, "concurrent limit exceeded")
            candidate.lifecycle_status = "simulation_deferred_concurrency_limit"
            self._emit_event(
                "scheduler_concurrent_limit",
                f"Slot {slot.slot_id}: concurrent limit hit, cooldown {_COOLDOWN_CONCURRENT_LIMIT}s",
                candidate.alpha_id,
                cycle,
                level="WARN",
            )
            # Don't halt the whole scheduler — just this slot
            slot.reset()
            return SlotOutcome(
                slot_id=slot.slot_id, action="cooldown",
                candidate=candidate, error=error_text,
            )

        if exc.status_code == 429:
            retry_after = exc.retry_after or _COOLDOWN_429
            slot.enter_cooldown(retry_after, f"rate limited (retry_after={retry_after})")
            candidate.lifecycle_status = "simulation_deferred_rate_limit"
            self._emit_event(
                "scheduler_rate_limit",
                f"Slot {slot.slot_id}: 429 rate limited, cooldown {retry_after}s",
                candidate.alpha_id,
                cycle,
                level="WARN",
            )
            slot.reset()
            return SlotOutcome(
                slot_id=slot.slot_id, action="cooldown",
                candidate=candidate, error=error_text,
            )

        # Server error — enter cooldown, don't halt pipeline
        slot.enter_cooldown(_COOLDOWN_SERVER_ERROR, f"server error: {error_text[:120]}")
        candidate.lifecycle_status = "simulation_deferred_server_error"
        self._emit_event(
            "scheduler_submit_error",
            f"Slot {slot.slot_id}: submit error {exc.status_code}, cooldown {_COOLDOWN_SERVER_ERROR}s",
            candidate.alpha_id,
            cycle,
            level="WARN",
        )
        slot.reset()
        return SlotOutcome(
            slot_id=slot.slot_id, action="cooldown",
            candidate=candidate, error=error_text,
        )

    def _handle_poll_error(
        self, slot: SimulationSlot, exc: BrainAPIError, cycle: int
    ) -> SlotOutcome | None:
        error_text = redact_error_message(exc)
        slot.last_error = error_text

        if exc.status_code == 429:
            retry_after = exc.retry_after or _COOLDOWN_429
            slot.enter_cooldown(retry_after, f"poll rate limited (retry_after={retry_after})")
            if slot.candidate:
                slot.candidate.lifecycle_status = "simulation_poll_deferred_rate_limit"
            self._emit_event(
                "scheduler_poll_rate_limit",
                f"Slot {slot.slot_id}: poll 429, cooldown {retry_after}s",
                slot.candidate.alpha_id if slot.candidate else "",
                cycle,
                level="WARN",
            )
            candidate = slot.candidate
            slot.reset()
            return SlotOutcome(
                slot_id=slot.slot_id, action="cooldown",
                candidate=candidate, error=error_text,
            )

        # Other poll error — treat as transient, keep polling
        if slot.candidate:
            slot.candidate.submission["next_poll_at"] = (
                time.monotonic() + max(self.poll_interval() * 2, 30.0)
            )
        self._emit_event(
            "scheduler_poll_error",
            f"Slot {slot.slot_id}: poll error {exc.status_code}, will retry",
            slot.candidate.alpha_id if slot.candidate else "",
            cycle,
            level="WARN",
        )
        return None

    def _pick_next_candidate(
        self,
        ranked_candidates: list[Candidate],
        excluded_keys: set[str],
    ) -> Candidate | None:
        """Pick the highest-priority candidate not already active."""
        active_keys = {self._expr_key(s.candidate) for s in self._slots if s.candidate}
        for candidate in ranked_candidates:
            key = self._expr_key(candidate)
            if key in active_keys or key in excluded_keys:
                continue
            # Skip candidates that are already being simulated
            if candidate.submission.get("simulation_status") in (
                "SUBMITTED", "RUNNING", "PENDING", "QUEUED"
            ):
                continue
            return candidate
        return None

    @staticmethod
    def _expr_key(candidate: Candidate | None) -> str:
        if candidate is None:
            return ""
        return candidate.expression.strip()

    def drain_completed(self) -> list[SlotOutcome]:
        completed = list(self._completed)
        self._completed.clear()
        return completed

    def slot_summaries(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._slots]

    def enter_global_cooldown(self, seconds: float, reason: str) -> None:
        self._global_cooldown_until = time.monotonic() + seconds
        self._global_cooldown_reason = reason
        logger.warning("Global scheduler cooldown for %.1fs: %s", seconds, reason)

    def resume(self) -> None:
        self._halted = False
        self._halt_reason = ""
        self._global_cooldown_until = 0.0
        self._global_cooldown_reason = ""
        for slot in self._slots:
            if slot.state == SlotState.COOLDOWN:
                slot.reset()

    def _emit_event(
        self,
        event: str,
        message: str,
        alpha_id: str = "",
        cycle: int = 0,
        level: str = "INFO",
    ) -> None:
        self.event_callback(
            event, message, alpha_id, level=level,
            data={"cycle": cycle, "slot_summaries": self.slot_summaries()},
        )

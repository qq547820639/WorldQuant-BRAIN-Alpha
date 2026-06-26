"""Tick, submit, poll, and outcome-handling mixin for ``ThreeSlotScheduler``."""

from __future__ import annotations

import time
from typing import Any, Callable

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.simulation_scheduler._types import (
    SlotOutcome,
    SlotState,
    _COOLDOWN_429,
    _COOLDOWN_CONCURRENT_LIMIT,
    _COOLDOWN_SERVER_ERROR,
)


class _SchedulerTickMixin:
    """Tick loop, slot submission, polling, and outcome handling."""

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

    def _submit_slot(
        self, slot, candidate: Candidate, cycle: int
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

    def _poll_slot(self, slot, cycle: int) -> SlotOutcome | None:
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

    def _handle_completed(self, slot, cycle: int) -> SlotOutcome:
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

    def _handle_failed(self, slot, cycle: int) -> SlotOutcome:
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
        self, slot, exc: BrainAPIError, candidate: Candidate
    ) -> SlotOutcome | None:
        error_text = redact_error_message(exc)
        slot.last_error = error_text
        cycle = 0  # will be set by caller context

        if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in error_text:
            # Workstream C2.1: reset FIRST (clears candidate/sim_id), THEN
            # enter cooldown — otherwise reset() wipes cooldown_until/reason
            # and the slot becomes immediately available (no-op cooldown).
            slot.reset()
            slot.enter_cooldown(_COOLDOWN_CONCURRENT_LIMIT, "concurrent limit exceeded")
            candidate.lifecycle_status = "simulation_deferred_concurrency_limit"
            self._emit_event(
                "scheduler_concurrent_limit",
                f"Slot {slot.slot_id}: concurrent limit hit, cooldown {_COOLDOWN_CONCURRENT_LIMIT}s",
                candidate.alpha_id,
                cycle,
                level="WARN",
            )
            return SlotOutcome(
                slot_id=slot.slot_id, action="cooldown",
                candidate=candidate, error=error_text,
            )

        if exc.status_code == 429:
            retry_after = exc.retry_after or _COOLDOWN_429
            # Workstream C2.2: reset before cooldown (same rationale as above).
            slot.reset()
            slot.enter_cooldown(retry_after, f"rate limited (retry_after={retry_after})")
            candidate.lifecycle_status = "simulation_deferred_rate_limit"
            self._emit_event(
                "scheduler_rate_limit",
                f"Slot {slot.slot_id}: 429 rate limited, cooldown {retry_after}s",
                candidate.alpha_id,
                cycle,
                level="WARN",
            )
            return SlotOutcome(
                slot_id=slot.slot_id, action="cooldown",
                candidate=candidate, error=error_text,
            )

        # Server error — enter cooldown, don't halt pipeline
        # Workstream C2.3: reset before cooldown (same rationale as above).
        slot.reset()
        slot.enter_cooldown(_COOLDOWN_SERVER_ERROR, f"server error: {error_text[:120]}")
        candidate.lifecycle_status = "simulation_deferred_server_error"
        self._emit_event(
            "scheduler_submit_error",
            f"Slot {slot.slot_id}: submit error {exc.status_code}, cooldown {_COOLDOWN_SERVER_ERROR}s",
            candidate.alpha_id,
            cycle,
            level="WARN",
        )
        return SlotOutcome(
            slot_id=slot.slot_id, action="cooldown",
            candidate=candidate, error=error_text,
        )

    def _handle_poll_error(
        self, slot, exc: BrainAPIError, cycle: int
    ) -> SlotOutcome | None:
        error_text = redact_error_message(exc)
        slot.last_error = error_text

        if exc.status_code == 429:
            retry_after = exc.retry_after or _COOLDOWN_429
            # Workstream C2.2: save candidate ref, reset, THEN enter cooldown.
            candidate = slot.candidate
            slot.reset()
            slot.enter_cooldown(retry_after, f"poll rate limited (retry_after={retry_after})")
            if candidate:
                candidate.lifecycle_status = "simulation_poll_deferred_rate_limit"
            self._emit_event(
                "scheduler_poll_rate_limit",
                f"Slot {slot.slot_id}: poll 429, cooldown {retry_after}s",
                candidate.alpha_id if candidate else "",
                cycle,
                level="WARN",
            )
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

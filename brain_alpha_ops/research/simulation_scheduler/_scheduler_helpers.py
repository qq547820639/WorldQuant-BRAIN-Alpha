"""Helper methods mixin for ``ThreeSlotScheduler``."""

from __future__ import annotations

import logging
import time
from typing import Any

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.simulation_scheduler._types import (
    SlotOutcome,
    SlotState,
)

logger = logging.getLogger("brain_alpha_ops.research.simulation_scheduler")


class _SchedulerHelpersMixin:
    """Slot management, candidate selection, and event helpers."""

    def active_count(self) -> int:
        return sum(
            1 for s in self._slots
            if s.state in (SlotState.SUBMITTING, SlotState.POLLING)
        )

    def available_slots(self) -> list:
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

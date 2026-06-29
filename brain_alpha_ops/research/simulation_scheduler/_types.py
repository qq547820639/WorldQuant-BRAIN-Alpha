"""Slot state enum, slot dataclasses, and scheduler constants."""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.models import Candidate

logger = logging.getLogger("brain_alpha_ops.research.simulation_scheduler")


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
        # Reset error tracking so a reused slot starts clean instead of
        # inheriting error_count/last_error from the previous occupant.
        self.error_count = 0
        self.last_error = ""

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

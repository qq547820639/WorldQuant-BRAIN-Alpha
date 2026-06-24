"""Candidate Alpha lifecycle state machine.

Tracks the full lifecycle of a candidate Alpha through pipeline stages:
  created → local_scored → gate_checked → queued_for_simulation → simulating
  → sim_passed / sim_failed → ready_for_submit → archived

Each state transition is logged to the audit trail and validated against
a legal-transition graph. Thread-safe via a lock on all mutations.
"""
from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class LifecycleState(enum.Enum):
    CREATED = "created"
    LOCAL_SCORED = "local_scored"
    GATE_CHECKED = "gate_checked"
    QUEUED_FOR_SIMULATION = "queued_for_simulation"
    SIMULATING = "simulating"
    SIM_PASSED = "sim_passed"
    SIM_FAILED = "sim_failed"
    READY_FOR_SUBMIT = "ready_for_submit"
    ARCHIVED = "archived"


# Legal transitions: from_state → {allowed to_states}
_LEGAL_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.CREATED: frozenset({LifecycleState.LOCAL_SCORED}),
    LifecycleState.LOCAL_SCORED: frozenset({LifecycleState.GATE_CHECKED}),
    LifecycleState.GATE_CHECKED: frozenset({
        LifecycleState.QUEUED_FOR_SIMULATION,
        LifecycleState.ARCHIVED,
    }),
    LifecycleState.QUEUED_FOR_SIMULATION: frozenset({LifecycleState.SIMULATING}),
    LifecycleState.SIMULATING: frozenset({
        LifecycleState.SIM_PASSED,
        LifecycleState.SIM_FAILED,
    }),
    LifecycleState.SIM_PASSED: frozenset({LifecycleState.READY_FOR_SUBMIT}),
    LifecycleState.SIM_FAILED: frozenset({
        LifecycleState.READY_FOR_SUBMIT,
        LifecycleState.ARCHIVED,
    }),
    LifecycleState.READY_FOR_SUBMIT: frozenset({LifecycleState.ARCHIVED}),
    LifecycleState.ARCHIVED: frozenset(),
}


@dataclass
class TransitionRecord:
    alpha_id: str
    from_state: str
    to_state: str
    reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha_id": self.alpha_id,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class CandidateLifecycle:
    """Thread-safe lifecycle state machine for a single candidate Alpha.

    Usage:
        lc = CandidateLifecycle("alpha_123")
        lc.transition(LifecycleState.LOCAL_SCORED, reason="local scoring done")
        assert lc.state == LifecycleState.LOCAL_SCORED
    """

    def __init__(self, alpha_id: str, initial_state: LifecycleState = LifecycleState.CREATED):
        self.alpha_id = alpha_id
        self._state = initial_state
        self._lock = threading.Lock()
        self._audit_trail: list[TransitionRecord] = []

    @property
    def state(self) -> LifecycleState:
        with self._lock:
            return self._state

    def transition(self, target: LifecycleState, *, reason: str = "") -> bool:
        """Attempt a state transition. Returns True if successful."""
        with self._lock:
            allowed = _LEGAL_TRANSITIONS.get(self._state, frozenset())
            if target not in allowed:
                logger.warning(
                    "Invalid lifecycle transition for %s: %s → %s",
                    self.alpha_id, self._state.value, target.value,
                )
                return False

            record = TransitionRecord(
                alpha_id=self.alpha_id,
                from_state=self._state.value,
                to_state=target.value,
                reason=reason,
            )
            self._audit_trail.append(record)
            self._state = target
            logger.info(
                "Lifecycle %s: %s → %s (%s)",
                self.alpha_id, record.from_state, record.to_state, reason,
            )
            return True

    def audit_trail(self) -> list[dict[str, Any]]:
        """Return a copy of the full audit trail."""
        with self._lock:
            return [r.to_dict() for r in self._audit_trail]

    def is_terminal(self) -> bool:
        """Check if the candidate is in a terminal state (archived)."""
        return self.state == LifecycleState.ARCHIVED

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha_id": self.alpha_id,
            "state": self.state.value,
            "audit_trail": self.audit_trail(),
        }


class LifecycleManager:
    """Manages lifecycle state machines for multiple candidates.

    Integration point with the pipeline: the pipeline creates a
    LifecycleManager, registers candidates, and calls transition()
    as the candidate progresses through scoring, simulation, and submission.
    """

    def __init__(self) -> None:
        self._lifecycles: dict[str, CandidateLifecycle] = {}
        self._lock = threading.Lock()

    def register(self, alpha_id: str, initial_state: LifecycleState = LifecycleState.CREATED) -> CandidateLifecycle:
        """Register a new candidate and return its lifecycle controller."""
        with self._lock:
            if alpha_id in self._lifecycles:
                return self._lifecycles[alpha_id]
            lc = CandidateLifecycle(alpha_id, initial_state)
            self._lifecycles[alpha_id] = lc
            return lc

    def get(self, alpha_id: str) -> CandidateLifecycle | None:
        with self._lock:
            return self._lifecycles.get(alpha_id)

    def transition(self, alpha_id: str, target: LifecycleState, *, reason: str = "") -> bool:
        """Convenience: look up lifecycle and transition."""
        lc = self.get(alpha_id)
        if lc is None:
            logger.warning("No lifecycle registered for %s", alpha_id)
            return False
        return lc.transition(target, reason=reason)

    def candidates_in_state(self, state: LifecycleState) -> list[str]:
        """Return alpha_ids of all candidates currently in the given state."""
        with self._lock:
            return [
                alpha_id
                for alpha_id, lc in self._lifecycles.items()
                if lc.state == state
            ]

    def summary(self) -> dict[str, Any]:
        """Aggregate counts per lifecycle state."""
        counts: dict[str, int] = {}
        for s in LifecycleState:
            counts[s.value] = 0
        with self._lock:
            for lc in self._lifecycles.values():
                counts[lc.state.value] += 1
        return counts

    def all_lifecycles(self) -> dict[str, CandidateLifecycle]:
        with self._lock:
            return dict(self._lifecycles)

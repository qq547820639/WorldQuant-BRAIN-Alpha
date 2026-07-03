"""Candidate Alpha lifecycle state machine (Workstream B).

Spec-defined 11-state lifecycle with a legal-transition graph, in-memory
``TransitionRecord`` audit trail, and best-effort JSONL audit write.
"""
from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from brain_alpha_ops.redaction import redact_error_message, redact_text

if TYPE_CHECKING:
    from brain_alpha_ops.models import Candidate

logger = logging.getLogger(__name__)


class LifecycleState(enum.Enum):
    """Canonical 11-state lifecycle per Workstream B spec.

    Legacy uppercase names (CREATED, LOCAL_SCORED, …) are aliases that
    resolve to the canonical lowercase members.
    """

    # Canonical spec states (11)
    draft = "draft"
    locally_scored = "locally_scored"
    gate_rejected = "gate_rejected"
    queued_for_simulation = "queued_for_simulation"
    simulating = "simulating"
    simulation_failed = "simulation_failed"
    simulation_passed = "simulation_passed"
    needs_optimization = "needs_optimization"
    ready_for_review = "ready_for_review"
    submitted = "submitted"
    archived = "archived"
    # Backward-compat aliases (legacy uppercase names → canonical members).
    CREATED = "draft"
    LOCAL_SCORED = "locally_scored"
    GATE_CHECKED = "locally_scored"
    QUEUED_FOR_SIMULATION = "queued_for_simulation"
    SIMULATING = "simulating"
    SIM_PASSED = "simulation_passed"
    SIM_FAILED = "simulation_failed"
    READY_FOR_SUBMIT = "ready_for_review"
    ARCHIVED = "archived"


class IllegalTransitionError(ValueError):
    """Raised when a state transition violates the legal-transition graph."""


# Legal transitions per Workstream B spec: from_state → {allowed to_states}.
# Self-transitions allow deferred/blocked sub-statuses without violating the graph.
_LEGAL_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.draft: frozenset({
        LifecycleState.locally_scored, LifecycleState.gate_rejected,
        LifecycleState.archived,
    }),
    LifecycleState.locally_scored: frozenset({
        LifecycleState.gate_rejected, LifecycleState.queued_for_simulation,
        LifecycleState.needs_optimization, LifecycleState.archived,
    }),
    LifecycleState.gate_rejected: frozenset({
        LifecycleState.needs_optimization, LifecycleState.archived,
    }),
    LifecycleState.needs_optimization: frozenset({LifecycleState.locally_scored}),
    LifecycleState.queued_for_simulation: frozenset({
        LifecycleState.simulating, LifecycleState.gate_rejected,
        LifecycleState.queued_for_simulation,
    }),
    LifecycleState.simulating: frozenset({
        LifecycleState.simulation_passed, LifecycleState.simulation_failed,
        LifecycleState.simulating,
    }),
    LifecycleState.simulation_failed: frozenset({
        LifecycleState.needs_optimization, LifecycleState.archived,
        LifecycleState.queued_for_simulation,
    }),
    LifecycleState.simulation_passed: frozenset({
        LifecycleState.ready_for_review, LifecycleState.submitted,
    }),
    LifecycleState.ready_for_review: frozenset({
        LifecycleState.submitted, LifecycleState.archived,
        LifecycleState.ready_for_review,
    }),
    LifecycleState.submitted: frozenset({LifecycleState.archived}),
    LifecycleState.archived: frozenset(),
}


# Legacy pipeline status strings → canonical LifecycleState. Used by
# ``get_lifecycle`` to seed state from ``candidate.lifecycle_status``.
_LEGACY_STATUS_MAP: dict[str, LifecycleState] = {
    # draft
    "created": LifecycleState.draft, "draft": LifecycleState.draft,
    # locally_scored
    "local_scored": LifecycleState.locally_scored, "locally_scored": LifecycleState.locally_scored,
    "candidate_pool_retained": LifecycleState.locally_scored,
    # gate_rejected
    "local_prefilter_rejected": LifecycleState.gate_rejected,
    "local_standard_rejected": LifecycleState.gate_rejected,
    "duplicate_expression_skipped": LifecycleState.gate_rejected,
    "previously_rejected_expression_skipped": LifecycleState.gate_rejected,
    "official_standard_rejected": LifecycleState.gate_rejected, "gate_rejected": LifecycleState.gate_rejected,
    # queued_for_simulation
    "queued_for_simulation": LifecycleState.queued_for_simulation,
    "backtest_slot_selected": LifecycleState.queued_for_simulation,
    "backtest_batch_selected": LifecycleState.queued_for_simulation,
    "simulation_deferred_concurrency_limit": LifecycleState.queued_for_simulation,
    "simulation_deferred_rate_limit": LifecycleState.queued_for_simulation,
    "simulation_deferred_server_error": LifecycleState.queued_for_simulation,
    # simulating
    "simulating": LifecycleState.simulating, "simulation_submitted": LifecycleState.simulating,
    "simulation_running": LifecycleState.simulating,
    "simulation_poll_deferred_rate_limit": LifecycleState.simulating,
    "simulation_result_deferred_rate_limit": LifecycleState.simulating,
    "simulation_poll_deferred_unknown": LifecycleState.simulating,
    # simulation_failed
    "simulation_failed": LifecycleState.simulation_failed, "simulation_poll_failed": LifecycleState.simulation_failed,
    "simulation_result_failed": LifecycleState.simulation_failed, "simulation_request_failed": LifecycleState.simulation_failed,
    # simulation_passed
    "simulation_passed": LifecycleState.simulation_passed, "official_simulated": LifecycleState.simulation_passed,
    # needs_optimization
    "needs_optimization": LifecycleState.needs_optimization,
    # ready_for_review
    "ready_for_review": LifecycleState.ready_for_review, "submission_ready": LifecycleState.ready_for_review,
    "auto_submit_cross_review_blocked": LifecycleState.ready_for_review,
    "auto_submit_readiness_blocked": LifecycleState.ready_for_review,
    # submitted / archived
    "submitted": LifecycleState.submitted, "archived": LifecycleState.archived,
    "candidate_pool_pruned": LifecycleState.archived,
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
    """Thread-safe lifecycle state machine for a single candidate Alpha."""

    def __init__(self, alpha_id: str, initial_state: LifecycleState = LifecycleState.draft):
        self.alpha_id = alpha_id
        self._state = initial_state
        self._lock = threading.Lock()
        self._audit_trail: list[TransitionRecord] = []

    @property
    def state(self) -> LifecycleState:
        with self._lock:
            return self._state

    def transition(
        self, target: LifecycleState, *,
        reason: str = "", context: dict[str, Any] | None = None,
    ) -> bool:
        """Attempt a state transition. Returns True if successful (False on illegal)."""
        with self._lock:
            allowed = _LEGAL_TRANSITIONS.get(self._state, frozenset())
            if target not in allowed:
                logger.warning(
                    "Invalid lifecycle transition for %s: %s → %s",
                    redact_text(self.alpha_id), self._state.value, target.value,
                )
                return False
            from_state = self._state
            record = TransitionRecord(
                alpha_id=self.alpha_id,
                from_state=from_state.value, to_state=target.value, reason=reason,
            )
            self._audit_trail.append(record)
            self._state = target
            logger.info(
                "Lifecycle %s: %s → %s (%s)",
                redact_text(self.alpha_id), record.from_state, record.to_state, reason,
            )
        _write_lifecycle_audit(self.alpha_id, from_state.value, target.value, reason, context)
        return True

    def audit_trail(self) -> list[dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._audit_trail]

    def force_transition(self, target: LifecycleState, *,
                         reason: str = "", context: dict[str, Any] | None = None) -> None:
        """Force a transition without legal-graph validation (backward compat)."""
        with self._lock:
            from_state = self._state
            self._audit_trail.append(TransitionRecord(
                alpha_id=self.alpha_id,
                from_state=from_state.value, to_state=target.value, reason=reason,
            ))
            self._state = target
        _write_lifecycle_audit(self.alpha_id, from_state.value, target.value, reason, context)

    def is_terminal(self) -> bool:
        return self.state == LifecycleState.archived

    def to_dict(self) -> dict[str, Any]:
        return {"alpha_id": self.alpha_id, "state": self.state.value,
                "audit_trail": self.audit_trail()}


class LifecycleManager:
    """Manages lifecycle state machines for multiple candidates.

    ``transition`` is overloaded: pass two ``LifecycleState`` args for
    stateless validation (raises on illegal), or ``alpha_id`` + target
    for the registered-candidate form.
    """

    def __init__(self) -> None:
        self._lifecycles: dict[str, CandidateLifecycle] = {}
        self._lock = threading.Lock()

    def register(self, alpha_id: str, initial_state: LifecycleState = LifecycleState.draft) -> CandidateLifecycle:
        with self._lock:
            if alpha_id in self._lifecycles:
                return self._lifecycles[alpha_id]
            lc = CandidateLifecycle(alpha_id, initial_state)
            self._lifecycles[alpha_id] = lc
            return lc

    def get(self, alpha_id: str) -> CandidateLifecycle | None:
        with self._lock:
            return self._lifecycles.get(alpha_id)

    def transition(self, alpha_id_or_from: "str | LifecycleState",
                   target: LifecycleState | None = None, *, reason: str = "") -> bool:
        """Stateless validator (raises on illegal) OR registered-candidate transition."""
        if isinstance(alpha_id_or_from, LifecycleState):
            from_state = alpha_id_or_from
            if not isinstance(target, LifecycleState):
                raise TypeError("transition(state, state) requires two LifecycleState args")
            if target not in _LEGAL_TRANSITIONS.get(from_state, frozenset()):
                raise IllegalTransitionError(
                    f"Illegal lifecycle transition: {from_state.value} → {target.value}"
                )
            return True
        alpha_id = alpha_id_or_from
        if target is None:
            raise TypeError("transition(alpha_id, target) requires a target state")
        lc = self.get(alpha_id)
        if lc is None:
            logger.warning("No lifecycle registered for %s", redact_text(alpha_id))
            return False
        return lc.transition(target, reason=reason)

    def candidates_in_state(self, state: LifecycleState) -> list[str]:
        with self._lock:
            return [aid for aid, lc in self._lifecycles.items() if lc.state == state]

    def summary(self) -> dict[str, Any]:
        """Aggregate counts per canonical lifecycle state (aliases deduped)."""
        counts: dict[str, int] = {}
        seen: set[int] = set()
        with self._lock:
            for lc in self._lifecycles.values():
                key = id(lc.state)
                if key in seen:
                    continue
                seen.add(key)
                counts[lc.state.value] = counts.get(lc.state.value, 0) + 1
        for s in LifecycleState:
            if s is not LifecycleState.__members__.get(s.name):
                continue
            counts.setdefault(s.value, 0)
        return counts

    def all_lifecycles(self) -> dict[str, CandidateLifecycle]:
        with self._lock:
            return dict(self._lifecycles)


def validate_transition(from_state: LifecycleState, to_state: LifecycleState) -> bool:
    """Stateless transition validator. Raises ``IllegalTransitionError`` if illegal."""
    if to_state not in _LEGAL_TRANSITIONS.get(from_state, frozenset()):
        raise IllegalTransitionError(
            f"Illegal lifecycle transition: {from_state.value} → {to_state.value}"
        )
    return True


def get_lifecycle(candidate: "Candidate") -> CandidateLifecycle:
    """Lazily attach a CandidateLifecycle to a candidate.

    Initializes the lifecycle state from the candidate's current
    ``lifecycle_status`` string，经 ``LifecycleStatusNormalizer`` 统一映射到规范
    ``LifecycleState``（Task 6.1：遗留状态映射清理）。
    """
    # 延迟导入避免与 lifecycle_status_normalizer 形成循环导入。
    from brain_alpha_ops.lifecycle_status_normalizer import normalizer
    lc = getattr(candidate, "_lifecycle", None)
    if lc is None or not isinstance(lc, CandidateLifecycle):
        current = getattr(candidate, "lifecycle_status", "") or "created"
        initial = normalizer.normalize(current)
        lc = CandidateLifecycle(getattr(candidate, "alpha_id", "") or "", initial_state=initial)
        try:
            setattr(candidate, "_lifecycle", lc)
        except (AttributeError, TypeError):
            pass
    return lc


def transition(candidate: "Candidate", target: LifecycleState, *,
               reason: str = "", legacy_status: str | None = None,
               context: dict[str, Any] | None = None) -> bool:
    """Validate candidate transition via state machine, then mutate.

    Falls back to ``force_transition`` on illegal transitions (isolated tests).
    Sets ``candidate.lifecycle_status`` to ``legacy_status`` if given."""
    lc = get_lifecycle(candidate)
    ok = lc.transition(target, reason=reason, context=context)
    if not ok:
        lc.force_transition(target, reason=reason, context=context)
    new_status = legacy_status if legacy_status is not None else target.value
    try:
        candidate.lifecycle_status = new_status
    except (AttributeError, TypeError):
        pass
    return True


def _write_lifecycle_audit(alpha_id: str, from_state: str, to_state: str,
                           reason: str, context: dict[str, Any] | None) -> None:
    """Best-effort JSONL audit write for a lifecycle transition."""
    try:
        from brain_alpha_ops.audit_trail.lifecycle_writer import record_lifecycle_transition
        record_lifecycle_transition(
            alpha_id=alpha_id, from_state=from_state, to_state=to_state,
            reason=reason, trigger_rule=(context or {}).get("trigger_rule", ""),
            context=context,
        )
    except Exception as exc:  # noqa: BLE001 — audit must never break the pipeline
        logger.debug("lifecycle audit write skipped: %s", redact_error_message(exc))

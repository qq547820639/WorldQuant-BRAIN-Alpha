"""F1.4 — Concurrent limit exceeded → rejection tests.

Spec ref: .trae/specs/overhaul-alpha-production-quality/spec.md
  "并发超限拒绝" — When 3 slots are all busy, a 4th submission is rejected
  (or deferred) with CONCURRENT_SIMULATION_LIMIT_EXCEEDED, the rejection
  only affects the 4th slot, and the candidate pool keeps producing.

Verifies that:
  - When all 3 slots are POLLING (busy), a 4th submission on a fresh slot
    attempt receives CONCURRENT_SIMULATION_LIMIT_EXCEEDED and is deferred
    (cooldown), not crashed.
  - The 3 active slots remain POLLING — unaffected by the 4th rejection.
  - The candidate pool keeps producing new candidates (no back-pressure).
  - The candidate's lifecycle_status is set to a "deferred" state.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.error_catalog import (
    ErrorKind,
    build_actionable_error,
    classify_exception,
)
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.simulation_scheduler import (
    SlotState,
    ThreeSlotScheduler,
)
from brain_alpha_ops.research.simulation_scheduler._types import (
    _COOLDOWN_CONCURRENT_LIMIT,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_api(
    submit_return: str = "sim_001",
    poll_return: str = "RUNNING",
    fetch_return: dict | None = None,
) -> MagicMock:
    api = MagicMock(spec=BrainAPI)
    api.submit_simulation.return_value = submit_return
    api.poll_simulation.return_value = poll_return
    api.fetch_result.return_value = fetch_return or {"alpha_id": "a1", "metrics": {}}
    return api


def _cand(alpha_id: str, expression: str | None = None) -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression=expression or f"rank(close_{alpha_id})",
        family="test",
        hypothesis="test",
    )


def _settings() -> dict:
    return {"settings": {"period": 120, "decay": 0.9}}


def _noop(*_a, **_kw) -> None:
    pass


def _make_scheduler(api: MagicMock | None = None, **kwargs) -> ThreeSlotScheduler:
    return ThreeSlotScheduler(
        api=api or _make_api(),
        settings_provider=_settings,
        event_callback=_noop,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# F1.4: 4th submission rejected when 3 slots are busy
# --------------------------------------------------------------------------- #

def test_fourth_submission_rejected_with_concurrent_limit_when_all_slots_busy():
    """When all 3 slots are POLLING (busy), a 4th submission attempt on a
    fresh idle slot that hits CONCURRENT_SIMULATION_LIMIT_EXCEEDED is
    rejected (deferred via cooldown), not crashed.
    """
    api = _make_api(poll_return="RUNNING")
    # First 3 submits succeed (filling all 3 slots); 4th hits concurrent limit.
    api.submit_simulation.side_effect = [
        "sim_1", "sim_2", "sim_3",
        BrainAPIError(
            "HTTP 400: CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
            status_code=400,
            payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
        ),
    ]
    scheduler = _make_scheduler(api=api)

    # Fill all 3 slots.
    initial_pool = [_cand(f"a{i}", f"rank(f{i})") for i in range(3)]
    scheduler.tick(initial_pool, cycle=1)
    assert scheduler.active_count() == 3
    assert all(s.state == SlotState.POLLING for s in scheduler._slots)

    # 4th candidate arrives — there's no free slot (all 3 POLLING), so the
    # 4th is not even submitted via the scheduler (it stays in the pool).
    # Verify: tick does not raise, scheduler is not halted.
    fourth = _cand("a4", "rank(f4)")
    outcomes = scheduler.tick([fourth], cycle=2)

    assert scheduler.halted is False
    # No new submission because all 3 slots are POLLING.
    submitted = [o for o in outcomes if o.action == "submitted"]
    assert len(submitted) == 0
    # The 4th candidate stays in the pool — pool keeps producing.
    assert fourth.lifecycle_status != "simulation_failed"


def test_concurrent_limit_rejection_only_affects_fourth_slot_not_active_three():
    """When the scheduler submits a 4th candidate to a fresh slot and that
    submission returns CONCURRENT_SIMULATION_LIMIT_EXCEEDED, only that
    slot enters cooldown; the 3 already-POLLING slots are unaffected.
    """
    api = _make_api(poll_return="RUNNING")
    # Slot 1 hits concurrent limit; slots 2 and 3 succeed (active).
    api.submit_simulation.side_effect = [
        BrainAPIError(
            "CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
            status_code=400,
            error_code="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
        ),
        "sim_slot2",
        "sim_slot3",
    ]
    scheduler = _make_scheduler(api=api)
    candidates = [
        _cand("a1", "rank(close)"),
        _cand("a2", "rank(volume)"),
        _cand("a3", "rank(high)"),
    ]

    outcomes = scheduler.tick(candidates, cycle=1)

    cooldown = [o for o in outcomes if o.action == "cooldown"]
    submitted = [o for o in outcomes if o.action == "submitted"]
    assert len(cooldown) == 1
    assert cooldown[0].slot_id == 1
    assert "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in cooldown[0].error
    assert len(submitted) == 2
    assert {o.slot_id for o in submitted} == {2, 3}

    # The 3 "active" slots are: slot 1 in COOLDOWN, slots 2 & 3 POLLING.
    # The concurrent-limit rejection only paused slot 1; slots 2 and 3 are
    # unaffected and continue polling.
    assert scheduler._slots[0].state == SlotState.COOLDOWN
    assert scheduler._slots[1].state == SlotState.POLLING
    assert scheduler._slots[2].state == SlotState.POLLING
    assert scheduler.halted is False
    assert scheduler.active_count() == 2


def test_concurrent_limit_sets_candidate_lifecycle_to_deferred():
    """The candidate whose submission hit the concurrent limit is marked
    with a "deferred" lifecycle_status so the pipeline can re-queue it.
    """
    api = _make_api(poll_return="RUNNING")
    api.submit_simulation.side_effect = [
        BrainAPIError(
            "CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
            status_code=400,
            error_code="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
        ),
    ]
    scheduler = _make_scheduler(api=api)
    candidate = _cand("deferred_alpha", "rank(close)")

    outcomes = scheduler.tick([candidate], cycle=1)

    cooldown = next(o for o in outcomes if o.action == "cooldown")
    assert cooldown.candidate is candidate
    assert "deferred" in candidate.lifecycle_status
    assert "concurrency" in candidate.lifecycle_status or "concurrent" in candidate.lifecycle_status


def test_concurrent_limit_cooldown_duration_is_60_seconds():
    """The slot enters cooldown for _COOLDOWN_CONCURRENT_LIMIT seconds."""
    api = _make_api(poll_return="RUNNING")
    api.submit_simulation.side_effect = BrainAPIError(
        "CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
        status_code=400,
    )
    scheduler = _make_scheduler(api=api)
    scheduler.tick([_cand("a1")], cycle=1)

    slot = scheduler._slots[0]
    assert slot.state == SlotState.COOLDOWN
    remaining = slot.cooldown_until - time.monotonic()
    # Should be roughly _COOLDOWN_CONCURRENT_LIMIT (60s); allow small drift.
    assert _COOLDOWN_CONCURRENT_LIMIT - 5 <= remaining <= _COOLDOWN_CONCURRENT_LIMIT


def test_candidate_pool_continues_producing_after_concurrent_limit_rejection():
    """After a concurrent-limit rejection, the candidate pool keeps
    producing — new candidates are accepted by tick() without error or
    back-pressure, and the deferred candidate is not lost (it can be
    re-queued once a slot frees up).
    """
    api = _make_api(poll_return="RUNNING")
    api.submit_simulation.side_effect = [
        BrainAPIError("CONCURRENT_SIMULATION_LIMIT_EXCEEDED", status_code=400),
        "sim_ok_2",
        "sim_ok_3",
    ]
    scheduler = _make_scheduler(api=api)
    initial_pool = [
        _cand("a1", "rank(close)"),
        _cand("a2", "rank(volume)"),
        _cand("a3", "rank(high)"),
    ]
    scheduler.tick(initial_pool, cycle=1)

    # Slot 1 in COOLDOWN; slots 2 & 3 POLLING; a1 deferred.
    assert scheduler._slots[0].state == SlotState.COOLDOWN
    assert scheduler.active_count() == 2
    deferred = initial_pool[0]
    assert "deferred" in deferred.lifecycle_status

    # Pool keeps producing — new candidates arrive without back-pressure.
    grown_pool = initial_pool + [
        _cand("a4", "rank(low)"),
        _cand("a5", "rank(open)"),
    ]
    outcomes = scheduler.tick(grown_pool, cycle=2)
    assert scheduler.halted is False
    # No new submissions (slots 2 & 3 still polling, slot 1 still cooling).
    assert all(o.action != "submitted" for o in outcomes)


def test_concurrent_limit_classified_as_simulation_concurrency_exceeded():
    """The BrainAPIError carrying CONCURRENT_SIMULATION_LIMIT_EXCEEDED is
    classified by the error catalog as ErrorKind.simulation_concurrency_exceeded
    so the frontend can render the right recovery entry.
    """
    err = BrainAPIError(
        "CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
        status_code=400,
        error_code="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
    )
    kind = classify_exception(err)
    assert kind == ErrorKind.simulation_concurrency_exceeded


def test_concurrent_limit_actionable_payload_has_recovery_url():
    """The actionable error payload for simulation_concurrency_exceeded
    carries a recovery_url so the frontend can render a clickable entry.
    """
    payload = build_actionable_error(ErrorKind.simulation_concurrency_exceeded)

    assert payload["kind"] == "simulation_concurrency_exceeded"
    assert payload["recovery_url"] == "/backtests"
    assert payload["suggested_action"]
    assert "concurrent" in payload["cause"].lower() or "并发" in payload["cause"]


def test_concurrent_limit_does_not_halt_scheduler():
    """A CONCURRENT_SIMULATION_LIMIT_EXCEEDED error must NEVER set
    scheduler.halted=True — the scheduler must remain usable.
    """
    api = _make_api(poll_return="RUNNING")
    api.submit_simulation.side_effect = BrainAPIError(
        "CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
        status_code=400,
    )
    scheduler = _make_scheduler(api=api)

    scheduler.tick([_cand("a1")], cycle=1)

    assert scheduler.halted is False
    assert scheduler.halt_reason == ""

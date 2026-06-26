"""Workstream C2 — hardened slot-level fault tolerance tests for ThreeSlotScheduler.

Covers C2.1 (CONCURRENT_SIMULATION_LIMIT_EXCEEDED isolation), C2.2 (429
cooldown isolation), C2.3 (network error isolation), C2.4 (cancel /
timeout / unknown-status self-heal / cooldown recovery), C1.1
(consistency guard), and the C3 decoupling regression.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.simulation_scheduler import (
    SlotState,
    ThreeSlotScheduler,
    assert_scheduler_consistency,
)
from brain_alpha_ops.research.simulation_scheduler._consistency import (
    OFFICIAL_SIMULATION_SLOT_LIMIT,
    SchedulerInconsistencyError,
)


def _make_api(submit_return="sim_001", poll_return="RUNNING", fetch_return=None):
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


def test_concurrent_limit_only_pauses_affected_slot_not_whole_chain():
    """C2.1: a CONCURRENT_SIMULATION_LIMIT_EXCEEDED submit error must
    enter per-slot cooldown only; other slots and the candidate pool
    are unaffected.
    """
    api = _make_api()
    api.submit_simulation.side_effect = [
        BrainAPIError(
            "HTTP 400: CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
            status_code=400,
            payload={"detail": "CONCURRENT_SIMULATION_LIMIT_EXCEEDED"},
        ),
        "sim_slot2",
        "sim_slot3",
    ]
    scheduler = _make_scheduler(api=api)
    candidates = [_cand("a1", "rank(close)"), _cand("a2", "rank(volume)"), _cand("a3", "rank(high)")]

    outcomes = scheduler.tick(candidates, cycle=1)

    cooldown = [o for o in outcomes if o.action == "cooldown"]
    submitted = [o for o in outcomes if o.action == "submitted"]
    assert len(cooldown) == 1 and cooldown[0].slot_id == 1
    assert len(submitted) == 2 and {o.slot_id for o in submitted} == {2, 3}
    assert scheduler.halted is False
    assert scheduler.active_count() == 2


def test_concurrent_limit_does_not_block_candidate_pool_progress():
    """C2.1: while slot 1 is in COOLDOWN, slots 2 and 3 continue to
    operate; the candidate pool is not locked — new candidates are
    accepted by tick() without error or halt.
    """
    api = _make_api()
    api.submit_simulation.side_effect = [
        BrainAPIError("CONCURRENT_SIMULATION_LIMIT_EXCEEDED", status_code=400),
        "sim_ok_2",
        "sim_ok_3",
    ]
    scheduler = _make_scheduler(api=api)
    pool = [_cand("a1", "rank(close)"), _cand("a2", "rank(vol)"), _cand("a3", "rank(high)")]
    scheduler.tick(pool, cycle=1)

    # Slot 1 in COOLDOWN (60s); slots 2 and 3 POLLING.
    assert scheduler._slots[0].state == SlotState.COOLDOWN
    assert scheduler._slots[1].state == SlotState.POLLING
    assert scheduler._slots[2].state == SlotState.POLLING
    assert scheduler.halted is False
    assert scheduler.active_count() == 2

    # Pool keeps producing — new candidates accepted without error/back-pressure.
    grown = pool + [_cand("a4", "rank(low)")]
    scheduler.tick(grown, cycle=2)
    assert scheduler.halted is False
    assert scheduler._slots[0].state == SlotState.COOLDOWN  # still cooling down


def test_rate_limit_429_only_enters_slot_cooldown():
    """C2.2: a 429 submit error enters per-slot cooldown with the
    retry_after window; other slots continue to operate.
    """
    api = _make_api()
    api.submit_simulation.side_effect = [
        BrainAPIError("HTTP 429", status_code=429, retry_after=2.0),
        "sim_ok_2",
        "sim_ok_3",
    ]
    scheduler = _make_scheduler(api=api)
    candidates = [_cand("a1", "rank(close)"), _cand("a2", "rank(volume)"), _cand("a3", "rank(high)")]

    outcomes = scheduler.tick(candidates, cycle=1)

    rate_limited = [o for o in outcomes if o.action == "cooldown"]
    submitted = [o for o in outcomes if o.action == "submitted"]
    assert len(rate_limited) == 1 and rate_limited[0].slot_id == 1
    assert scheduler._slots[0].cooldown_until > time.monotonic()
    assert "rate limited" in scheduler._slots[0].cooldown_reason
    assert len(submitted) == 2
    assert scheduler.halted is False
    assert scheduler.active_count() == 2


def test_rate_limit_does_not_consume_candidates_from_pool():
    """C2.2: a 429-cooldown slot does not lock the candidate — the pool
    keeps producing new candidates in the meantime.
    """
    api = _make_api()
    api.submit_simulation.side_effect = [
        BrainAPIError("HTTP 429", status_code=429, retry_after=60.0),
    ] + ["sim_ok"] * 5
    scheduler = _make_scheduler(api=api)
    pool = [_cand("a1", "rank(close)"), _cand("a2", "rank(vol)")]
    scheduler.tick(pool, cycle=1)
    assert scheduler._slots[0].state == SlotState.COOLDOWN

    pool.append(_cand("a3", "rank(high)"))
    scheduler.tick(pool, cycle=2)
    assert scheduler.halted is False
    assert scheduler._slots[0].state == SlotState.COOLDOWN  # still cooling down


def test_network_error_only_cooldowns_affected_slot():
    """C2.3: a 5xx submit error enters per-slot cooldown; the candidate
    stays retryable and other slots continue.
    """
    api = _make_api()
    api.submit_simulation.side_effect = [
        BrainAPIError("HTTP 503 service unavailable", status_code=503),
        "sim_ok_2",
        "sim_ok_3",
    ]
    scheduler = _make_scheduler(api=api)
    candidates = [_cand("a1", "rank(close)"), _cand("a2", "rank(volume)"), _cand("a3", "rank(high)")]

    outcomes = scheduler.tick(candidates, cycle=1)

    cooldown = [o for o in outcomes if o.action == "cooldown"]
    submitted = [o for o in outcomes if o.action == "submitted"]
    assert len(cooldown) == 1 and cooldown[0].slot_id == 1
    assert "server error" in scheduler._slots[0].cooldown_reason
    assert len(submitted) == 2
    assert scheduler.halted is False


def test_poll_network_error_keeps_slot_polling_without_halt():
    """C2.3: a non-429 poll error is treated as transient — the slot
    stays in POLLING and schedules a backoff retry; the scheduler is
    not halted and other slots are unaffected.
    """
    api = _make_api(poll_return="RUNNING")
    scheduler = _make_scheduler(api=api)
    scheduler.tick([_cand("a1", "rank(close)")], cycle=1)
    assert scheduler._slots[0].state == SlotState.POLLING

    api.poll_simulation.side_effect = BrainAPIError("HTTP 500 poll", status_code=500)
    outcomes = scheduler.tick([], cycle=2)
    assert outcomes == []
    assert scheduler._slots[0].state == SlotState.POLLING
    assert scheduler.halted is False
    assert scheduler._slots[0].candidate.submission["next_poll_at"] > time.monotonic()


def test_task_cancellation_stops_tick_loop_without_halt_flag():
    """C2.4: ``stop_callback`` returning True breaks ``tick_loop``
    cleanly without setting ``halted`` (the scheduler can be reused).
    """
    api = _make_api(poll_return="RUNNING")
    stop_flag = threading.Event()
    scheduler = _make_scheduler(api=api, stop_callback=stop_flag.is_set, poll_interval=lambda: 0.05)
    scheduler.tick([_cand("a1")], cycle=1)

    stop_flag.set()
    scheduler.tick_loop(
        candidate_provider=lambda: [],
        result_handler=lambda _o: None,
        cycle=2,
        duration_seconds=0.5,
    )
    assert scheduler.halted is False


def test_tick_loop_respects_duration_timeout():
    """C2.4: ``tick_loop`` honours ``duration_seconds`` and returns
    once the deadline elapses (timeout interrupt).
    """
    api = _make_api(poll_return="RUNNING")
    scheduler = _make_scheduler(api=api, poll_interval=lambda: 0.05)
    scheduler.tick([_cand("a1")], cycle=1)

    tick_count = 0

    def candidate_provider() -> list[Candidate]:
        nonlocal tick_count
        tick_count += 1
        return []

    start = time.monotonic()
    scheduler.tick_loop(
        candidate_provider=candidate_provider,
        result_handler=lambda _o: None,
        cycle=2,
        duration_seconds=0.3,
    )
    assert time.monotonic() - start >= 0.3
    assert tick_count >= 2


def test_unknown_status_self_heal_keeps_polling():
    """C2.4: an unrecognised simulation status is treated as "still
    running" and the slot schedules the next poll rather than crashing
    or halting. The scheduler self-heals by polling again.
    """
    api = _make_api(poll_return="UNKNOWN_STATUS")
    scheduler = _make_scheduler(api=api)
    scheduler.tick([_cand("a1")], cycle=1)
    assert scheduler._slots[0].state == SlotState.POLLING

    for _ in range(3):
        outcomes = scheduler.tick([], cycle=2)
        assert outcomes == []
        assert scheduler._slots[0].state == SlotState.POLLING
        assert scheduler.halted is False


def test_cooldown_recovery_returns_slot_to_idle():
    """C2.4: a slot in COOLDOWN with ``cooldown_until`` in the past is
    automatically reset to IDLE by ``available_slots()`` and becomes
    eligible for new candidate assignment.
    """
    api = _make_api()
    api.submit_simulation.side_effect = BrainAPIError(
        "HTTP 429", status_code=429, retry_after=0.01,
    )
    scheduler = _make_scheduler(api=api)
    scheduler.tick([_cand("a1")], cycle=1)
    assert scheduler._slots[0].state == SlotState.COOLDOWN

    time.sleep(0.05)
    available = scheduler.available_slots()
    assert len(available) == 3
    assert all(s.state == SlotState.IDLE for s in available)

    api.submit_simulation.side_effect = None
    api.submit_simulation.return_value = "sim_recovered"
    outcomes = scheduler.tick([_cand("a2", "rank(volume)")], cycle=2)
    submitted = [o for o in outcomes if o.action == "submitted"]
    assert len(submitted) == 1
    assert scheduler.active_count() == 1


def test_consistency_guard_passes_with_default_config():
    """C1.1: ``assert_scheduler_consistency`` succeeds with defaults."""
    assert_scheduler_consistency()
    scheduler = _make_scheduler()
    assert_scheduler_consistency(scheduler)
    assert scheduler.max_slots == OFFICIAL_SIMULATION_SLOT_LIMIT == 3


def test_consistency_guard_raises_on_max_slots_mismatch():
    """C1.1: a scheduler constructed with a non-3 ``max_slots`` raises
    ``SchedulerInconsistencyError`` at init.
    """
    with pytest.raises(SchedulerInconsistencyError):
        ThreeSlotScheduler(
            api=_make_api(),
            settings_provider=_settings,
            event_callback=_noop,
            max_slots=5,
        )


def test_candidate_pool_keeps_producing_while_slots_in_flight():
    """C3: candidate generation is NOT blocked by in-flight official
    simulations. While all 3 slots are POLLING, a grown pool is accepted
    without error; when slots free up, the next pool candidates are
    picked (proving no back-pressure onto the generator).
    """
    api = _make_api(poll_return="RUNNING")
    scheduler = _make_scheduler(api=api, poll_interval=lambda: 0.0)

    initial_pool = [_cand(f"a{i}", f"rank(f{i})") for i in range(3)]
    scheduler.tick(initial_pool, cycle=1)
    assert scheduler.active_count() == 3

    # Pool grows while slots are in-flight — no error / halt / back-pressure.
    grown_pool = initial_pool + [_cand(f"a{i}", f"rank(f{i})") for i in range(3, 8)]
    assert scheduler.tick(grown_pool, cycle=2) == []
    assert scheduler.halted is False
    assert scheduler.active_count() == 3

    # Complete all slots — each freed slot picks up a new pool candidate.
    api.poll_simulation.return_value = "COMPLETED"
    scheduler.tick([], cycle=3)  # all 3 slots complete + reset to IDLE
    # New pool candidates (a3..a7) — pipeline moves completed ones onward.
    remaining = [_cand(f"a{i}", f"rank(f{i})") for i in range(3, 8)]
    outcomes = scheduler.tick(remaining, cycle=4)
    submitted = [o for o in outcomes if o.action == "submitted"]
    assert len(submitted) == 3  # all 3 slots refilled from the grown pool
    assert {o.candidate.alpha_id for o in submitted} == {"a3", "a4", "a5"}
    assert scheduler.halted is False

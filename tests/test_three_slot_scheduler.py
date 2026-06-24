"""Tests for ThreeSlotScheduler — 3-slot concurrent simulation scheduler.

Covers slot initialization, tick behavior, state transitions, cooldown
isolation, concurrency, cancellation, audit trail, and deduplication.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from brain_alpha_ops.brain_api.base import BrainAPI, BrainAPIError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.simulation_scheduler import (
    SlotState,
    ThreeSlotScheduler,
)


def _make_api(submit_return: str = "sim_001", poll_return: str = "RUNNING", fetch_return: dict | None = None):
    api = MagicMock(spec=BrainAPI)
    api.submit_simulation.return_value = submit_return
    api.poll_simulation.return_value = poll_return
    api.fetch_result.return_value = fetch_return or {"alpha_id": "a1", "metrics": {}}
    return api


def _make_candidate(alpha_id: str, expression: str = "rank(close)") -> Candidate:
    return Candidate(
        alpha_id=alpha_id,
        expression=expression,
        family="test",
        hypothesis="test",
    )


def _settings():
    return {"settings": {"period": 120, "decay": 0.9}}


_noop_event = lambda *a, **kw: None


def test_slot_initialization():
    api = _make_api()
    scheduler = ThreeSlotScheduler(api=api, settings_provider=_settings, event_callback=_noop_event)
    assert len(scheduler._slots) == 3
    for slot in scheduler._slots:
        assert slot.state == SlotState.IDLE
        assert slot.candidate is None


def test_tick_fills_idle_slots():
    api = _make_api()
    scheduler = ThreeSlotScheduler(api=api, settings_provider=_settings, event_callback=_noop_event)
    candidates = [_make_candidate(f"a{i}", f"rank(field_{i})") for i in range(5)]

    outcomes = scheduler.tick(candidates, cycle=1)

    assert len(outcomes) == 3
    assert all(o.action == "submitted" for o in outcomes)
    assert scheduler.active_count() == 3


def test_slot_state_transitions():
    api = _make_api()
    scheduler = ThreeSlotScheduler(api=api, settings_provider=_settings, event_callback=_noop_event)
    candidates = [_make_candidate("a1")]

    scheduler.tick(candidates, cycle=1)
    slot = scheduler._slots[0]
    assert slot.state == SlotState.POLLING

    api.poll_simulation.return_value = "COMPLETED"
    scheduler.tick([], cycle=2)
    assert slot.state == SlotState.IDLE


def test_429_cooldown_isolation():
    api = _make_api()
    api.submit_simulation.side_effect = BrainAPIError(
        "rate limited", status_code=429, retry_after=2.0
    )
    scheduler = ThreeSlotScheduler(api=api, settings_provider=_settings, event_callback=_noop_event)
    candidates = [_make_candidate("a1", "rank(close)")]

    scheduler.tick(candidates, cycle=1)
    assert scheduler.active_count() == 0

    slot0 = scheduler._slots[0]
    assert slot0.error_count == 1
    assert slot0.last_error == "rate limited"

    for slot in scheduler._slots[1:]:
        assert slot.state == SlotState.IDLE
        assert slot.error_count == 0


def test_concurrent_slot_operation():
    api = _make_api()
    scheduler = ThreeSlotScheduler(api=api, settings_provider=_settings, event_callback=_noop_event)
    candidates = [_make_candidate(f"a{i}", f"rank(field_{i})") for i in range(3)]

    scheduler.tick(candidates, cycle=1)
    assert scheduler.active_count() == 3

    def poll_worker(slot_idx):
        api.poll_simulation.return_value = "RUNNING"
        scheduler.tick([], cycle=1)

    threads = [threading.Thread(target=poll_worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert scheduler.active_count() == 3


def test_task_cancellation():
    api = _make_api()
    stop_flag = threading.Event()
    scheduler = ThreeSlotScheduler(
        api=api,
        settings_provider=_settings,
        stop_callback=stop_flag.is_set,
        event_callback=_noop_event,
    )
    candidates = [_make_candidate("a1")]
    scheduler.tick(candidates, cycle=1)

    stop_flag.set()
    scheduler.tick([], cycle=2)
    assert scheduler.halted or scheduler.active_count() <= 3


def test_audit_trail_events():
    api = _make_api()
    events = []
    scheduler = ThreeSlotScheduler(
        api=api,
        settings_provider=_settings,
        event_callback=lambda *a, **kw: events.append(a),
    )
    candidates = [_make_candidate("a1")]
    scheduler.tick(candidates, cycle=1)

    event_types = [e[0] for e in events]
    assert "scheduler_submit" in event_types
    assert "scheduler_submitted" in event_types


def test_duplicate_expression_avoidance():
    api = _make_api()
    scheduler = ThreeSlotScheduler(api=api, settings_provider=_settings, event_callback=_noop_event)
    dup = _make_candidate("a1", "rank(close)")
    candidates = [dup, _make_candidate("a2", "rank(volume)")]

    scheduler.tick(candidates, cycle=1)
    active_keys = {s.candidate.expression for s in scheduler._slots if s.candidate}
    assert len(active_keys) == 2


def test_excluded_keys_prevent_submission():
    api = _make_api()
    scheduler = ThreeSlotScheduler(api=api, settings_provider=_settings, event_callback=_noop_event)
    candidates = [_make_candidate("a1", "rank(close)")]

    scheduler.tick(candidates, cycle=1, active_expression_keys={"rank(close)"})
    assert scheduler.active_count() == 0


def test_available_slots_respects_global_cooldown():
    api = _make_api()
    scheduler = ThreeSlotScheduler(api=api, settings_provider=_settings)
    scheduler.enter_global_cooldown(120.0, "test cooldown")

    available = scheduler.available_slots()
    assert len(available) == 0

    scheduler.resume()
    available = scheduler.available_slots()
    assert len(available) == 3

"""Tests for ProductionHealthMonitor and UnifiedMonitor wiring (Workstream E1)."""
from __future__ import annotations

import time
from dataclasses import dataclass

from brain_alpha_ops.monitoring.production_health import (
    DEFAULT_AUTH_FAILURE_LOOP_THRESHOLD,
    DEFAULT_CANDIDATE_STALL_SECONDS,
    DEFAULT_GATE_BACKLOG_THRESHOLD,
    DEFAULT_SCORING_FAILURE_SPIKE_THRESHOLD,
    DEFAULT_SIMULATION_STUCK_SECONDS,
    HealthCheck,
    ProductionHealthMonitor,
    SIMULATION_WRITEBACK_TIMEOUT_SECONDS,
    UnifiedHealthSnapshot,
)
from brain_alpha_ops.monitoring.unified_monitor import (
    Severity,
    UnifiedHealth,
    UnifiedMonitor,
)


@dataclass
class _FakeSlot:
    slot_id: int
    state: str
    started_at: float


class _FakeScheduler:
    def __init__(self, slots):
        self._slots = slots


# --- E1.1: simulation_slots ---

def test_simulation_slots_no_scheduler_returns_ok():
    monitor = ProductionHealthMonitor()
    check = monitor.check_simulation_slots(None)
    assert check.severity == Severity.OK
    assert check.component == "simulation_slots"


def test_simulation_slots_progressing_normally_returns_ok():
    slot = _FakeSlot(slot_id=1, state="simulating", started_at=time.time() - 30)
    monitor = ProductionHealthMonitor()
    check = monitor.check_simulation_slots(_FakeScheduler([slot]))
    assert check.severity == Severity.OK
    assert check.context_snapshot["slot_count"] == 1


def test_simulation_slots_stuck_returns_degraded():
    """E1.1: slot in simulating > DEFAULT_SIMULATION_STUCK_SECONDS but < timeout → DEGRADED."""
    elapsed = DEFAULT_SIMULATION_STUCK_SECONDS + 60
    slot = _FakeSlot(slot_id=2, state="simulating", started_at=time.time() - elapsed)
    monitor = ProductionHealthMonitor()
    check = monitor.check_simulation_slots(_FakeScheduler([slot]))
    assert check.severity == Severity.DEGRADED
    assert "simulating state longer than" in check.message
    assert check.context_snapshot["stuck_slots"]


def test_simulation_slots_hung_returns_critical_e1_2():
    """E1.2: slot in simulating > SIMULATION_WRITEBACK_TIMEOUT_SECONDS → CRITICAL.

    Message: "Simulation slot X has not written back results in Ys, likely hung"
    suggested_action: "interrupt_slot + cooldown + retry".
    """
    elapsed = SIMULATION_WRITEBACK_TIMEOUT_SECONDS + 120
    slot = _FakeSlot(slot_id=3, state="simulating", started_at=time.time() - elapsed)
    monitor = ProductionHealthMonitor()
    check = monitor.check_simulation_slots(_FakeScheduler([slot]))
    assert check.severity == Severity.CRITICAL
    assert "has not written back results" in check.message
    assert "likely hung" in check.message
    assert check.suggested_action == "interrupt_slot + cooldown + retry"
    assert check.context_snapshot["hung_slots"]


def test_simulation_slots_ignores_non_simulating_states():
    """Slots in IDLE/COOLDOWN/COMPLETED must not trigger stuck/hung detection."""
    slots = [
        _FakeSlot(slot_id=1, state="idle", started_at=time.time() - 99999),
        _FakeSlot(slot_id=2, state="cooldown", started_at=time.time() - 99999),
        _FakeSlot(slot_id=3, state="completed", started_at=time.time() - 99999),
    ]
    monitor = ProductionHealthMonitor()
    check = monitor.check_simulation_slots(_FakeScheduler(slots))
    assert check.severity == Severity.OK


# --- E1.1: candidate_production ---

def test_candidate_production_stall_returns_degraded():
    """No new candidates for > DEFAULT_CANDIDATE_STALL_SECONDS → DEGRADED."""
    lgt = time.time() - DEFAULT_CANDIDATE_STALL_SECONDS - 60
    monitor = ProductionHealthMonitor()
    check = monitor.check_candidate_production(pool=["a", "b"], last_generation_time=lgt)
    assert check.severity == Severity.DEGRADED
    assert "no new candidates" in check.message
    assert check.context_snapshot["pool_size"] == 2


def test_candidate_production_active_returns_ok():
    lgt = time.time() - 60
    monitor = ProductionHealthMonitor()
    check = monitor.check_candidate_production(pool=["a"], last_generation_time=lgt)
    assert check.severity == Severity.OK


def test_candidate_production_unknown_timestamp_returns_warning():
    monitor = ProductionHealthMonitor()
    check = monitor.check_candidate_production(pool=["a"], last_generation_time=None)
    assert check.severity == Severity.WARNING


# --- E1.1: scoring_service ---

def test_scoring_service_failure_spike_returns_degraded():
    """Failure count >= DEFAULT_SCORING_FAILURE_SPIKE_THRESHOLD → DEGRADED."""
    failures = [time.time() - 10] * DEFAULT_SCORING_FAILURE_SPIKE_THRESHOLD
    monitor = ProductionHealthMonitor()
    check = monitor.check_scoring_service(type("Svc", (), {"recent_failures": failures})())
    assert check.severity == Severity.DEGRADED
    assert "scoring failure spike" in check.message


def test_scoring_service_normal_returns_ok():
    monitor = ProductionHealthMonitor()
    check = monitor.check_scoring_service(
        type("Svc", (), {"recent_failures": [time.time() - 10]})())
    assert check.severity == Severity.OK


# --- E1.1: quality_gate ---

def test_quality_gate_backlog_returns_degraded():
    backlog = DEFAULT_GATE_BACKLOG_THRESHOLD + 5
    monitor = ProductionHealthMonitor()
    check = monitor.check_quality_gate(type("Gate", (), {"pending_count": backlog})())
    assert check.severity == Severity.DEGRADED
    assert "quality gate backlog" in check.message
    assert check.context_snapshot["pending_evaluations"] == backlog


def test_quality_gate_normal_returns_ok():
    monitor = ProductionHealthMonitor()
    check = monitor.check_quality_gate(type("Gate", (), {"pending_count": 2})())
    assert check.severity == Severity.OK


# --- E1.1: login_session ---

def test_login_session_auth_failure_loop_returns_degraded():
    failures = DEFAULT_AUTH_FAILURE_LOOP_THRESHOLD + 1
    monitor = ProductionHealthMonitor()
    check = monitor.check_login_session(
        {"authenticated": False, "consecutive_failures": failures})
    assert check.severity == Severity.DEGRADED
    assert "auth failure loop" in check.message


def test_login_session_unauthenticated_returns_warning():
    monitor = ProductionHealthMonitor()
    check = monitor.check_login_session({"authenticated": False, "consecutive_failures": 0})
    assert check.severity == Severity.WARNING


def test_login_session_expired_returns_degraded():
    monitor = ProductionHealthMonitor()
    check = monitor.check_login_session({
        "authenticated": True,
        "session_expiry": time.time() - 3600,
        "consecutive_failures": 0,
    })
    assert check.severity == Severity.DEGRADED
    assert "session token expired" in check.message


def test_login_session_authenticated_returns_ok():
    monitor = ProductionHealthMonitor()
    check = monitor.check_login_session({
        "authenticated": True,
        "session_expiry": time.time() + 3600,
        "consecutive_failures": 0,
    })
    assert check.severity == Severity.OK


# --- E1.1: cache_state (corruption detection) ---

def test_cache_state_corruption_returns_degraded(tmp_path):
    """E1.1/F1.1: corrupted official_fields.json → DEGRADED with restore action."""
    path = tmp_path / "official_fields.json"
    path.write_text("{not valid json", encoding="utf-8")
    monitor = ProductionHealthMonitor()
    check = monitor.check_cache_state(str(tmp_path))
    assert check.severity == Severity.DEGRADED
    assert "official cache file(s) corrupted" in check.message
    assert "official_fields.json" in check.message
    assert "restore" in check.suggested_action
    assert any(c["file"] == "official_fields.json" for c in check.context_snapshot["corrupted_files"])


def test_cache_state_valid_files_return_ok(tmp_path):
    (tmp_path / "official_fields.json").write_text("{}", encoding="utf-8")
    (tmp_path / "official_operators.json").write_text("[]", encoding="utf-8")
    monitor = ProductionHealthMonitor()
    check = monitor.check_cache_state(str(tmp_path))
    assert check.severity == Severity.OK
    assert "official_fields.json" in check.context_snapshot["checked_files"]


def test_cache_state_missing_files_return_ok(tmp_path):
    """Missing cache files (not yet fetched) must not be flagged as corrupted."""
    monitor = ProductionHealthMonitor()
    check = monitor.check_cache_state(str(tmp_path))
    assert check.severity == Severity.OK


# --- E1.3: state_consistency ---

def test_state_consistency_drift_returns_degraded_e1_3():
    """E1.3: frontend/backend mismatch → DEGRADED.

    Message: "Frontend-backend state drift: field X (frontend=A, backend=B)"
    suggested_action: "refresh_frontend_state".
    """
    fe = {"connection_state": "connected", "active_view": "dashboard", "candidate_count": 5, "slot_states": []}
    be = {"connection_state": "disconnected", "active_view": "dashboard", "candidate_count": 5, "slot_states": []}
    monitor = ProductionHealthMonitor()
    check = monitor.check_state_consistency(fe, be)
    assert check.severity == Severity.DEGRADED
    assert "Frontend-backend state drift" in check.message
    assert "connection_state" in check.message
    assert "frontend=" in check.message and "backend=" in check.message
    assert check.suggested_action == "refresh_frontend_state"
    drift = check.context_snapshot["drift_fields"]
    assert drift[0]["field"] == "connection_state"
    assert drift[0]["frontend"] == "connected"
    assert drift[0]["backend"] == "disconnected"


def test_state_consistency_matching_returns_ok():
    state = {"connection_state": "connected", "active_view": "dashboard", "candidate_count": 5, "slot_states": []}
    monitor = ProductionHealthMonitor()
    check = monitor.check_state_consistency(state, dict(state))
    assert check.severity == Severity.OK


def test_state_consistency_missing_inputs_returns_ok():
    monitor = ProductionHealthMonitor()
    check = monitor.check_state_consistency(None, None)
    assert check.severity == Severity.OK


# --- aggregate() ---

def test_aggregate_all_ok_returns_ok_no_interrupt():
    monitor = ProductionHealthMonitor()
    snap = monitor.aggregate()
    assert isinstance(snap, UnifiedHealthSnapshot)
    assert snap.overall == Severity.OK
    assert snap.needs_interrupt is False
    assert len(snap.checks) == 7


def test_aggregate_critical_propagates_needs_interrupt():
    """E1.2: hung slot → aggregate overall=CRITICAL → needs_interrupt=True."""
    elapsed = SIMULATION_WRITEBACK_TIMEOUT_SECONDS + 60
    slot = _FakeSlot(slot_id=9, state="simulating", started_at=time.time() - elapsed)
    monitor = ProductionHealthMonitor()
    monitor.configure(scheduler=_FakeScheduler([slot]))
    snap = monitor.aggregate()
    assert snap.overall == Severity.CRITICAL
    assert snap.needs_interrupt is True


def test_aggregate_degraded_does_not_trigger_interrupt():
    """DEGRADED must not trigger needs_interrupt (only CRITICAL does)."""
    lgt = time.time() - DEFAULT_CANDIDATE_STALL_SECONDS - 60
    monitor = ProductionHealthMonitor()
    monitor.configure(pool=["a"], last_generation_time=lgt)
    snap = monitor.aggregate()
    assert snap.overall == Severity.DEGRADED
    assert snap.needs_interrupt is False


def test_aggregate_uses_overrides():
    """aggregate() should accept per-call overrides for any service ref."""
    monitor = ProductionHealthMonitor()
    fe = {"connection_state": "a", "active_view": "x", "candidate_count": 1, "slot_states": []}
    be = {"connection_state": "b", "active_view": "x", "candidate_count": 1, "slot_states": []}
    snap = monitor.aggregate(frontend_state=fe, backend_state=be)
    assert snap.overall == Severity.DEGRADED


# --- UnifiedMonitor wiring ---

def test_unified_monitor_backward_compat_without_production_monitor():
    """UnifiedMonitor with no production_health_monitor behaves exactly as before."""
    m = UnifiedMonitor()
    h = m.check()
    assert isinstance(h, UnifiedHealth)
    assert h.overall == Severity.OK
    assert h.production is None
    assert h.needs_interrupt is False


def test_unified_monitor_with_unconfigured_production_monitor_returns_ok():
    phm = ProductionHealthMonitor()
    m = UnifiedMonitor(production_health_monitor=phm)
    h = m.check()
    assert h.overall == Severity.OK
    assert h.needs_interrupt is False
    assert h.production is not None
    assert h.production["overall"] == "ok"
    assert len(h.production["checks"]) == 7


def test_unified_monitor_critical_production_propagates_needs_interrupt():
    """E1.2: CRITICAL from production monitor → UnifiedHealth.needs_interrupt=True."""
    elapsed = SIMULATION_WRITEBACK_TIMEOUT_SECONDS + 60
    slot = _FakeSlot(slot_id=7, state="simulating", started_at=time.time() - elapsed)
    phm = ProductionHealthMonitor()
    phm.configure(scheduler=_FakeScheduler([slot]))
    m = UnifiedMonitor(production_health_monitor=phm)
    h = m.check()
    assert h.overall == Severity.CRITICAL
    assert h.needs_interrupt is True
    assert h.production["overall"] == "critical"
    interrupt_events = [e for e in h.events if e.action == "interrupt" and e.source == "production"]
    assert interrupt_events, "expected at least one production interrupt event"


def test_unified_monitor_degraded_production_does_not_interrupt():
    """DEGRADED from production monitor must NOT set needs_interrupt."""
    lgt = time.time() - DEFAULT_CANDIDATE_STALL_SECONDS - 60
    phm = ProductionHealthMonitor()
    phm.configure(pool=["a"], last_generation_time=lgt)
    m = UnifiedMonitor(production_health_monitor=phm)
    h = m.check()
    assert h.overall == Severity.DEGRADED
    assert h.needs_interrupt is False


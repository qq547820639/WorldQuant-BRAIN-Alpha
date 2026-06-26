"""Production health monitor — extends UnifiedMonitor coverage (Workstream E1).

Covers official simulation queue, candidate-pool production, scoring service,
quality gate, login session, cache state, and frontend/backend state drift.
Each ``check_*`` returns a :class:`HealthCheck`; :meth:`aggregate` combines
them into a :class:`UnifiedHealthSnapshot` (``needs_interrupt`` is True iff
any check is CRITICAL, per E1.2). Duck-typed: missing/None inputs return OK.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.monitoring.unified_monitor import Severity

logger = logging.getLogger(__name__)

# Thresholds (seconds / counts).
DEFAULT_SIMULATION_STUCK_SECONDS = 600.0        # "simulating" > 10min → DEGRADED
SIMULATION_WRITEBACK_TIMEOUT_SECONDS = 1800.0   # 30min → CRITICAL (likely hung)
DEFAULT_CANDIDATE_STALL_SECONDS = 1800.0        # no new candidates → DEGRADED
DEFAULT_SCORING_FAILURE_SPIKE_WINDOW = 60
DEFAULT_SCORING_FAILURE_SPIKE_THRESHOLD = 5
DEFAULT_GATE_BACKLOG_THRESHOLD = 10
DEFAULT_AUTH_FAILURE_LOOP_THRESHOLD = 3

_OFFICIAL_CACHE_FILES = ("official_fields.json", "official_operators.json",
                         "official_datasets.json", "official_settings.json")
_CONSISTENCY_FIELDS = ("connection_state", "active_view", "candidate_count", "slot_states")
_SIMULATING_STATES = ("simulating", "polling", "submitting")


@dataclass
class HealthCheck:
    """Single production health check result."""
    severity: Severity
    component: str
    message: str
    suggested_action: str = ""
    context_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedHealthSnapshot:
    """Aggregated health across all production checks."""
    overall: Severity
    needs_interrupt: bool
    checks: list[HealthCheck] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


def _check(sev: Severity, component: str, message: str, action: str = "", **ctx: Any) -> HealthCheck:
    return HealthCheck(sev, component, message, action, dict(ctx))


def _ok(component: str, message: str, **ctx: Any) -> HealthCheck:
    return HealthCheck(Severity.OK, component, message, "", dict(ctx))


class ProductionHealthMonitor:
    """Monitors production subsystems not covered by Browser/Stall monitors."""

    def __init__(
        self,
        *,
        simulation_stuck_seconds: float = DEFAULT_SIMULATION_STUCK_SECONDS,
        simulation_writeback_timeout_seconds: float = SIMULATION_WRITEBACK_TIMEOUT_SECONDS,
        candidate_stall_seconds: float = DEFAULT_CANDIDATE_STALL_SECONDS,
        scoring_failure_window: int = DEFAULT_SCORING_FAILURE_SPIKE_WINDOW,
        scoring_failure_threshold: int = DEFAULT_SCORING_FAILURE_SPIKE_THRESHOLD,
        gate_backlog_threshold: int = DEFAULT_GATE_BACKLOG_THRESHOLD,
        auth_failure_loop_threshold: int = DEFAULT_AUTH_FAILURE_LOOP_THRESHOLD,
    ) -> None:
        for _k, _v in locals().items():
            if _k != "self":
                setattr(self, _k, _v)
        # Configurable live service references (any may be None).
        self._scheduler = self._pool = self._scoring_service = None
        self._gate_service = self._auth_state = self._data_dir = None
        self._last_generation_time: float | None = None
        self._frontend_state: dict[str, Any] | None = None
        self._backend_state: dict[str, Any] | None = None

    def configure(self, **services: Any) -> None:
        for name, val in services.items():
            if val is not None:
                setattr(self, f"_{name}", val)

    def check_simulation_slots(self, scheduler: Any | None = None) -> HealthCheck:
        sched = scheduler if scheduler is not None else self._scheduler
        if sched is None:
            return _ok("simulation_slots", "no scheduler provided", active=False)
        slots = _safe_get_slots(sched)
        if not slots:
            return _ok("simulation_slots", "no active simulation slots", slot_count=0)
        now = time.time()
        stuck: list[dict[str, Any]] = []
        hung: list[dict[str, Any]] = []
        for slot in slots:
            state = _slot_state_value(slot)
            if state not in _SIMULATING_STATES:
                continue
            started_at = float(getattr(slot, "started_at", 0) or _dict_get(slot, "started_at", 0) or 0)
            if started_at <= 0:
                continue
            elapsed = now - started_at
            sid = getattr(slot, "slot_id", _dict_get(slot, "slot_id", "?"))
            if elapsed >= self.simulation_writeback_timeout_seconds:
                hung.append({"slot_id": sid, "elapsed": elapsed, "state": state})
            elif elapsed >= self.simulation_stuck_seconds:
                stuck.append({"slot_id": sid, "elapsed": elapsed, "state": state})
        if hung:
            return _check(Severity.CRITICAL, "simulation_slots",
                          f"Simulation slot {hung[0]['slot_id']} has not written back results "
                          f"in {int(hung[0]['elapsed'])}s, likely hung",
                          "interrupt_slot + cooldown + retry",
                          hung_slots=hung, stuck_slots=stuck, slot_count=len(slots))
        if stuck:
            return _check(Severity.DEGRADED, "simulation_slots",
                          f"{len(stuck)} simulation slot(s) in simulating state longer than "
                          f"{int(self.simulation_stuck_seconds)}s",
                          "investigate slot progress; consider interrupt if no writeback soon",
                          stuck_slots=stuck, slot_count=len(slots))
        return _ok("simulation_slots", "all simulation slots progressing normally", slot_count=len(slots))

    def check_candidate_production(
        self, pool: Any | None = None, last_generation_time: float | None = None,
    ) -> HealthCheck:
        pl = pool if pool is not None else self._pool
        lgt = last_generation_time if last_generation_time is not None else self._last_generation_time
        if pl is None and lgt is None:
            return _ok("candidate_production", "no pool/generation time provided", active=False)
        pool_size = _pool_size(pl)
        if lgt is None or lgt <= 0:
            return _check(Severity.WARNING, "candidate_production",
                          "candidate generation timestamp unknown; cannot verify production liveness",
                          "record last_generation_time when producing candidates",
                          pool_size=pool_size, last_generation_time=lgt)
        elapsed = time.time() - float(lgt)
        if elapsed >= self.candidate_stall_seconds:
            return _check(Severity.DEGRADED, "candidate_production",
                          f"no new candidates in {int(elapsed)}s (pool_size={pool_size})",
                          "resume generation cycle; check generator health",
                          elapsed_since_generation=elapsed, pool_size=pool_size, last_generation_time=lgt)
        return _ok("candidate_production", "candidate production active",
                   pool_size=pool_size, elapsed_since_generation=elapsed)

    def check_scoring_service(self, scoring_service: Any | None = None) -> HealthCheck:
        svc = scoring_service if scoring_service is not None else self._scoring_service
        if svc is None:
            return _ok("scoring_service", "no scoring service provided", active=False)
        recent = _count_recent_failures(svc, self.scoring_failure_window)
        if recent >= self.scoring_failure_threshold:
            return _check(Severity.DEGRADED, "scoring_service",
                          f"scoring failure spike: {recent} failures in last {self.scoring_failure_window}s",
                          "inspect scoring error logs; throttle new evaluations if persistent",
                          recent_failures=recent, window_seconds=self.scoring_failure_window)
        return _ok("scoring_service", "scoring service failure rate normal", recent_failures=recent)

    def check_quality_gate(self, gate_service: Any | None = None) -> HealthCheck:
        svc = gate_service if gate_service is not None else self._gate_service
        if svc is None:
            return _ok("quality_gate", "no gate service provided", active=False)
        backlog = _count_gate_backlog(svc)
        if backlog >= self.gate_backlog_threshold:
            return _check(Severity.DEGRADED, "quality_gate",
                          f"quality gate backlog: {backlog} pending evaluations",
                          "increase gate throughput or pause new submissions until backlog clears",
                          pending_evaluations=backlog)
        return _ok("quality_gate", "quality gate backlog normal", pending_evaluations=backlog)

    def check_login_session(self, auth_state: Any | None = None) -> HealthCheck:
        state = auth_state if auth_state is not None else self._auth_state
        if state is None:
            return _ok("login_session", "no auth state provided", active=False)
        auth = _coerce_auth_state(state)
        authenticated = bool(auth.get("authenticated", auth.get("logged_in", False)))
        expiry = auth.get("session_expiry") or auth.get("expires_at")
        failures = int(auth.get("consecutive_failures", 0) or 0)
        if failures >= self.auth_failure_loop_threshold:
            return _check(Severity.DEGRADED, "login_session",
                          f"auth failure loop: {failures} consecutive failures",
                          "halt automated retries; prompt user to re-authenticate via env-var credentials",
                          consecutive_failures=failures, authenticated=authenticated)
        if not authenticated:
            return _check(Severity.WARNING, "login_session", "session not authenticated",
                          "authenticate via BRAIN_USERNAME/BRAIN_PASSWORD env vars", authenticated=False)
        if expiry and float(expiry) < time.time():
            return _check(Severity.DEGRADED, "login_session", "session token expired",
                          "refresh authentication; do not retry with stale token",
                          authenticated=authenticated, session_expiry=expiry)
        return _ok("login_session", "session authenticated", authenticated=True, session_expiry=expiry)

    def check_cache_state(self, data_dir: Any | None = None) -> HealthCheck:
        d = data_dir if data_dir is not None else self._data_dir
        if not d:
            return _ok("cache_state", "no data_dir provided", active=False)
        corrupted: list[dict[str, Any]] = []
        checked: list[str] = []
        for name in _OFFICIAL_CACHE_FILES:
            path = os.path.join(str(d), name)
            if not os.path.exists(path):
                continue
            checked.append(name)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    json.load(fh)
            except json.JSONDecodeError as exc:
                corrupted.append({"file": name, "error": f"JSONDecodeError: {exc}"})
            except OSError as exc:
                corrupted.append({"file": name, "error": f"OSError: {exc}"})
        if corrupted:
            return _check(Severity.DEGRADED, "cache_state",
                          f"{len(corrupted)} official cache file(s) corrupted: "
                          + ", ".join(c["file"] for c in corrupted),
                          "restore official_*.json from last known good snapshot or re-fetch from BRAIN API",
                          corrupted_files=corrupted, checked_files=checked)
        return _ok("cache_state", "official cache files parse successfully", checked_files=checked)

    def check_state_consistency(
        self,
        frontend_state: dict[str, Any] | None = None,
        backend_state: dict[str, Any] | None = None,
    ) -> HealthCheck:
        fe = frontend_state if frontend_state is not None else self._frontend_state
        be = backend_state if backend_state is not None else self._backend_state
        if fe is None or be is None:
            return _ok("state_consistency", "frontend/backend state not both provided", active=False)
        drift: list[dict[str, Any]] = []
        for fname in _CONSISTENCY_FIELDS:
            fe_val, be_val = fe.get(fname), be.get(fname)
            if fe_val != be_val:
                drift.append({"field": fname, "frontend": fe_val, "backend": be_val})
        if drift:
            return _check(Severity.DEGRADED, "state_consistency",
                          f"Frontend-backend state drift: field {drift[0]['field']} "
                          f"(frontend={drift[0]['frontend']!r}, backend={drift[0]['backend']!r})",
                          "refresh_frontend_state", drift_fields=drift)
        return _ok("state_consistency", "frontend and backend state consistent",
                   checked_fields=list(_CONSISTENCY_FIELDS))

    def aggregate(self, **overrides: Any) -> UnifiedHealthSnapshot:
        """Run all configured checks; needs_interrupt=True iff any check is CRITICAL."""
        checks: list[HealthCheck] = [
            self.check_simulation_slots(overrides.get("scheduler")),
            self.check_candidate_production(
                overrides.get("pool"), overrides.get("last_generation_time")),
            self.check_scoring_service(overrides.get("scoring_service")),
            self.check_quality_gate(overrides.get("gate_service")),
            self.check_login_session(overrides.get("auth_state")),
            self.check_cache_state(overrides.get("data_dir")),
            self.check_state_consistency(
                overrides.get("frontend_state"), overrides.get("backend_state")),
        ]
        severities = [c.severity for c in checks]
        if Severity.CRITICAL in severities:
            overall = Severity.CRITICAL
        elif Severity.DEGRADED in severities:
            overall = Severity.DEGRADED
        elif Severity.WARNING in severities:
            overall = Severity.WARNING
        else:
            overall = Severity.OK
        return UnifiedHealthSnapshot(
            overall=overall, needs_interrupt=overall == Severity.CRITICAL, checks=checks)


def _safe_get_slots(scheduler: Any) -> list[Any]:
    if scheduler is None:
        return []
    slots = getattr(scheduler, "_slots", None) or getattr(scheduler, "slots", None)
    if slots is None and isinstance(scheduler, dict):
        slots = scheduler.get("slots") or scheduler.get("_slots")
    return list(slots) if isinstance(slots, (list, tuple)) else []

def _slot_state_value(slot: Any) -> str:
    state = getattr(slot, "state", None) or (
        slot.get("state") if isinstance(slot, dict) else None)
    if state is None:
        return ""
    return str(getattr(state, "value", state)).lower()

def _dict_get(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else default

def _pool_size(pool: Any) -> int:
    if pool is None:
        return 0
    if isinstance(pool, list):
        return len(pool)
    if isinstance(pool, dict):
        return int(pool.get("size", pool.get("count", len(pool))) or 0)
    size = getattr(pool, "size", None) or getattr(pool, "candidate_count", None)
    if size is None:
        cands = getattr(pool, "candidates", None)
        return len(cands) if isinstance(cands, (list, tuple)) else 0
    try:
        return int(size)
    except (TypeError, ValueError):
        return 0

def _attr_or_dict_item(service: Any, *names: str) -> Any:
    for n in names:
        val = getattr(service, n, None)
        if val is None and isinstance(service, dict):
            val = service.get(n)
        if val is not None:
            return val
    return None

def _count_recent_failures(service: Any, window_seconds: int) -> int:
    failures = _attr_or_dict_item(service, "recent_failures", "failure_timestamps")
    if not failures:
        return 0
    if isinstance(failures, int):
        return int(failures)
    try:
        return sum(1 for ts in failures if float(ts) >= time.time() - window_seconds)
    except (TypeError, ValueError):
        return 0

def _count_gate_backlog(service: Any) -> int:
    backlog = _attr_or_dict_item(service, "pending_count", "backlog")
    if backlog is None:
        pending = getattr(service, "pending", None)
        return len(pending) if isinstance(pending, (list, tuple, dict)) else 0
    try:
        return int(backlog)
    except (TypeError, ValueError):
        return 0

def _coerce_auth_state(auth_state: Any) -> dict[str, Any]:
    if isinstance(auth_state, dict):
        return auth_state
    if hasattr(auth_state, "__dict__"):
        return {k: v for k, v in vars(auth_state).items() if not k.startswith("_")}
    return {}


__all__ = ["DEFAULT_SIMULATION_STUCK_SECONDS", "SIMULATION_WRITEBACK_TIMEOUT_SECONDS",
           "DEFAULT_CANDIDATE_STALL_SECONDS", "DEFAULT_SCORING_FAILURE_SPIKE_WINDOW",
           "DEFAULT_SCORING_FAILURE_SPIKE_THRESHOLD", "DEFAULT_GATE_BACKLOG_THRESHOLD",
           "DEFAULT_AUTH_FAILURE_LOOP_THRESHOLD", "HealthCheck", "UnifiedHealthSnapshot",
           "ProductionHealthMonitor"]

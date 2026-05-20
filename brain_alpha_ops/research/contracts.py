"""Typed record contracts for persisted research state.

The project stores most operational state in append-only JSONL files.  These
helpers keep the records stable across the pipeline, web API, MCP tools, and
LLM context builders without adding a heavy validation dependency.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any, TypedDict

from brain_alpha_ops.models import Candidate, utc_now


LIFECYCLE_RECORD_SCHEMA = "lifecycle_record.v1"
BACKTEST_RECORD_SCHEMA = "backtest_record.v1"
ASSISTANT_GUIDANCE_RECORD_SCHEMA = "assistant_guidance_record.v1"
STRATEGY_LIFECYCLE_RECORD_SCHEMA = "strategy_lifecycle_record.v1"

ACTIVE_BACKTEST_ACTIONS = {
    "submitted",
    "polled",
    "running",
    "poll_deferred",
    "result_deferred",
}
ACTIVE_BACKTEST_STATUSES = {
    "SUBMITTED",
    "RUNNING",
    "PENDING",
    "POLLING",
    "SIMULATION_SUBMITTED",
    "SIMULATION_RUNNING",
    "SIMULATION_POLL_DEFERRED_RATE_LIMIT",
    "SIMULATION_RESULT_DEFERRED_RATE_LIMIT",
}
TERMINAL_BACKTEST_ACTIONS = {
    "completed",
    "failed",
    "submit_failed",
    "poll_failed",
    "result_failed",
}
TERMINAL_BACKTEST_STATUSES = {
    "COMPLETED",
    "FAILED",
    "ERROR",
    "CANCELLED",
    "SIMULATION_FAILED",
    "SIMULATION_POLL_FAILED",
    "SIMULATION_REQUEST_FAILED",
    "SIMULATION_RESULT_FAILED",
    "SIMULATION_TIMEOUT",
    "OFFICIAL_SIMULATED",
    "OFFICIAL_STANDARD_REJECTED",
    "SUBMISSION_READY",
}


class LifecycleRecord(TypedDict, total=False):
    schema_version: str
    correlation_id: str
    timestamp: Any
    run_id: str
    alpha_id: str
    official_alpha_id: str
    stage: str
    status: str
    simulation_id: str
    expression: str


class BacktestRecord(TypedDict, total=False):
    schema_version: str
    correlation_id: str
    timestamp: Any
    run_id: str
    action: str
    slot: int
    alpha_id: str
    official_alpha_id: str
    simulation_id: str
    status: str
    lifecycle_status: str
    expression: str
    poll_count: int


class AssistantGuidanceRecord(TypedDict, total=False):
    schema_version: str
    correlation_id: str
    timestamp: str
    source: str
    guidance_digest: str
    guidance: dict[str, Any]


class StrategyLifecycleRecord(TypedDict, total=False):
    schema_version: str
    correlation_id: str
    timestamp: Any
    run_id: str
    action: str
    profile_id: str
    profile_index: int
    profile_name: str
    cycle: int
    reason: str
    parent_profile_id: str
    metrics: dict[str, Any]


def lifecycle_record(run_id: str, record: dict[str, Any]) -> LifecycleRecord:
    row: LifecycleRecord = {
        **_clean_mapping(record),
        "schema_version": LIFECYCLE_RECORD_SCHEMA,
        "run_id": str(run_id or record.get("run_id") or ""),
    }
    row.setdefault("timestamp", utc_now())
    row["correlation_id"] = correlation_id(
        run_id=row.get("run_id", ""),
        alpha_id=row.get("alpha_id", ""),
        simulation_id=row.get("simulation_id", ""),
        phase=row.get("stage", ""),
    )
    return row


def backtest_record(run_id: str, record: dict[str, Any]) -> BacktestRecord:
    row: BacktestRecord = {
        **_clean_mapping(record),
        "schema_version": BACKTEST_RECORD_SCHEMA,
        "run_id": str(run_id or record.get("run_id") or ""),
    }
    row.setdefault("timestamp", utc_now())
    row["correlation_id"] = correlation_id(
        run_id=row.get("run_id", ""),
        alpha_id=row.get("alpha_id", ""),
        simulation_id=row.get("simulation_id", ""),
        phase=row.get("action", ""),
    )
    return row


def assistant_guidance_record(guidance: dict[str, Any], *, source: str = "web") -> AssistantGuidanceRecord:
    digest = str(guidance.get("guidance_digest") or "")
    row: AssistantGuidanceRecord = {
        "schema_version": ASSISTANT_GUIDANCE_RECORD_SCHEMA,
        "timestamp": utc_now(),
        "source": str(source or "web"),
        "guidance_digest": digest,
        "guidance": dict(guidance),
    }
    row["correlation_id"] = correlation_id(run_id="", alpha_id="", simulation_id="", phase=digest or source)
    return row


def strategy_lifecycle_record(run_id: str, record: dict[str, Any]) -> StrategyLifecycleRecord:
    row: StrategyLifecycleRecord = {
        **_clean_mapping(record),
        "schema_version": STRATEGY_LIFECYCLE_RECORD_SCHEMA,
        "run_id": str(run_id or record.get("run_id") or ""),
    }
    row.setdefault("timestamp", utc_now())
    row["correlation_id"] = correlation_id(
        run_id=row.get("run_id", ""),
        alpha_id=row.get("profile_id", ""),
        simulation_id="",
        phase=row.get("action", ""),
    )
    return row


def correlation_id(*, run_id: Any, alpha_id: Any, simulation_id: Any, phase: Any) -> str:
    parts = [str(run_id or ""), str(alpha_id or ""), str(simulation_id or ""), str(phase or "")]
    seed = "|".join(parts)
    return "corr_" + sha256(seed.encode("utf-8")).hexdigest()[:16]


def is_active_backtest_record(row: dict[str, Any]) -> bool:
    action = str(row.get("action") or "").strip().lower()
    status = str(row.get("status") or row.get("lifecycle_status") or "").strip().upper()
    if not str(row.get("simulation_id") or "").strip():
        return False
    if action in TERMINAL_BACKTEST_ACTIONS or status in TERMINAL_BACKTEST_STATUSES:
        return False
    return action in ACTIVE_BACKTEST_ACTIONS or status in ACTIVE_BACKTEST_STATUSES


def recoverable_backtest_candidates(rows: list[dict[str, Any]], *, max_slots: int) -> list[Candidate]:
    """Return latest active persisted simulations as Candidates for polling.

    JSONL rows are append-only, so the newest row per simulation wins.  Missing
    simulation ids are ignored because the official API cannot reconcile them.
    """
    latest: dict[str, dict[str, Any]] = {}
    terminal: set[str] = set()
    for row in rows:
        sim_id = str(row.get("simulation_id") or "").strip()
        if not sim_id:
            continue
        action = str(row.get("action") or "").strip().lower()
        status = str(row.get("status") or row.get("lifecycle_status") or "").strip().upper()
        if action in TERMINAL_BACKTEST_ACTIONS or status in TERMINAL_BACKTEST_STATUSES:
            terminal.add(sim_id)
            latest.pop(sim_id, None)
            continue
        if sim_id not in terminal and is_active_backtest_record(row):
            latest[sim_id] = row

    rows_by_slot = sorted(latest.values(), key=lambda item: (_safe_int(item.get("slot")), str(item.get("timestamp") or "")))
    candidates: list[Candidate] = []
    used_slots: set[int] = set()
    for row in rows_by_slot:
        slot = _safe_int(row.get("slot"))
        if slot <= 0 or slot > max_slots or slot in used_slots:
            continue
        expression = str(row.get("expression") or "").strip()
        if not expression:
            continue
        candidate = Candidate(
            alpha_id=str(row.get("alpha_id") or f"recovered_{row.get('simulation_id')}"),
            expression=expression,
            family=str(row.get("family") or "Recovered"),
            hypothesis=str(row.get("hypothesis") or "Recovered persisted official simulation."),
            simulation_id=str(row.get("simulation_id") or ""),
            official_alpha_id=str(row.get("official_alpha_id") or ""),
            official_metrics=dict(row.get("official_metrics") or {}) if isinstance(row.get("official_metrics"), dict) else {},
            scorecard=dict(row.get("scorecard") or {}) if isinstance(row.get("scorecard"), dict) else {"total_score": _safe_float(row.get("score"))},
            gate=dict(row.get("gate") or {}) if isinstance(row.get("gate"), dict) else {},
            lifecycle_status=str(row.get("lifecycle_status") or "simulation_running"),
        )
        candidate.submission.update(
            {
                "backtest_slot": slot,
                "simulation_status": str(row.get("status") or "RUNNING"),
                "poll_count": _safe_int(row.get("poll_count")),
                "next_poll_at": 0.0,
                "recovered_from_persistence": True,
                "recovered_correlation_id": str(row.get("correlation_id") or ""),
            }
        )
        candidates.append(candidate)
        used_slots.add(slot)
        if len(candidates) >= max_slots:
            break
    return candidates


def _clean_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

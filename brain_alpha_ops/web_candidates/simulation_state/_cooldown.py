"""Cooldown helpers for Web candidate simulation state (candidate + account scope)."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

DEFERRED_SIMULATION_STATUSES = frozenset({
    "simulation_deferred_concurrency_limit",
    "simulation_deferred_rate_limit",
})
SIMULATION_COOLDOWN_FILENAME = "simulation_cooldown.json"
SIMULATION_COOLDOWN_SCOPE = "official_simulation"
COOLDOWN_UPDATE_FIELDS = [
    "lifecycle_status",
    "simulation_deferred_at",
    "simulation_deferred_until",
    "simulation_retry_after_seconds",
    "simulation_deferred_reason",
    "simulation_cooldown_active",
]

_SIMULATION_COOLDOWN_FILE_LOCK = threading.Lock()


def defer_candidate(
    candidate: dict[str, Any],
    *,
    lifecycle_status: str,
    error_text: str,
    retry_seconds: float,
    now: float | None = None,
) -> None:
    now_value = time.time() if now is None else float(now)
    retry_value = max(0.0, float(retry_seconds or 0.0))
    candidate["lifecycle_status"] = lifecycle_status
    candidate["simulation_deferred_at"] = now_value
    candidate["simulation_deferred_until"] = now_value + retry_value
    candidate["simulation_retry_after_seconds"] = retry_value
    candidate["simulation_deferred_reason"] = error_text
    candidate["simulation_cooldown_active"] = True


def clear_candidate_simulation_cooldown(candidate: dict[str, Any]) -> None:
    candidate["simulation_deferred_at"] = None
    candidate["simulation_deferred_until"] = None
    candidate["simulation_retry_after_seconds"] = None
    candidate["simulation_deferred_reason"] = None
    candidate["simulation_cooldown_active"] = False


def _safe_storage_file(storage_dir: str, filename: str) -> Path:
    if Path(filename).name != filename or Path(filename).is_absolute():
        raise ValueError(f"unsafe storage file: {filename}")
    root = Path(storage_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / filename).resolve()
    if path.parent != root:
        raise ValueError(f"storage file escapes storage_dir: {filename}")
    return path


def _read_simulation_cooldowns_unlocked(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_simulation_cooldowns_unlocked(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def record_account_simulation_cooldown(
    storage_dir: str,
    *,
    lifecycle_status: str,
    error_text: str,
    retry_seconds: float,
    now: float | None = None,
) -> dict[str, Any]:
    now_value = time.time() if now is None else float(now)
    retry_value = max(0.0, float(retry_seconds or 0.0))
    record = {
        "scope": "account",
        "endpoint": SIMULATION_COOLDOWN_SCOPE,
        "active": True,
        "lifecycle_status": lifecycle_status,
        "reason": error_text,
        "recorded_at": now_value,
        "deferred_until": now_value + retry_value,
        "retry_after_seconds": retry_value,
    }
    path = _safe_storage_file(storage_dir, SIMULATION_COOLDOWN_FILENAME)
    with _SIMULATION_COOLDOWN_FILE_LOCK:
        payload = _read_simulation_cooldowns_unlocked(path)
        payload[SIMULATION_COOLDOWN_SCOPE] = record
        _write_simulation_cooldowns_unlocked(path, payload)
    return record


def clear_account_simulation_cooldown(storage_dir: str, *, now: float | None = None) -> None:
    current = time.time() if now is None else float(now)
    path = _safe_storage_file(storage_dir, SIMULATION_COOLDOWN_FILENAME)
    with _SIMULATION_COOLDOWN_FILE_LOCK:
        payload = _read_simulation_cooldowns_unlocked(path)
        record = payload.get(SIMULATION_COOLDOWN_SCOPE)
        if not isinstance(record, dict):
            return
        payload[SIMULATION_COOLDOWN_SCOPE] = {
            **record,
            "active": False,
            "cleared_at": current,
            "remaining_seconds": 0.0,
        }
        _write_simulation_cooldowns_unlocked(path, payload)


def active_account_simulation_cooldown(storage_dir: str, *, now: float | None = None) -> dict[str, Any] | None:
    current = time.time() if now is None else float(now)
    path = _safe_storage_file(storage_dir, SIMULATION_COOLDOWN_FILENAME)
    with _SIMULATION_COOLDOWN_FILE_LOCK:
        payload = _read_simulation_cooldowns_unlocked(path)
        record = payload.get(SIMULATION_COOLDOWN_SCOPE)
        if not isinstance(record, dict) or not record.get("active"):
            return None
        try:
            deferred_until = float(record.get("deferred_until"))
        except (TypeError, ValueError):
            deferred_until = current
        if current < deferred_until:
            remaining = max(0.0, deferred_until - current)
            return {**record, "deferred_until": deferred_until, "remaining_seconds": remaining}
        payload[SIMULATION_COOLDOWN_SCOPE] = {
            **record,
            "active": False,
            "cleared_at": current,
            "remaining_seconds": 0.0,
        }
        _write_simulation_cooldowns_unlocked(path, payload)
    return None


def _simulation_deferred_until(candidate: dict[str, Any]) -> float | None:
    value = candidate.get("simulation_deferred_until")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_simulation_cooling_down(candidate: dict[str, Any], *, now: float | None = None) -> bool:
    lifecycle = str(candidate.get("lifecycle_status", "")).lower()
    if lifecycle not in DEFERRED_SIMULATION_STATUSES:
        return False
    until = _simulation_deferred_until(candidate)
    if until is None:
        return True
    current = time.time() if now is None else float(now)
    if current < until:
        return True
    candidate["simulation_cooldown_active"] = False
    return False

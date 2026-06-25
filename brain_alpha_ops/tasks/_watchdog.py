"""Watchdog helpers for the pipeline task store.

These functions implement stall detection and terminal-state protection so
that ambiguous hangs become explicit, user-visible failures.
"""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.core_state import (
    JOB_ACTIVE_STATUSES as ACTIVE_STATUSES,
)
from brain_alpha_ops.core_state import (
    JOB_TERMINAL_STATUSES as TERMINAL_STATUSES,
)

from ._constants import DEFAULT_WATCHDOG_ERROR


def _updated_at(job: dict[str, Any]) -> float:
    try:
        return float(job.get("updated_at", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _watchdog_should_stop(job: dict[str, Any], now: float, timeout_seconds: float) -> bool:
    status = str(job.get("status") or "").strip().lower()
    if status in TERMINAL_STATUSES:
        return False
    if status not in ACTIVE_STATUSES:
        return True
    updated_at = _updated_at(job)
    return updated_at <= 0 or now - updated_at > timeout_seconds


def _mark_watchdog_failed(job: dict[str, Any], now: float) -> None:
    status = str(job.get("status") or "unknown").strip().lower() or "unknown"
    message = (
        "Web flow watchdog stopped this task because its status was unclear."
        if status not in ACTIVE_STATUSES
        else DEFAULT_WATCHDOG_ERROR
    )
    job["status"] = "failed"
    job["cancel"] = True
    job["error"] = message
    job["updated_at"] = now
    progress = dict(job.get("progress") or {})
    progress.update({
        "phase": "watchdog_failed",
        "percent": 100,
        "percent_complete": 100,
        "message": message,
        "status_message": message,
        "watchdog": {
            "triggered": True,
            "previous_status": status,
        },
    })
    job["progress"] = progress


def _reject_watchdog_terminal_update(
    current: dict[str, Any],
    update: dict[str, Any],
    allow_terminal_overwrite: bool,
) -> bool:
    if allow_terminal_overwrite or not _is_watchdog_terminal_failed(current):
        return False
    return True


def _is_watchdog_terminal_failed(job: dict[str, Any]) -> bool:
    if str(job.get("status") or "").strip().lower() != "failed":
        return False
    progress = job.get("progress") if isinstance(job.get("progress"), dict) else {}
    watchdog = progress.get("watchdog") if isinstance(progress.get("watchdog"), dict) else {}
    return progress.get("phase") == "watchdog_failed" or watchdog.get("triggered") is True

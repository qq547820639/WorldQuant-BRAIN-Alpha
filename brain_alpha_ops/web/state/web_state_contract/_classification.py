"""Status and user-error classification helpers."""
from __future__ import annotations

from typing import Any, Mapping

from brain_alpha_ops.tasks import (
    ACTIVE_STATUSES,
    DEFAULT_RECOVERY_ERROR,
    DEFAULT_WATCHDOG_ERROR,
)

from ._definitions import (
    _CANCELLED_STATUSES,
    _FAILED_STATUSES,
    _MISSING_STATUSES,
    _STATUS_LABELS,
    _SUCCESS_STATUSES,
    _WARNING_STATUSES,
)

def classify_job_status(
    *,
    status: str,
    phase: str = "",
    error: str = "",
    progress: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_status(status)
    text = f"{normalized} {phase} {error} {dict(progress or {})}".lower()

    if normalized in ACTIVE_STATUSES:
        return _state("active", terminal=False, recoverable=True, next_action="monitor_or_cancel")
    if normalized in _SUCCESS_STATUSES:
        return _state("success", terminal=True, recoverable=False, next_action="review_results")
    if normalized in _WARNING_STATUSES:
        return _state(
            "warning",
            terminal=True,
            recoverable=True,
            retryable=True,
            next_action="review_warnings",
            user_error_kind="completed_with_warnings",
        )
    if normalized in _CANCELLED_STATUSES:
        return _state(
            "interrupted",
            terminal=True,
            interrupted=True,
            recoverable=True,
            retryable=True,
            next_action="restart_flow",
            user_error_kind="task_cancelled",
        )
    if normalized in _FAILED_STATUSES:
        interrupted = _looks_interrupted(text)
        specific_error_kind = "task_interrupted" if interrupted else _specific_failed_job_kind(text)
        return _state(
            "interrupted" if interrupted else "failed",
            terminal=True,
            interrupted=interrupted,
            recoverable=True,
            retryable=True,
            next_action="resume_or_restart" if interrupted else "inspect_error",
            user_error_kind=specific_error_kind,
        )
    if normalized in _MISSING_STATUSES:
        return _state(
            "missing",
            terminal=True,
            interrupted=True,
            recoverable=True,
            retryable=True,
            next_action="restart_flow",
            user_error_kind="job_not_found",
        )
    if normalized in {"idle", ""}:
        return _state("idle", terminal=False, recoverable=False, next_action="")
    return _state(
        "unknown",
        terminal=False,
        recoverable=True,
        retryable=True,
        next_action="refresh_status",
        user_error_kind="unknown_state",
    )

def classify_user_error_kind(payload: Mapping[str, Any]) -> str:
    code = str(payload.get("error_code") or payload.get("status_code") or "")
    status_code = _int_value(payload.get("status_code"))
    error_text = str(payload.get("error") or payload.get("redacted_message") or payload.get("message") or "")
    text = f"{code} {error_text}".strip()
    upper = text.upper()
    lower = text.lower()

    if "SESSION_INVALID" in upper or "AUTH" in upper or status_code in {401, 403} or "invalid local session" in lower:
        return "session_expired"
    if "CONCURRENT_SIMULATION_LIMIT_EXCEEDED" in upper or "CONCURRENT_SIMULATION_LIMIT" in upper:
        return "official_concurrency_limit"
    if "WEB_RATE_LIMIT" in upper or "LOCAL_RATE_LIMIT" in upper or "too many read requests" in lower or "too many write requests" in lower or "too many submit requests" in lower:
        return "web_rate_limited"
    if "RATE_LIMIT" in upper or "RATE LIMIT" in upper or "RATE_LIMITED" in upper or status_code == 429 or "too many requests" in lower:
        return "official_rate_limited"
    if "CACHE" in upper and any(token in lower for token in ("unavailable", "missing", "invalid", "failed", "not found")):
        return "cache_unavailable"
    if "CONTEXT" in upper and any(token in lower for token in ("unavailable", "missing cache", "cache unavailable")):
        return "cache_unavailable"
    if "DATASET" in upper and any(token in lower for token in ("missing", "not found", "unknown", "unavailable", "not in official")):
        return "dataset_missing"
    if "EXPRESSION" in upper or "UNKNOWN_OPERATOR" in upper or "syntax" in lower or "unknown operator" in lower:
        return "invalid_expression"
    if "TIMEOUT" in upper or status_code == 408 or "timed out" in lower or "timeout" in lower:
        return "network_timeout"
    if status_code in {500, 502, 503, 504} or any(token in lower for token in ("network", "connection reset", "connection aborted", "remote end closed", "urlopen error")):
        return "network_timeout"
    if any(token in upper for token in ("CANCELLED", "CANCELED", "STOPPED", "STOP_FAILED")) or "task cancelled" in lower:
        return "task_cancelled"
    if "CONFLICT" in upper or "JOBS_FULL" in upper or "QUEUE" in upper or "active " in lower or "already running" in lower:
        return "queue_blocked"
    if "JOB_NOT_FOUND" in upper or ("not found" in lower and "dataset" not in lower):
        return "job_not_found"
    return "general_error"

def _state(
    status_kind: str,
    *,
    terminal: bool,
    interrupted: bool = False,
    recoverable: bool,
    retryable: bool = False,
    next_action: str,
    user_error_kind: str = "",
) -> dict[str, Any]:
    return {
        "status_kind": status_kind,
        "state_label": _STATUS_LABELS.get(status_kind, "状态不明确"),
        "terminal": terminal,
        "active": status_kind == "active",
        "interrupted": interrupted,
        "recoverable": recoverable,
        "retryable": retryable,
        "next_action": next_action,
        **({"user_error_kind": user_error_kind} if user_error_kind else {}),
    }

def _normalize_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "canceled":
        return "cancelled"
    return normalized

def _looks_interrupted(text: str) -> bool:
    markers = (
        "watchdog",
        "stopped",
        "cancelled",
        "canceled",
        "status_failed",
        "sse_exhausted",
        "stream_timeout",
        "ambiguous",
        "stalled",
        "restart",
        DEFAULT_RECOVERY_ERROR.lower(),
        DEFAULT_WATCHDOG_ERROR.lower(),
    )
    return any(marker in text for marker in markers)

def _specific_failed_job_kind(text: str) -> str:
    kind = classify_user_error_kind({"error": text})
    return "job_failed" if kind in {"general_error", "job_failed"} else kind

def _int_value(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

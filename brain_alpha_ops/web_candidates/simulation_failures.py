"""Failure-evidence helpers for Web official simulation jobs."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.web_candidates.audit import append_scientific_audit_event

_SIMULATION_FAILURE_KEYS = (
    "error",
    "detail",
    "message",
    "reason",
    "failureReason",
    "failure_reason",
    "status",
    "state",
)


def simulation_failure_evidence(api: Any, simulation_id: str) -> dict[str, Any]:
    """Fetch a compact, redacted failure summary for an official FAILED simulation."""

    try:
        payload = api.fetch_result(simulation_id)
    except Exception as exc:
        return {
            "simulation_id": simulation_id,
            "error": redact_error_message(exc),
            "source": "fetch_result_exception",
        }
    summary = _simulation_failure_summary(payload)
    return {
        "simulation_id": simulation_id,
        "error": summary or "official simulation returned FAILED",
        "source": "fetch_result",
    }


def append_official_simulation_audit(
    candidate: dict[str, Any],
    *,
    source: str,
    status: str,
    official_api_called: bool = True,
    simulation_id: str = "",
    error: str = "",
    retry_after_seconds: float | None = None,
    submit_attempts: int = 0,
    poll_count: int = 0,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "status": status,
        "simulation_id": simulation_id,
        "submit_attempts": max(0, int(submit_attempts or 0)),
        "poll_count": max(0, int(poll_count or 0)),
    }
    if error:
        details["error"] = error
    if retry_after_seconds is not None:
        details["retry_after_seconds"] = retry_after_seconds
    return append_scientific_audit_event(
        candidate,
        operation="official_simulation_writeback",
        source=source,
        feedback_sources=["official_simulation_status"],
        official_api_called=official_api_called,
        details=details,
    )


def _simulation_failure_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates: list[Any] = [payload]
    raw = payload.get("raw")
    if isinstance(raw, dict):
        candidates.append(raw)
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        candidates.append(metrics)
    for item in candidates:
        text = _first_failure_text(item)
        if text:
            return text
    return ""


def _first_failure_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in _SIMULATION_FAILURE_KEYS:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and str(value).strip():
            return redact_text(str(value).strip())[:240]
        if isinstance(value, dict):
            nested = _first_failure_text(value)
            if nested:
                return nested
    for key in ("errors", "checks", "failures"):
        values = payload.get(key)
        if isinstance(values, list):
            for row in values:
                nested = _first_failure_text(row)
                if nested:
                    return nested
    return ""

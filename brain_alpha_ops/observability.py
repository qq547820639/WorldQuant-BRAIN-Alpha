"""Small structured-context helpers for logs, events, and job failures."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.errors import classify_error
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.contracts import correlation_id as build_correlation_id


OBSERVABILITY_SCHEMA_VERSION = "observability.v1"


def context_payload(
    *,
    run_id: str = "",
    job_id: str = "",
    alpha_id: str = "",
    simulation_id: str = "",
    official_alpha_id: str = "",
    phase: str = "",
    event: str = "",
    error_code: str = "",
    correlation_id: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"schema_version": OBSERVABILITY_SCHEMA_VERSION}
    corr = correlation_id or build_correlation_id(
        run_id=run_id,
        alpha_id=alpha_id,
        simulation_id=simulation_id,
        phase=phase or event or error_code,
    )
    if corr:
        payload["correlation_id"] = corr
    for key, value in {
        "run_id": run_id,
        "job_id": job_id,
        "alpha_id": alpha_id,
        "simulation_id": simulation_id,
        "official_alpha_id": official_alpha_id,
        "phase": phase,
        "event": event,
        "error_code": error_code,
    }.items():
        if value not in ("", None):
            payload[key] = str(value)
    for key, value in extra.items():
        if value not in ("", None):
            payload[key] = value
    return payload


def candidate_context(candidate: Any = None, **extra: Any) -> dict[str, Any]:
    if candidate is None:
        return context_payload(**extra)
    if isinstance(candidate, dict):
        official_metrics = candidate.get("official_metrics") if isinstance(candidate.get("official_metrics"), dict) else {}
        return context_payload(
            alpha_id=str(candidate.get("alpha_id") or ""),
            simulation_id=str(candidate.get("simulation_id") or ""),
            official_alpha_id=str(candidate.get("official_alpha_id") or official_metrics.get("official_alpha_id") or ""),
            **extra,
        )
    official_metrics = getattr(candidate, "official_metrics", {}) or {}
    return context_payload(
        alpha_id=str(getattr(candidate, "alpha_id", "") or ""),
        simulation_id=str(getattr(candidate, "simulation_id", "") or ""),
        official_alpha_id=str(getattr(candidate, "official_alpha_id", "") or official_metrics.get("official_alpha_id") or ""),
        **extra,
    )


def error_payload(
    exc: Exception,
    *,
    error_code: str = "UNHANDLED_ERROR",
    max_length: int = 500,
    **context: Any,
) -> dict[str, Any]:
    classified = classify_error(exc, default_code=error_code)
    redacted_message = redact_error_message(exc, max_length=max_length)
    return context_payload(
        error_code=error_code,
        error_category=classified.category,
        error_type=classified.error_type,
        error=redacted_message,
        redacted_message=redacted_message,
        retryable=classified.retryable,
        status_code=classified.status_code,
        retry_after=classified.retry_after,
        **context,
    )

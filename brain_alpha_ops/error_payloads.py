"""Shared safe error payloads for user-facing entry points."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.errors import classify_error
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.contracts import correlation_id as build_correlation_id


def user_error_payload(
    exc: Exception,
    *,
    error_code: str = "UNHANDLED_ERROR",
    max_length: int = 500,
    **context: Any,
) -> dict[str, Any]:
    info = classify_error(exc, default_code=error_code)
    redacted_message = redact_error_message(exc, max_length=max_length)
    payload: dict[str, Any] = {
        "ok": False,
        **info.to_dict(),
        "error_code": error_code,
        "error": redacted_message,
        "redacted_message": redacted_message,
    }
    payload["correlation_id"] = str(
        context.get("correlation_id")
        or build_correlation_id(
            run_id=context.get("run_id", ""),
            alpha_id=context.get("alpha_id", ""),
            simulation_id=context.get("simulation_id", ""),
            phase=context.get("phase", error_code),
        )
    )
    for key, value in context.items():
        if value not in ("", None):
            payload[key] = value
    return payload

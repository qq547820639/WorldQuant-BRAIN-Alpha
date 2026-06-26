"""Public enrichment and user-error contract functions."""
from __future__ import annotations

from typing import Any, Mapping

from brain_alpha_ops.redaction import redact_error_message

from ._classification import classify_job_status, classify_user_error_kind
from ._definitions import _ERROR_DEFINITIONS

def enrich_error_payload(payload: Mapping[str, Any], *, fallback_kind: str | None = None) -> dict[str, Any]:
    """Return an error payload with AF-018 user-action metadata attached."""

    enriched = dict(payload)
    raw_error = enriched.get("error") or enriched.get("redacted_message") or ""
    safe_error = redact_error_message(raw_error, max_length=500)
    if raw_error or "error" in enriched:
        enriched["error"] = safe_error
    kind = fallback_kind or classify_user_error_kind(enriched)
    user_error = build_user_error(kind, raw_error=safe_error, payload=enriched)
    enriched["user_error"] = user_error
    enriched["user_error_kind"] = user_error["kind"]
    enriched["user_message"] = user_error["message"]
    enriched["next_action"] = user_error["next_action"]
    enriched["recoverable"] = user_error["recoverable"]
    enriched["retryable"] = bool(enriched.get("retryable", user_error["retryable"]))
    return enriched

def enrich_job_response(payload: Mapping[str, Any], *, job_type: str | None = None) -> dict[str, Any]:
    """Attach stable status classification to a job/status response."""

    enriched = dict(payload)
    if job_type:
        enriched.setdefault("job_type", job_type)
    progress = enriched.get("progress") if isinstance(enriched.get("progress"), dict) else {}
    status = str(enriched.get("status") or progress.get("status") or "unknown")
    phase = str(enriched.get("phase") or progress.get("phase") or "")
    error = str(enriched.get("error") or progress.get("error") or progress.get("status_message") or "")

    state = classify_job_status(status=status, phase=phase, error=error, progress=progress)
    enriched.update(state)
    if state.get("user_error_kind"):
        user_error = build_user_error(str(state["user_error_kind"]), raw_error=error, payload=enriched)
        enriched["user_error"] = user_error
        enriched["user_error_kind"] = user_error["kind"]
        enriched["user_message"] = user_error["message"]
        enriched["next_action"] = user_error["next_action"]
        enriched["retryable"] = bool(enriched.get("retryable", user_error["retryable"]))
    elif enriched.get("ok") is False or enriched.get("error") or enriched.get("error_code"):
        enriched = enrich_error_payload(enriched)
    return enriched

def build_user_error(kind: str, *, raw_error: str = "", payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    definition = _ERROR_DEFINITIONS.get(kind) or _ERROR_DEFINITIONS["general_error"]
    safe_error = redact_error_message(raw_error, max_length=500)
    message = str(definition["message"])
    if kind == "general_error" and safe_error:
        message = safe_error
    result = {
        "kind": kind if kind in _ERROR_DEFINITIONS else "general_error",
        "title": definition["title"],
        "message": message,
        "impact": definition["impact"],
        "suggested_action": definition["suggested_action"],
        "action_label": definition["action_label"],
        "next_action": definition["next_action"],
        "severity": definition["severity"],
        "recoverable": bool(definition["recoverable"]),
        "retryable": bool(definition["retryable"]),
    }
    retry_after = (payload or {}).get("retry_after")
    if retry_after not in (None, ""):
        result["retry_after"] = retry_after
    if safe_error and safe_error != message:
        result["detail"] = safe_error
    return result

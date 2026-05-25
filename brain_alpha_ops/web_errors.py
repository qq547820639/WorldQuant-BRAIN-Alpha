"""Error-shaping helpers for the local web console."""

from __future__ import annotations

from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.web_risk_guidance import build_cloud_self_correlation_explanation


AUTH_ERROR_MARKERS = ("authorization", "cookie", "token", "password")


def safe_error_message(exc: Exception) -> str:
    message = redact_error_message(exc)
    lowered = message.lower()
    if "production mode requires" in lowered:
        return "production mode requires BRAIN_USERNAME/BRAIN_PASSWORD or BRAIN_TOKEN"
    if any(marker in lowered for marker in AUTH_ERROR_MARKERS):
        return "Authentication failed; check credentials or connection settings."
    return message


def safe_error_payload(exc: Exception, *, error_code: str = "UNHANDLED_ERROR") -> dict:
    payload = user_error_payload(exc, error_code=error_code)
    payload["error"] = safe_error_message(exc)
    return payload


def web_error_payload(exc: Exception, error_code: str) -> dict:
    payload = safe_error_payload(exc, error_code=error_code)
    text = f"{payload.get('error_code', '')} {payload.get('error', '')}".lower()
    if "cloud_self_correlation" in text:
        explanation = build_cloud_self_correlation_explanation(
            {},
            {"level": "high", "max_similarity": 0.90, "matched_alpha_id": "", "matched_status": ""},
        )
        payload["risk_explanation"] = explanation
        payload["risk_explanations"] = [explanation]
        payload["state_navigation"] = explanation.get("navigation")
    return payload

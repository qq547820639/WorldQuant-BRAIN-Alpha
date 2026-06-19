"""Error-shaping helpers for the local web console."""

from __future__ import annotations

from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.web_check_availability import (
    build_cloud_self_correlation_explanation,
)
from brain_alpha_ops.web_state_contract import enrich_error_payload

AUTH_ERROR_MARKERS = (
    "authorization",
    "cookie",
    "token",
    "password",
    "credential",
    "unauthorized",
    "forbidden",
    "incorrect authentication credentials",
)

# P0-1: BRAIN error code → Chinese translation table.
# Used by safe_error_message() to produce human-readable messages
# for end users who don't know what raw BRAIN error codes mean.
_BRAIN_ERROR_TRANSLATIONS: dict[str, str] = {
    "AUTH_INVALID": "认证失败，用户名或密码不正确。",
    "AUTH_BEARER_INVALID": "Bearer Token 无效，请重新连接。",
    "AUTH_TOKEN_EXPIRED": "登录已过期，请重新输入凭据。",
    "RATE_LIMITED": "BRAIN 平台限流，系统将自动重试，请稍候。",
    "NETWORK_TIMEOUT": "连接 BRAIN 平台超时，请检查网络后重试。",
    "BRAIN_SERVER_ERROR": "BRAIN 平台服务异常，请稍后重试。",
    "CONNECTION_REFUSED": "无法连接到 BRAIN 平台，请确认网络正常。",
    "CONCURRENT_SIMULATION_LIMIT_EXCEEDED": "BRAIN 回测并发槽位已满，系统将等待释放后自动重试。",
}


def safe_error_message(exc: Exception, *, error_code: str = "") -> str:
    """Translate an exception into a user-facing Chinese error message.

    Priority:
    1. Exact BRAIN error_code match from the translation table.
    2. Known message patterns (production mode, auth).
    3. Fallback: redacted exception text.
    """
    # P0-1: check the translation table first using the error_code.
    if error_code and error_code in _BRAIN_ERROR_TRANSLATIONS:
        return _BRAIN_ERROR_TRANSLATIONS[error_code]
    message = redact_error_message(exc)
    lowered = message.lower()
    # Also check if the redacted message contains a known error_code
    for code, translation in _BRAIN_ERROR_TRANSLATIONS.items():
        if code in message:
            return translation
    if "production mode requires" in lowered:
        return "生产模式需要：请设置 BRAIN_USERNAME 和 BRAIN_PASSWORD 环境变量"
    status_code = getattr(exc, "status_code", None)
    if status_code in (401, 403) or "http 401" in lowered or "http 403" in lowered or any(marker in lowered for marker in AUTH_ERROR_MARKERS):
        return "认证失败，请检查凭据或连接设置。"
    return message


def safe_error_payload(exc: Exception, *, error_code: str = "UNHANDLED_ERROR") -> dict:
    payload = user_error_payload(exc, error_code=error_code)
    payload["error"] = safe_error_message(exc, error_code=error_code)
    return enrich_error_payload(payload)


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

from __future__ import annotations

import brain_alpha_ops.web  # noqa: F401  install meta-path bridge for web_* modules
from brain_alpha_ops.brain_api.official import BrainAPIError
from brain_alpha_ops.web_errors import safe_error_message, safe_error_payload, web_error_payload


def test_safe_error_message_redacts_auth_secrets():
    assert safe_error_message(RuntimeError("token secret-token-123 failed")) == (
        "认证失败，请检查凭据或连接设置。"
    )
    assert safe_error_message(RuntimeError("production mode requires credentials")) == (
        "生产模式需要：请设置 BRAIN_USERNAME 和 BRAIN_PASSWORD 环境变量"
    )


def test_safe_error_payload_preserves_error_classification():
    payload = safe_error_payload(
        BrainAPIError("HTTP 429: rate limit", status_code=429, retry_after=5),
        error_code="SYNC_ERROR",
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "SYNC_ERROR"
    assert payload["error_category"] == "rate_limit"
    assert payload["retryable"] is True
    assert payload["status_code"] == 429
    assert payload["retry_after"] == 5


def test_safe_error_payload_maps_plain_403_to_actionable_auth_message():
    payload = safe_error_payload(
        BrainAPIError("HTTP 403: Forbidden", status_code=403),
        error_code="CONNECTION_FAILED",
    )

    assert payload["ok"] is False
    assert payload["error_code"] == "CONNECTION_FAILED"
    assert payload["error_category"] == "auth"
    assert payload["retryable"] is False
    assert payload["status_code"] == 403
    assert payload["error"] == "认证失败，请检查凭据或连接设置。"


def test_web_error_payload_adds_cloud_self_correlation_guidance():
    payload = web_error_payload(ValueError("SUBMIT_CLOUD_SELF_CORRELATION_BLOCKED"), "SUBMIT_ERROR")

    assert payload["risk_explanation"]["rule"] == "cloud_self_correlation"
    assert payload["risk_explanations"] == [payload["risk_explanation"]]
    assert payload["state_navigation"]["reason_code"] == "CLOUD_SELF_CORRELATION_BLOCKED"

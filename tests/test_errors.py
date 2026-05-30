from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.errors import ValidationError, classify_error
from brain_alpha_ops.observability import error_payload
from brain_alpha_ops.redaction import redact_data, redact_text


def test_classify_error_marks_rate_limit_retryable():
    exc = BrainAPIError("HTTP 429: too many requests", status_code=429, retry_after=12)

    info = classify_error(exc, default_code="OFFICIAL_CALL_FAILED")

    assert info.error_code == "OFFICIAL_CALL_FAILED"
    assert info.category == "rate_limit"
    assert info.retryable is True
    assert info.status_code == 429
    assert info.retry_after == 12


def test_classify_error_uses_app_error_code():
    info = classify_error(ValidationError("bad input"), default_code="OTHER")

    assert info.error_code == "VALIDATION_ERROR"
    assert info.category == "validation"
    assert info.retryable is False
    assert info.status_code == 400


def test_error_payload_includes_structured_classification():
    payload = error_payload(
        BrainAPIError("network timeout", status_code=503),
        error_code="SYNC_JOB_FAILED",
        job_id="job_1",
        phase="sync",
    )

    assert payload["schema_version"] == "observability.v1"
    assert payload["error_code"] == "SYNC_JOB_FAILED"
    assert payload["error_category"] == "network"
    assert payload["retryable"] is True
    assert payload["status_code"] == 503
    assert payload["redacted_message"] == payload["error"]


def test_redaction_catches_freeform_secret_fragments():
    text = redact_text("worker failed with secret-token-123 and token=SECRET456")

    assert "secret-token-123" not in text
    assert "SECRET456" not in text
    assert "<redacted>" in text


def test_redaction_catches_email_addresses_next_to_secrets():
    text = redact_text("auth failed for researcher@example.com with token=SECRET456")

    assert "researcher@example.com" not in text
    assert "SECRET456" not in text
    assert "***@***" in text
    assert "token=<redacted>" in text


def test_error_payload_redacts_freeform_secret_fragments():
    payload = error_payload(RuntimeError("secret-token-123 failed"), error_code="RUN_JOB_FAILED")

    assert "secret-token-123" not in payload["error"]
    assert "<redacted>" in payload["error"]
    assert payload["redacted_message"] == payload["error"]


def test_redaction_redacts_user_profile_contact_fields():
    payload = redact_data({
        "username": "researcher@example.com",
        "raw": {
            "email": "researcher@example.com",
            "telephone": "+1234567890",
            "firstName": "Research",
            "fullName": "Research User",
            "address": {"country": "CN"},
            "employment": {"employer": "Example Capital"},
        },
    })
    encoded = str(payload)

    assert "researcher@example.com" not in encoded
    assert "+1234567890" not in encoded
    assert "Research User" not in encoded
    assert payload["username"] == "<redacted>"
    assert payload["raw"]["email"] == "<redacted>"
    assert payload["raw"]["telephone"] == "<redacted>"
    assert payload["raw"]["firstName"] == "<redacted>"
    assert payload["raw"]["fullName"] == "<redacted>"
    assert payload["raw"]["employment"] == "<redacted>"


def test_classify_error_marks_5xx_retryable_network():
    info = classify_error(BrainAPIError("HTTP 503", status_code=503), default_code="OFFICIAL_CALL_FAILED")

    assert info.category == "network"
    assert info.retryable is True
    assert info.status_code == 503

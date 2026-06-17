from __future__ import annotations

from brain_alpha_ops.redaction import (
    REDACTED_SECRET_PLACEHOLDER,
    REDACTION_FIXTURE_EMAIL,
    SHARED_REDACTION_FIXTURE_CORPUS,
    redact_data,
    redact_text,
)


def test_redact_data_handles_recursive_dicts_without_hanging():
    row: dict[str, object] = {"username": "reader@example.com", "status": "running"}
    row["self"] = row

    redacted = redact_data(row)

    assert redacted["username"] == "<redacted>"
    assert redacted["status"] == "running"
    assert redacted["self"] == "<redacted-recursive-reference>"


def test_redact_data_handles_recursive_lists_without_hanging():
    row: list[object] = ["safe"]
    row.append(row)

    assert redact_data(row) == ["safe", "<redacted-recursive-reference>"]


def test_redact_data_limits_deep_nested_runtime_payloads():
    value: object = {"leaf": "safe"}
    for _ in range(8):
        value = {"child": value}

    redacted = redact_data(value, max_depth=4)

    current = redacted
    for _ in range(4):
        assert isinstance(current, dict)
        current = current["child"]
    assert current == "<redacted-depth-limit>"


def test_redact_data_handles_camel_case_and_header_style_secret_keys():
    redacted = redact_data({
        "csrfToken": "csrf-secret-123",
        "sessionId": "session-secret-123",
        "accessToken": "access-secret-123",
        "refreshToken": "refresh-secret-123",
        "idToken": "id-secret-123",
        "headers": {
            "X-Brain-Alpha-Admin-Token": "admin-secret-123",
            "X-CSRF-Token": "csrf-header-secret-123",
            "Set-Cookie": "session=secret-cookie-123",
        },
        "session_credentials_available": True,
    })

    assert redacted["csrfToken"] == "<redacted>"
    assert redacted["sessionId"] == "<redacted>"
    assert redacted["accessToken"] == "<redacted>"
    assert redacted["refreshToken"] == "<redacted>"
    assert redacted["idToken"] == "<redacted>"
    assert redacted["headers"]["X-Brain-Alpha-Admin-Token"] == "<redacted>"
    assert redacted["headers"]["X-CSRF-Token"] == "<redacted>"
    assert redacted["headers"]["Set-Cookie"] == "<redacted>"
    assert redacted["session_credentials_available"] is True


def test_redact_text_rejects_shared_secret_shaped_fixture_corpus():
    for fixture in SHARED_REDACTION_FIXTURE_CORPUS:
        redacted = redact_text(fixture["raw_text"])

        assert REDACTED_SECRET_PLACEHOLDER not in redacted, fixture["label"]
        assert REDACTION_FIXTURE_EMAIL not in redacted, fixture["label"]
        assert "<redacted>" in redacted or "***@***" in redacted, fixture["label"]


def test_redact_data_rejects_shared_secret_shaped_fixture_keys():
    payload = {
        fixture["key"]: fixture["raw_text"]
        for fixture in SHARED_REDACTION_FIXTURE_CORPUS
    }

    redacted = redact_data(payload)

    for fixture in SHARED_REDACTION_FIXTURE_CORPUS:
        assert redacted[fixture["key"]] == "<redacted>", fixture["label"]

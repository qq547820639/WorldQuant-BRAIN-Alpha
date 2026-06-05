from __future__ import annotations

from brain_alpha_ops.redaction import redact_data


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

"""Property-based tests for brain_alpha_ops.redaction module.

Requires hypothesis; tests are skipped gracefully if it is not installed.
"""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")

from hypothesis import given, settings, strategies as st

from brain_alpha_ops.redaction import redact_data, redact_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flatten(obj) -> str:
    """Recursively stringify all leaf values for substring search."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_flatten(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flatten(v) for v in obj)
    return str(obj)


# ---------------------------------------------------------------------------
# Property 1: redacted text does not contain the original credential values
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=2000)
@given(
    password=st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=6, max_size=24),
    token=st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=6, max_size=24),
)
def test_redacted_data_does_not_contain_original_secrets(password: str, token: str):
    """Given a dict containing password/token, redaction must hide the originals."""
    raw = {
        "username": "analyst",
        "password": password,
        "token": token,
        "region": "USA",
    }
    redacted = redact_data(raw)
    blob = _flatten(redacted)
    # The original secret values must not appear anywhere in the redacted output.
    assert password not in blob, f"password leaked: {password!r}"
    assert token not in blob, f"token leaked: {token!r}"


# ---------------------------------------------------------------------------
# Property 2: circular references do not crash
# ---------------------------------------------------------------------------

def test_redact_data_handles_circular_reference():
    """A self-referencing dict must not raise; redact_data should return safely."""
    data: dict = {"key": "value", "password": "s3cret"}
    data["self"] = data  # create cycle

    result = redact_data(data)
    # Must be a dict (not raise), and the recursive ref is replaced with a marker.
    assert isinstance(result, dict)
    blob = _flatten(result)
    assert "s3cret" not in blob


# ---------------------------------------------------------------------------
# Property 3: depth limit is respected
# ---------------------------------------------------------------------------

def _build_nested(depth: int) -> dict:
    """Build a dict nested `depth` levels deep with a password at the bottom."""
    inner: dict = {"password": "deep_secret"}
    for _ in range(depth):
        inner = {"child": inner}
    return inner


@settings(max_examples=20, deadline=2000)
@given(max_depth=st.integers(min_value=1, max_value=6))
def test_redact_data_respects_max_depth(max_depth: int):
    """Values deeper than max_depth are replaced with the depth-limit marker."""
    # Build a structure deeper than max_depth
    data = _build_nested(max_depth + 3)
    result = redact_data(data, max_depth=max_depth)
    blob = _flatten(result)
    # The deep secret should not survive past the depth limit.
    assert "deep_secret" not in blob


# ---------------------------------------------------------------------------
# Property 4: idempotency — redacting already-redacted data yields the same result
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=2000)
@given(
    email_local=st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=3, max_size=10),
)
def test_redact_data_is_idempotent(email_local: str):
    """Redacting an already-redacted structure should not change it further."""
    raw = {
        "email": f"{email_local}@example.com",
        "api_key": "AKIAIOSF0D7EXAMPLE1234",
        "description": "normal text without secrets",
    }
    first_pass = redact_data(raw)
    second_pass = redact_data(first_pass)
    assert first_pass == second_pass, (
        f"Redaction is not idempotent:\n  1st: {first_pass!r}\n  2nd: {second_pass!r}"
    )


# ---------------------------------------------------------------------------
# Property 5: redact_text does not leak auth bearer tokens
# ---------------------------------------------------------------------------

@settings(max_examples=30, deadline=2000)
@given(
    bearer=st.text(
        alphabet=st.characters(min_codepoint=65, max_codepoint=90)
        | st.characters(min_codepoint=97, max_codepoint=122)
        | st.characters(min_codepoint=48, max_codepoint=57)
        | st.sampled_from("._~+/=-"),
        min_size=8,
        max_size=40,
    ),
)
def test_redact_text_hides_bearer_token(bearer: str):
    """redact_text must replace Bearer tokens with <redacted>."""
    text = f"Authorization: Bearer {bearer}"
    result = redact_text(text)
    assert bearer not in result
    assert "<redacted>" in result

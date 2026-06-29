"""Property-based tests for error classification (errors.py + error_catalog.py).

Requires hypothesis; tests are skipped gracefully if it is not installed.
"""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")

from hypothesis import given, settings, strategies as st

from brain_alpha_ops.errors import classify_error, ErrorInfo
from brain_alpha_ops.error_catalog import classify_exception, ErrorKind


# ---------------------------------------------------------------------------
# Valid category set produced by classify_error()
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = frozenset({
    "auth", "validation", "not_found", "conflict",
    "rate_limit", "network", "storage", "internal",
})


# ---------------------------------------------------------------------------
# Property 1: classify_error always returns a valid category
# ---------------------------------------------------------------------------

@settings(max_examples=80, deadline=2000)
@given(
    message=st.text(min_size=0, max_size=120),
    status_code=st.one_of(st.none(), st.integers(min_value=400, max_value=599)),
)
def test_classify_error_returns_valid_category(message: str, status_code):
    """classify_error().category is always one of the known categories."""
    exc = Exception(message)
    if status_code is not None:
        exc.status_code = status_code  # type: ignore[attr-defined]
    info = classify_error(exc)
    assert isinstance(info, ErrorInfo)
    assert info.category in _VALID_CATEGORIES, (
        f"unexpected category {info.category!r} for message={message!r} sc={status_code}"
    )


# ---------------------------------------------------------------------------
# Property 2: determinism — same input always yields same output
# ---------------------------------------------------------------------------

@settings(max_examples=50, deadline=2000)
@given(
    message=st.text(min_size=1, max_size=80),
    code=st.sampled_from(["AUTH_FAILED", "VALIDATION_ERROR", "RATE_LIMITED", "NOT_FOUND", ""]),
)
def test_classify_error_is_deterministic(message: str, code: str):
    """Calling classify_error twice with the same input gives the same result."""
    exc = Exception(message)
    if code:
        exc.code = code  # type: ignore[attr-defined]
    first = classify_error(exc)
    second = classify_error(exc)
    assert first.error_code == second.error_code
    assert first.category == second.category
    assert first.retryable == second.retryable
    assert first.message == second.message


# ---------------------------------------------------------------------------
# Property 3: None-like inputs do not crash
# ---------------------------------------------------------------------------

def test_classify_error_handles_none_message():
    """classify_error with an exception whose message is empty must not raise."""
    exc = Exception("")
    info = classify_error(exc)
    assert isinstance(info, ErrorInfo)
    assert info.category in _VALID_CATEGORIES


def test_classify_exception_handles_none_input():
    """classify_exception(None) must return a valid ErrorKind without raising."""
    kind = classify_exception(None)
    assert isinstance(kind, ErrorKind)


# ---------------------------------------------------------------------------
# Property 4: classify_exception always returns a valid ErrorKind member
# ---------------------------------------------------------------------------

@settings(max_examples=80, deadline=2000)
@given(
    message=st.text(min_size=0, max_size=120),
)
def test_classify_exception_returns_valid_error_kind(message: str):
    """classify_exception() always returns a member of ErrorKind."""
    exc = Exception(message)
    kind = classify_exception(exc)
    assert isinstance(kind, ErrorKind), f"got {kind!r} which is not an ErrorKind"
    # Also verify the value is one of the declared enum values.
    assert kind in ErrorKind


@settings(max_examples=40, deadline=2000)
@given(
    status_code=st.integers(min_value=100, max_value=599),
)
def test_classify_exception_with_status_code_returns_valid_kind(status_code: int):
    """classify_exception(int) maps any status code to a valid ErrorKind."""
    kind = classify_exception(status_code)
    assert isinstance(kind, ErrorKind)


@settings(max_examples=40, deadline=2000)
@given(
    text=st.text(min_size=1, max_size=80),
)
def test_classify_exception_with_string_returns_valid_kind(text: str):
    """classify_exception(str) maps any string to a valid ErrorKind."""
    kind = classify_exception(text)
    assert isinstance(kind, ErrorKind)

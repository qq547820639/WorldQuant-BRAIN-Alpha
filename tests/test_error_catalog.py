"""Tests for brain_alpha_ops.error_catalog (Workstream E3).

Covers:
  - ErrorKind enum has exactly 11 members with snake_case values.
  - ERROR_CATALOG / RECOVERY_URLS completeness for every kind.
  - build_actionable_error returns all required keys + context passthrough.
  - build_actionable_error raises ValueError on unknown kind.
  - classify_exception maps HTTP status codes (401/403/429/408/503/504).
  - classify_exception maps Python exception types
    (JSONDecodeError / KeyError / ConnectionError / TimeoutError).
  - classify_exception maps BRAIN error_code strings and message substrings.
  - classify_exception fallback returns network_timeout.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from brain_alpha_ops.brain_api.base import BrainAPIError
from brain_alpha_ops.error_catalog import (
    ERROR_CATALOG,
    RECOVERY_URLS,
    ErrorCatalogEntry,
    ErrorKind,
    build_actionable_error,
    classify_exception,
)

# ── Catalog structure ─────────────────────────────────────────────────────


def test_error_kind_enum_has_eleven_members():
    members = list(ErrorKind)
    assert len(members) == 11
    expected = {
        "login_expired",
        "cache_unavailable",
        "official_rate_limited",
        "simulation_concurrency_exceeded",
        "dataset_missing",
        "field_non_compliant",
        "expression_invalid",
        "network_timeout",
        "task_cancelled",
        "queue_blocked",
        "local_service_unavailable",
    }
    assert {m.value for m in members} == expected
    # Every member value must be snake_case (no spaces / dashes).
    for m in members:
        assert m.value == m.name


def test_error_catalog_has_entry_for_every_kind():
    assert set(ERROR_CATALOG.keys()) == set(ErrorKind)
    for kind, entry in ERROR_CATALOG.items():
        assert isinstance(entry, ErrorCatalogEntry)
        assert entry.kind is kind
        # Every entry must carry non-empty cause / impact / action / recovery.
        assert entry.cause, f"empty cause for {kind}"
        assert entry.impact_scope, f"empty impact_scope for {kind}"
        assert entry.suggested_action, f"empty suggested_action for {kind}"
        assert entry.recovery_action_id, f"empty recovery_action_id for {kind}"
        assert entry.i18n_key.startswith("error."), f"bad i18n_key for {kind}"
        assert entry.severity in ("error", "warning", "info"), f"bad severity for {kind}"


def test_recovery_urls_cover_every_kind_and_are_non_empty():
    assert set(RECOVERY_URLS.keys()) == set(ErrorKind)
    for kind, url in RECOVERY_URLS.items():
        assert isinstance(url, str) and url.startswith("/"), f"bad recovery_url for {kind}"
        # Catalog entry recovery_url must agree with the RECOVERY_URLS table.
        assert ERROR_CATALOG[kind].recovery_url == url


# ── build_actionable_error ────────────────────────────────────────────────


def test_build_actionable_error_returns_all_required_keys():
    payload = build_actionable_error(ErrorKind.login_expired)
    required = {
        "kind",
        "cause",
        "impact_scope",
        "suggested_action",
        "recovery_action_id",
        "recovery_url",
        "i18n_key",
        "severity",
        "context",
    }
    assert required.issubset(payload.keys())
    assert payload["kind"] == "login_expired"
    assert payload["context"] == {}


def test_build_actionable_error_passes_context_and_accepts_string_kind():
    ctx = {"retry_after": 30.0, "status_code": 429}
    payload = build_actionable_error("official_rate_limited", context=ctx)
    assert payload["kind"] == "official_rate_limited"
    assert payload["context"] == ctx
    # context must be a copy, not the same dict reference.
    ctx["retry_after"] = 999
    assert payload["context"]["retry_after"] == 30.0


def test_build_actionable_error_raises_on_unknown_kind():
    with pytest.raises(ValueError, match="unknown ErrorKind"):
        build_actionable_error("not_a_real_kind")
    with pytest.raises(ValueError):
        build_actionable_error(object())  # type: ignore[arg-type]


# ── classify_exception: HTTP status codes ─────────────────────────────────


@pytest.mark.parametrize(
    "status, expected",
    [
        (401, ErrorKind.login_expired),
        (403, ErrorKind.login_expired),
        (429, ErrorKind.official_rate_limited),
        (408, ErrorKind.network_timeout),
        (504, ErrorKind.network_timeout),
        (503, ErrorKind.local_service_unavailable),
    ],
)
def test_classify_exception_status_codes(status, expected):
    assert classify_exception(status) is expected


def test_classify_exception_unknown_status_falls_back_to_network_timeout():
    assert classify_exception(418) is ErrorKind.network_timeout


# ── classify_exception: exception types ───────────────────────────────────


def test_classify_exception_json_decode_error_is_cache_unavailable():
    try:
        json.loads("{not json}")
    except json.JSONDecodeError as exc:
        assert classify_exception(exc) is ErrorKind.cache_unavailable
    else:
        pytest.fail("expected JSONDecodeError")


def test_classify_exception_key_error_is_dataset_missing():
    assert classify_exception(KeyError("dataset_xyz")) is ErrorKind.dataset_missing


def test_classify_exception_connection_error_is_local_service_unavailable():
    assert classify_exception(ConnectionError("refused")) is ErrorKind.local_service_unavailable


def test_classify_exception_timeout_error_is_network_timeout():
    assert classify_exception(TimeoutError("read timed out")) is ErrorKind.network_timeout


def test_classify_exception_asyncio_cancelled_is_task_cancelled():
    assert classify_exception(asyncio.CancelledError()) is ErrorKind.task_cancelled


# ── classify_exception: BrainAPIError (error_code + status_code) ──────────


def test_classify_exception_brain_rate_limited_error_code():
    exc = BrainAPIError("rate limit", status_code=429, error_code="RATE_LIMITED", retry_after=60)
    assert classify_exception(exc) is ErrorKind.official_rate_limited


def test_classify_exception_brain_concurrent_simulation_error_code():
    exc = BrainAPIError(
        "too many concurrent",
        status_code=400,
        error_code="CONCURRENT_SIMULATION_LIMIT_EXCEEDED",
    )
    assert classify_exception(exc) is ErrorKind.simulation_concurrency_exceeded


def test_classify_exception_brain_auth_token_expired():
    exc = BrainAPIError("token expired", status_code=401, error_code="AUTH_TOKEN_EXPIRED")
    assert classify_exception(exc) is ErrorKind.login_expired


# ── classify_exception: string / message substrings ──────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("CONCURRENT_SIMULATION_LIMIT_EXCEEDED", ErrorKind.simulation_concurrency_exceeded),
        ("HTTP 429: rate limit", ErrorKind.official_rate_limited),
        ("unauthorized access", ErrorKind.login_expired),
        ("DATASET_NOT_FOUND", ErrorKind.dataset_missing),
        ("expression_invalid", ErrorKind.expression_invalid),
        ("queue_blocked", ErrorKind.queue_blocked),
        ("connection refused", ErrorKind.local_service_unavailable),
        ("read timed out", ErrorKind.network_timeout),
    ],
)
def test_classify_exception_string_patterns(text, expected):
    assert classify_exception(text) is expected


def test_classify_exception_none_falls_back_to_network_timeout():
    assert classify_exception(None) is ErrorKind.network_timeout  # type: ignore[arg-type]


def test_classify_exception_generic_exception_falls_back_to_network_timeout():
    assert classify_exception(RuntimeError("something unusual")) is ErrorKind.network_timeout


# ── safe_error_payload integration (actionable field present) ─────────────


def test_safe_error_payload_attaches_actionable_field():
    from brain_alpha_ops.web_errors import safe_error_payload

    payload = safe_error_payload(
        BrainAPIError("HTTP 429: rate limit", status_code=429, retry_after=30, error_code="RATE_LIMITED"),
        error_code="SYNC_ERROR",
    )
    actionable = payload.get("actionable")
    assert isinstance(actionable, dict)
    assert actionable["kind"] == "official_rate_limited"
    assert actionable["recovery_url"] == "/backtests"
    assert actionable["context"]["retry_after"] == 30.0
    assert actionable["context"]["status_code"] == 429

"""Utility helpers for the scientific audit subpackage."""

from __future__ import annotations

import json
from typing import Any

FORBIDDEN_SCIENTIFIC_AUDIT_FEEDBACK_SOURCE_TOKENS = (
    "pytest",
    "fixture",
    "fixtures",
    "unit_test",
    "unit-test",
    "test_result",
    "browser_smoke",
    "browser-smoke",
    "vitest",
)


def _audit_events(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in audit.get("events") or [] if isinstance(event, dict)]


def _scientific_audit_payloads(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Return unique audit payloads from all persisted candidate locations.

    Older writeback paths can leave a stale copy under ``extra_fields`` while a
    newer top-level copy looks safe.  Summaries must inspect both locations so
    the research workflow fails closed instead of hiding unsafe provenance.
    """

    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for audit in (
        row.get("scientific_audit"),
        (row.get("extra_fields") or {}).get("scientific_audit")
        if isinstance(row.get("extra_fields"), dict)
        else None,
    ):
        if not isinstance(audit, dict):
            continue
        identity = _audit_identity(audit)
        if identity in seen:
            continue
        seen.add(identity)
        payloads.append(audit)
    return payloads


def _audit_identity(audit: dict[str, Any]) -> str:
    try:
        return json.dumps(audit, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return repr(audit)


def _feedback_sources_include_test_feedback(sources: Any) -> bool:
    for source in sources if isinstance(sources, list) else []:
        normalized = str(source or "").strip().lower()
        if any(token in normalized for token in FORBIDDEN_SCIENTIFIC_AUDIT_FEEDBACK_SOURCE_TOKENS):
            return True
    return False


def _first_int(*values: Any, default: int) -> int:
    for value in values:
        if _is_int_like(value):
            return int(value)
    return int(default)


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _bool_default(value: Any, default: bool) -> bool:
    return default if value is None else bool(value)


def _is_int_like(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key or "unknown"] = counter.get(key or "unknown", 0) + 1

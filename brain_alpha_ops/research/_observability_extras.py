from __future__ import annotations

"""Scalar coercion helpers extracted from _observability_helpers.py.

These are private primitives used by the observability payload builders.
Do not import from this module directly — import via _observability_helpers.
"""

from typing import Any


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int_from_any(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_from_any(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique_text_items(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    seen: set[str] = set()
    rows: list[str] = []
    for item in values:
        text = _text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(text)
    return rows

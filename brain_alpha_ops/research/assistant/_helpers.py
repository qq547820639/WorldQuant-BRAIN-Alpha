"""Pure helper functions for the assistant sub-package.

These small utilities (``_as_dict``, ``_clamp``, ``_string_items``,
``_guidance_outcomes``, etc.) are used across the request, offline, and
response sub-modules.  Keeping them here avoids duplication.
"""

from __future__ import annotations

import json
import math
from hashlib import sha256
from typing import Any


def _digest_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _digest_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return _digest_text(encoded)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return round(number, 4)


def _string_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _number_items(value: Any) -> list[int | float]:
    items = value if isinstance(value, list) else []
    rows: list[int | float] = []
    for item in items:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        rows.append(int(number) if number.is_integer() else number)
    return rows


def _unique_strings(value: Any) -> list[str]:
    rows = _string_items(value)
    seen: set[str] = set()
    unique: list[str] = []
    for item in rows:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _unique_numbers(value: Any) -> list[int | float]:
    rows = _number_items(value) if not isinstance(value, list) else [item for item in value if isinstance(item, (int, float))]
    unique: list[int | float] = []
    seen: set[float] = set()
    for item in rows:
        marker = float(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(int(marker) if marker.is_integer() else marker)
    return unique


def _normalize_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    if not math.isfinite(number):
        return 0.5
    if 1.0 < number <= 100.0:
        number = number / 100.0
    return round(_clamp(number, 0.0, 1.0), 2)


def _guidance_digest(row: dict[str, Any] | None) -> str:
    return str((row or {}).get("guidance_digest") or "")


def _guidance_count(row: dict[str, Any] | None) -> int:
    return _int_value((row or {}).get("count"))


def _guidance_success_rate(row: dict[str, Any] | None) -> float:
    return _float_value((row or {}).get("success_rate"))


def _guidance_outcomes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        row = _as_dict(item)
        digest = str(row.get("guidance_digest") or "").strip()
        if not digest:
            continue
        rows.append({
            "guidance_digest": digest,
            "count": _int_value(row.get("count")),
            "success_count": _int_value(row.get("success_count")),
            "success_rate": _float_value(row.get("success_rate")),
            "avg_score": _float_value(row.get("avg_score")),
            "avg_sharpe": _float_value(row.get("avg_sharpe")),
            "avg_fitness": _float_value(row.get("avg_fitness")),
        })
    return rows


def _strong_guidance_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outcomes:
        if _guidance_count(row) <= 0:
            continue
        if _guidance_success_rate(row) >= 0.5 or _float_value(row.get("avg_score")) >= 70:
            return row
    return {}


def _weak_guidance_outcome(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    for row in outcomes:
        count = _guidance_count(row)
        if count <= 0:
            continue
        success_rate = _guidance_success_rate(row)
        avg_score = _float_value(row.get("avg_score"))
        if (count >= 2 and success_rate <= 0.25) or (success_rate == 0.0 and avg_score <= 50):
            return row
    return {}


def _duplicate_expressions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        row = _as_dict(item)
        if not row:
            continue
        try:
            count = int(row.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        if count > 1:
            rows.append(row)
    return rows


def _recent_backtest_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_as_dict(item) for item in value[-10:] if _as_dict(item)]

"""Value-coercion helpers extracted from ``market_data_cache``.

These numeric primitives were split out so the parent module stays within the
project's line limit. They are re-imported by the parent module, so public
behavior is unchanged.
"""
from __future__ import annotations

import math
from typing import Any


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _numeric_values(row: dict[str, Any]) -> dict[str, float]:
    ignored = {
        "symbol",
        "id",
        "alpha_id",
        "official_alpha_id",
        "timestamp",
        "updated_at",
        "saved_at",
        "loaded_at",
        "values",
        "metrics",
        "official_metrics",
    }
    values: dict[str, float] = {}
    for source in (row, row.get("values"), row.get("metrics"), row.get("official_metrics")):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key in ignored or not isinstance(value, (int, float)):
                continue
            values[str(key)] = _float(value)
    return values


# Shared value conversion helpers (merged from _value_helpers.py).

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

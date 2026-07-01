"""Shared value conversion helpers for the research package."""
from __future__ import annotations

import math
from typing import Any


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

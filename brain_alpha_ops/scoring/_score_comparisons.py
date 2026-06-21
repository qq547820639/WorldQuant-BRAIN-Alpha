"""Shared scoring comparison primitives used by scoring.py and release_score_gate.py.

Both modules previously duplicated min/max check logic, sub_universe_sharpe
formula, and fitness crosscheck. This module provides them as a single source
of truth.

Import convention: this module MUST NOT import from scoring.py or
release_score_gate.py (avoid cycles). It is imported by both.
"""
from __future__ import annotations

import math
from typing import Any


def min_check(
    name: str,
    actual: float | None,
    expected: float,
    severity: str,
    reason: str,
    *,
    pass_fail: bool = False,
) -> dict[str, Any]:
    """Return a comparison item for a minimum-required metric.

    Args:
        name: Metric name (e.g. "sharpe", "fitness").
        actual: Observed value (None → unknown).
        expected: Minimum required value.
        severity: "ERROR" for hard gates, "WARN" for soft.
        reason: Human-readable description.
        pass_fail: If True, format as {"passed", "actual", "expected"} suitable
                   for ScoreAttribution. Otherwise return scoring.item() style.

    Returns:
        A dict with at least {"name", "actual", "expected", "passed", "reason"}.
    """
    passed = actual is not None and actual >= expected
    if pass_fail:
        return {
            "name": name,
            "passed": passed,
            "actual": actual,
            "expected": expected,
            "severity": severity,
            "reason": reason,
        }
    return {
        "name": name,
        "actual": actual,
        "direction": ">=",
        "target": expected,
        "passed": passed,
        "severity": severity,
        "reason": reason,
    }


def max_check(
    name: str,
    actual: float | None,
    expected: float,
    severity: str,
    reason: str,
    *,
    pass_fail: bool = False,
) -> dict[str, Any]:
    """Return a comparison item for a maximum-required metric."""
    passed = actual is not None and actual <= expected
    if pass_fail:
        return {
            "name": name,
            "passed": passed,
            "actual": actual,
            "expected": expected,
            "severity": severity,
            "reason": reason,
        }
    return {
        "name": name,
        "actual": actual,
        "direction": "<=",
        "target": expected,
        "passed": passed,
        "severity": severity,
        "reason": reason,
    }


def sub_universe_sharpe_formula(
    sharpe: float,
    sub_size: float,
    alpha_size: float,
    min_ratio: float = 0.75,
) -> float | None:
    """BRAIN official SUB_UNIVERSE_SHARPE threshold formula.

    threshold = min_ratio × sqrt(sub_size / alpha_size) × sharpe
    """
    if (
        sharpe is None
        or sub_size is None
        or sub_size <= 0
        or alpha_size is None
        or alpha_size <= 0
    ):
        return None
    size_factor = math.sqrt(sub_size / alpha_size)
    return round(min_ratio * size_factor * sharpe, 4)


def fitness_crosscheck_formula(
    sharpe: float,
    returns: float,
    turnover: float,
    *,
    raw_turnover: float | None = None,
) -> float:
    """BRAIN official Fitness formula: Sharpe × sqrt(|Returns| / max(Turnover, 0.125)).

    IMPORTANT: BRAIN API returns turnover as raw decimal (e.g. 1.2 = 120%).
    This formula prefers raw_turnover when available, falling back to adjusted
    turnover to avoid display normalization affecting the calculation.
    """
    used_turnover = raw_turnover if (raw_turnover is not None and raw_turnover > 0) else turnover
    denominator = max(used_turnover, 0.125)
    ratio = abs(returns) / denominator
    return sharpe * math.sqrt(ratio)


def is_finite_float(value: Any) -> float | None:
    """Parse a value to a finite float, returning None for invalid/missing."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def safe_text(value: Any) -> str | None:
    """Coerce a value to non-empty text, returning None for empty/missing."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None

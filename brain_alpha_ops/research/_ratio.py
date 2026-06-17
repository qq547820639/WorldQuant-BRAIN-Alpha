"""Unified ratio normalization for BRAIN API metrics.

P0-4 fix (2026-06-13): four research modules used to define their own copy
of ``_ratio()`` with subtly different cutoffs. Phase 3 (2026-06-13)
corrects the unified threshold: the original Phase-2 implementation
chose ``abs >= 2.0`` as the unbounded cutoff, but that rule compressed
turnover values like ``125`` to ``1.25`` (125 / 100) — the opposite of
the "preserve turnover" goal. The correct unified rule mirrors the
pre-Phase-2 ``scoring._ratio`` semantics for the unbounded path and the
``experience._ratio`` / ``safety._ratio`` / ``diagnostics._ratio``
semantics for the bounded path:

* **Unbounded** (default): a value is treated as a percentage **only**
  when ``abs(value) >= 100.0``. This is the historical ``scoring`` rule
  and it is the only rule that simultaneously preserves turnover
  (``2.5 → 2.5``), normalises legacy percentage fields (``125 → 1.25``)
  and rejects out-of-range decimals (``0.7 → 0.7``).
* **Bounded** (``bounded=True``): also divide by 100 for values in
  ``1.0 < abs(value) < 100.0``. This is the historical ``scoring``
  ``bounded=True`` rule, which catches the cases where the BRAIN API
  returned a percentage (e.g. ``70``) for a metric that is naturally
  bounded in ``[0, 1]`` (drawdown, correlation, weight concentration).

Comparison with the historical per-module behaviours:

| Input                       | scoring (pre-Phase-2) | experience / safety / diagnostics | New unified |
|-----------------------------|-----------------------|------------------------------------|-------------|
| ``0.7`` (decimal)           | 0.7                   | 0.7                                | 0.7         |
| ``0.5``                     | 0.5                   | 0.5                                | 0.5         |
| ``2.5`` (turnover)          | 2.5                   | 0.025 (bug)                        | 2.5         |
| ``70`` (percentage)         | 70 (bug)              | 0.7                                | 70          |
| ``70, bounded=True``        | 0.7                   | 0.7                                | 0.7         |
| ``125`` (large percentage)  | 1.25                  | 1.25                               | 1.25        |
| ``1.5, bounded=True``       | 0.015                 | 1.5 (bug)                          | 0.015       |

The "bounded" flag exists for callers that need to opt into the
stricter percentage heuristic for mathematically-bounded metrics.
"""
from __future__ import annotations

from typing import Any

def _coerce_float(value: Any) -> float:
    """Best-effort float coercion that never raises."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0

def normalize_brain_ratio(value: Any, *, bounded: bool = False) -> float:
    """Normalize a BRAIN API ratio metric.

    Args:
        value: raw metric value (possibly percentage, possibly decimal,
            possibly ``None`` or a string).
        bounded: when ``True``, also divide by 100 for values in the
            ``1.0 < abs(value) < 100.0`` range. Use this for metrics
            that are mathematically clamped to ``[0, 1]`` (drawdown,
            correlation, weight concentration).

    Returns:
        The metric in decimal form, or 0.0 for unparseable / missing
        input.
    """
    numeric = _coerce_float(value)
    if numeric == 0.0:
        return 0.0
    abs_numeric = abs(numeric)
    # Unbounded: preserve free-range metrics (turnover, sharpe, fitness).
    # Bounded: re-scale 1.0 < abs < 100 percentages back to decimals.
    if abs_numeric >= 100.0 or (bounded and abs_numeric > 1.0):
        return numeric / 100.0
    return numeric

# Convenience alias matching the historical local name in scoring.py / safety.py
_ratio = normalize_brain_ratio

__all__ = ["normalize_brain_ratio", "_ratio"]

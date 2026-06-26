"""Operator signatures, templates, and field-pool constants for the validated generator.

These constants are authoritative from BRAIN official docs and are consumed by
the validation and prefilter sub-modules.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("brain_alpha_ops.research.validated_generator")

# ═══════════════════════════════════════════════════════════════════
# P0: Operator signatures — authoritative from BRAIN official docs
# ═══════════════════════════════════════════════════════════════════

OPERATOR_SIGNATURES: dict[str, dict[str, Any]] = {
    # Cross-sectional
    "rank":           {"params": ["x"],   "category": "cross_sectional"},
    "zscore":         {"params": ["x"],   "category": "cross_sectional"},
    "scale":          {"params": ["x"],   "category": "cross_sectional"},
    "group_rank":     {"params": ["x", "sector"], "category": "cross_sectional"},
    "group_zscore":   {"params": ["x", "sector"], "category": "cross_sectional"},
    "group_neutralize":{"params": ["x", "sector"], "category": "cross_sectional"},
    # Transformation / sanitization
    "winsorize":      {"params": ["x", "std"], "category": "transformation"},
    "truncate":       {"params": ["x", "limit"], "category": "transformation"},
    # Time series (2-param)
    "ts_mean":         {"params": ["x", "d"], "category": "time_series"},
    "ts_std_dev":          {"params": ["x", "d"], "category": "time_series"},
    "ts_sum":          {"params": ["x", "d"], "category": "time_series"},
    "ts_delta":        {"params": ["x", "d"], "category": "time_series"},
    "ts_delay":        {"params": ["x", "d"], "category": "time_series"},
    "ts_rank":         {"params": ["x", "d"], "category": "time_series"},"ts_kurtosis":     {"params": ["x", "d"], "category": "time_series"},
    "ts_decay_linear": {"params": ["x", "d"], "category": "time_series"},
    "ts_zscore":       {"params": ["x", "d"], "category": "time_series"},
    # Time series (3-param)
    "ts_corr":  {"params": ["x", "y", "d"], "category": "time_series"},
    "ts_cov":   {"params": ["x", "y", "d"], "category": "time_series"},
    # Vector
    "abs":   {"params": ["x"],    "category": "vector"},
    "sign":  {"params": ["x"],    "category": "vector"},
    "log":   {"params": ["x"],    "category": "vector"},
    "max":   {"params": ["x", "y"], "category": "vector"},
    "min":   {"params": ["x", "y"], "category": "vector"},
}

# Window constraints per operator
WINDOW_CONSTRAINTS: dict[str, dict[str, int]] = {
    "winsorize":       {"min": 1,  "max": 5},
    "truncate":        {"min": 1,  "max": 10},
    "ts_mean":         {"min": 2,  "max": 252},
    "ts_std_dev":          {"min": 5,  "max": 252},
    "ts_sum":          {"min": 2,  "max": 252},
    "ts_delta":        {"min": 1,  "max": 120},
    "ts_delay":        {"min": 1,  "max": 120},
    "ts_rank":         {"min": 5,  "max": 252},
    "ts_corr":         {"min": 10, "max": 252},
    "ts_cov":          {"min": 10, "max": 252},"ts_kurtosis":     {"min": 10, "max": 252},
    "ts_decay_linear": {"min": 2,  "max": 120},
    "ts_zscore":       {"min": 5,  "max": 252},
}

# ═══════════════════════════════════════════════════════════════════
# P0: Field whitelist — loaded from official_fields.json
# ═══════════════════════════════════════════════════════════════════
SAFE_FIELDS: set[str] = set()


# ═══════════════════════════════════════════════════════════════════
# Validated templates — each template verified against operator signatures
# ═══════════════════════════════════════════════════════════════════

# Round 5: expanded from 10 to 55 templates with logical pairings + stratified windows + deep nesting

TEMPLATES: dict[str, list[tuple[str, list[str]]]] = {
    "momentum": [
        ("rank(ts_delta({f1}, {d1}))",                                    ["f1", "d1"]),
        ("rank(ts_delta({f1}, {d1}) / ts_std_dev({f2}, {d2}))",           ["f1", "d1", "f2", "d2"]),
        ("rank(ts_sum({f1}, {d1}))",                                       ["f1", "d1"]),
        ("rank(ts_rank({f1}, {d1}))",                                      ["f1", "d1"]),
        ("rank(ts_mean({f1}, {d1}))",                                      ["f1", "d1"]),
        ("rank(ts_sum(ts_delta({f1}, {d1}), {d2}))",                       ["f1", "d1", "d2"]),
        ("zscore(ts_delta({f1}, {d1}))",                                   ["f1", "d1"]),
        ("rank(ts_decay_linear({f1}, {d1}))",                               ["f1", "d1"]),
    ],
    "reversal": [
        ("-rank(ts_delta({f1}, {d1}))",                                    ["f1", "d1"]),
        ("-rank(ts_sum({f1}, {d1}))",                                       ["f1", "d1"]),
        ("rank(-ts_delta({f1}, {d1}))",                                    ["f1", "d1"]),
        ("-rank(ts_rank({f1}, {d1}))",                                      ["f1", "d1"]),
        ("rank(ts_delay({f1}, {d1}) - {f1})",                               ["f1", "d1"]),
        ("-zscore(ts_delta({f1}, {d1}))",                                   ["f1", "d1"]),
    ],
    "volume_reversal": [
        ("-rank(ts_zscore({f1}, {d1}) * ts_delta({f2}, {d2}))",           ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_delta({f1}, {d1}) * ts_delta({f2}, {d2}))",            ["f1", "d1", "f2", "d2"]),
        ("-rank(ts_delta({f1}, {d1}) * ts_mean({f2}, {d2}))",             ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_sum({f1}, {d1}) / ts_std_dev({f2}, {d2}))",            ["f1", "d1", "f2", "d2"]),
        ("-rank(ts_rank({f1}, {d1}) * zscore(ts_delta({f2}, {d2})))",     ["f1", "d1", "f2", "d2"]),
    ],
    "volatility": [
        ("rank(-ts_std_dev({f1}, {d1}))",                                   ["f1", "d1"]),
        ("-rank(ts_std_dev({f1}, {d1}))",                                   ["f1", "d1"]),
        ("-rank(ts_std_dev({f1}, {d1}) / ts_mean({f2}, {d2}))",            ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_std_dev({f1}, {d1}) * zscore({f1}))",                   ["f1", "d1"]),
        ("rank(ts_zscore({f1}, {d1}) / ts_std_dev({f1}, {d1}))",           ["f1", "d1"]),
    ],
    "mean_reversion": [
        ("-rank(ts_delta({f1}, {d1}) / ts_std_dev({f2}, {d2}))",           ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_delta({f1}, {d1}))",                                    ["f1", "d1"]),
        ("-rank(ts_zscore({f1}, {d1}))",                                     ["f1", "d1"]),
        ("-rank(({f1} - ts_mean({f1}, {d1})) / ts_std_dev({f1}, {d1}))",  ["f1", "d1"]),
        ("-rank(ts_decay_linear(ts_delta({f1}, {d1}), {d2}))",             ["f1", "d1", "d2"]),
    ],
    "value": [
        ("rank({f1})",                                                      ["f1"]),
        ("rank(zscore({f1}))",                                              ["f1"]),
        ("rank(-{f1})",                                                     ["f1"]),
        ("rank(zscore(-{f1}))",                                             ["f1"]),
    ],
    "quality": [
        ("rank(ts_mean({f1}, {d1}))",                                       ["f1", "d1"]),
        ("zscore(ts_mean({f1}, {d1}))",                                     ["f1", "d1"]),
        ("rank(ts_mean({f1}, {d1}) / ts_std_dev({f1}, {d1}))",             ["f1", "d1"]),
        ("rank(zscore(ts_mean({f1}, {d1})))",                                ["f1", "d1"]),
    ],
    "hybrid": [
        ("rank(ts_delta({f1}, {d1})) + rank(ts_delta({f2}, {d2}))",        ["f1", "d1", "f2", "d2"]),
        ("rank(ts_mean({f1}, {d1})) * rank(-ts_std_dev({f2}, {d2}))",      ["f1", "d1", "f2", "d2"]),
        ("rank(zscore({f1})) * rank(ts_delta({f2}, {d1}))",                ["f1", "f2", "d1"]),
        ("-rank(ts_delta({f1}, {d1}) * ts_zscore({f2}, {d2}))",            ["f1", "d1", "f2", "d2"]),
        ("zscore(ts_delta({f1}, {d1})) + zscore(-ts_std_dev({f2}, {d2}))", ["f1", "d1", "f2", "d2"]),
        ("rank(ts_sum({f1}, {d1}) + ts_delta({f2}, {d2}))",                ["f1", "d1", "f2", "d2"]),
    ],
    "deep_nested": [
        ("rank(ts_delta(ts_mean({f1}, {d1}), {d2}))",                       ["f1", "d1", "d2"]),
        ("rank(ts_mean(ts_delta({f1}, {d1}), {d2}))",                        ["f1", "d1", "d2"]),
        ("-rank(ts_std_dev(ts_delta({f1}, {d1}), {d2}))",                   ["f1", "d1", "d2"]),
        ("zscore(ts_delta(ts_mean({f1}, {d1}), {d2}))",                      ["f1", "d1", "d2"]),
        ("rank(ts_zscore(ts_delta({f1}, {d1}), {d2}))",                      ["f1", "d1", "d2"]),
    ],
    # ── P0-8 additions: new strategy families ──
    "growth": [
        ("rank(ts_delta({f1}, {d1}) / ts_mean({f1}, {d1}))",               ["f1", "d1"]),
        ("rank(ts_delta({f1}, {d1}) / ts_std_dev({f1}, {d1}))",            ["f1", "d1"]),
        ("zscore(ts_delta({f1}, {d1}) / ts_mean({f1}, {d2}))",             ["f1", "d1", "d2"]),
        ("rank(ts_decay_linear(ts_delta({f1}, {d1}), {d2}))",               ["f1", "d1", "d2"]),
        ("rank(ts_delta({f1}, {d1}) * ts_delta({f2}, {d2}))",              ["f1", "d1", "f2", "d2"]),
    ],
    "liquidity": [
        ("-rank(ts_delta({f1}, {d1}) / ts_std_dev({f1}, {d2}))",           ["f1", "d1", "d2"]),
        ("rank(-ts_std_dev({f1}, {d1}) * ts_delta({f2}, {d2}))",           ["f1", "d1", "f2", "d2"]),
        ("-rank(ts_rank({f1}, {d1}) * zscore(ts_delta({f2}, {d2})))",      ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_zscore({f1}, {d1}) / ts_mean({f2}, {d2}))",             ["f1", "d1", "f2", "d2"]),
    ],
    "stat_arb": [
        ("rank(ts_corr({f1}, {f2}, {d1}))",                                  ["f1", "f2", "d1"]),
        ("rank(({f1} - ts_mean({f1}, {d1})) / ts_std_dev({f2}, {d1}))",    ["f1", "f2", "d1"]),
        ("rank(zscore({f1}) - ts_mean(zscore({f2}), {d1}))",               ["f1", "f2", "d1"]),
        ("-rank(zscore({f1}) + zscore({f2}))",                               ["f1", "f2"]),
    ],
    "cross_sectional": [
        ("group_rank(ts_delta({f1}, {d1}), {f2})",                          ["f1", "d1", "f2"]),
        ("group_neutralize(zscore({f1}), {f2})",                            ["f1", "f2"]),
        ("group_rank({f1}, {f2})",                                          ["f1", "f2"]),
        ("rank(zscore({f1}) - group_neutralize(zscore({f1}), {f2}))",      ["f1", "f2"]),
    ],
}

# Logical field pool names. Values are injected from official context at runtime.
FIELD_POOLS: dict[str, list[str]] = {
    "price": [],
    "volume": [],
    "returns": [],
    "value": [],
    "momentum": [],
    "volatility": [],
    "fundamental": [],
    "analyst": [],
    "cashflow": [],
    "quality": [],
}

# Logical field pairings for 2-field templates: (pool_for_f1, pool_for_f2)
FIELD_PAIRINGS = [
    (["price", "volume"],        ["returns", "volatility"]),
    (["price", "volatility"],    ["volume", "returns"]),
    (["momentum"],               ["value", "returns"]),
    (["volume", "price"],        ["returns", "momentum"]),
    (["price", "value"],         ["volatility", "returns"]),
    # P0-8 additions — cross-family pairings for diversity
    (["price", "volume"],        ["fundamental", "analyst"]),
    (["fundamental"],            ["returns", "volatility"]),
    (["analyst", "cashflow"],    ["price", "momentum"]),
    (["price", "fundamental"],   ["volume", "quality"]),
    (["fundamental", "analyst"], ["value", "returns"]),
    (["cashflow"],               ["price", "volatility"]),
]

# Stratified window pools — short, medium, long
WINDOW_POOL: list[int] = [1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 60, 90, 120]
SHORT_WINDOWS: list[int] = [1, 2, 3, 5, 7]
MEDIUM_WINDOWS: list[int] = [10, 15, 20, 30]
LONG_WINDOWS: list[int] = [40, 60, 90, 120]


# ═══════════════════════════════════════════════════════════════════
# Dynamic safe-fields injection point
# ═══════════════════════════════════════════════════════════════════
# Override SAFE_FIELDS at runtime with live-verified fields from pipeline:
#   from brain_alpha_ops.research.validated_generator import set_active_safe_fields
#   set_active_safe_fields(production_context["safe_fields"])

_ACTIVE_SAFE_FIELDS: set[str] | None = None
_ACTIVE_FIELD_POOLS: dict[str, list[str]] | None = None
_ACTIVE_STATE_LOCK = threading.Lock()


def get_active_safe_fields() -> set[str]:
    """Return the currently active safe-fields set."""
    with _ACTIVE_STATE_LOCK:
        if _ACTIVE_SAFE_FIELDS is not None:
            return set(_ACTIVE_SAFE_FIELDS)
    try:
        from brain_alpha_ops.data import OfficialDataLoader

        return {
            str(getattr(field, "id", "") or getattr(field, "name", "") or "").strip()
            for field in OfficialDataLoader.instance().get_fields()
            if str(getattr(field, "id", "") or getattr(field, "name", "") or "").strip()
        }
    except Exception:
        return set()


def get_active_field_pools() -> dict[str, list[str]]:
    """Return official field pools for generation without static field fallback."""
    with _ACTIVE_STATE_LOCK:
        if _ACTIVE_FIELD_POOLS is not None:
            return {key: list(value) for key, value in _ACTIVE_FIELD_POOLS.items()}
    fields = sorted(get_active_safe_fields())
    if not fields:
        return {}
    return {pool_name: list(fields) for pool_name in FIELD_POOLS}


def set_active_safe_fields(field_ids: list[str], field_pools: dict[str, list[str]] | None = None) -> None:
    """Inject live-verified fields from production context.

    Called by pipeline after authenticating and discovering available fields.
    If never called, local official_fields.json is used; unavailable context
    returns an empty set so validation fails closed.
    """
    global _ACTIVE_SAFE_FIELDS, _ACTIVE_FIELD_POOLS
    with _ACTIVE_STATE_LOCK:
        _ACTIVE_SAFE_FIELDS = set(field_ids)
        if field_pools is not None:
            _ACTIVE_FIELD_POOLS = dict(field_pools)

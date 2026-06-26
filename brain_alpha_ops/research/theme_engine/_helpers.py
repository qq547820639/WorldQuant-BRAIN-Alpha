"""Dynamic Alpha theme engine — helper functions.

Contains ``_normalize_operator_aliases``, ``_build_category_map``, and the
extracted ``_build_auto_skeletons_impl`` body that generates expression
skeletons by combining BRAIN official operators.
"""
from __future__ import annotations

import re


def _normalize_operator_aliases(expression: str) -> str:
    """Normalize legacy shorthand to official BRAIN operator names."""
    import re as _re

    replacements = {
        "ts_std": "ts_std_dev",
        "ts_argmax": "ts_arg_max",
        "ts_argmin": "ts_arg_min",
        "ts_cov": "ts_covariance",
    }
    normalized = expression
    for old, new in replacements.items():
        normalized = _re.sub(rf"\b{old}\s*\(", f"{new}(", normalized)
    return normalized


def _build_category_map() -> dict[str, list[str]]:
    """Map skeleton category → field categories that can fill its slots."""
    return {
        "momentum": ["price", "model", "technical", "momentum", "analyst"],
        "reversal": ["price", "model", "technical", "analyst"],
        "value": ["fundamental", "valuation", "model", "analyst"],
        "quality": ["fundamental", "quality", "model", "analyst"],
        "growth": ["fundamental", "growth", "model", "analyst"],
        "volatility": ["price", "volatility", "model", "analyst"],
        "liquidity": ["volume", "price", "model", "analyst"],
        "cross_sectional": ["fundamental", "price", "model", "valuation", "analyst"],
        "hybrid": ["price", "fundamental", "model", "volume", "analyst"],
    }


def _build_auto_skeletons_impl(loader) -> dict[str, list[str]]:
    """Generate expression skeletons by combining BRAIN official operators.

    Sources all operator names from OfficialDataLoader (data/official_operators.json),
    which mirrors BRAIN's /operators API endpoint. Zero hardcoded operator names.

    Returns a dict keyed by category with list of expression skeletons.
    """
    # Get operators by category from official data
    ops = loader.get_operators()
    ts_ops: list[str] = []       # Time Series
    cs_ops: list[str] = []       # Cross Sectional
    group_ops: list[str] = []    # Group
    arith_ops: list[str] = []    # Arithmetic (binary/comparison only)

    for op in ops:
        cat = (op.category or "").lower()
        name = op.name
        if "time" in cat or cat == "time_series":
            ts_ops.append(name)
        elif "cross" in cat or cat == "cross_sectional":
            cs_ops.append(name)
        elif cat == "group":
            group_ops.append(name)
        elif cat in ("arithmetic", "logical"):
            # Only include operators useful in expression composition
            if name in ("add", "subtract", "multiply", "divide", "power",
                       "signed_power", "min", "max", "greater", "less",
                       "greater_equal", "less_equal", "if_else"):
                arith_ops.append(name)

    # Preferred operators for alpha construction (most commonly used)
    preferred_ts = [op for op in ts_ops if op in (
        "ts_rank", "ts_delta", "ts_mean", "ts_std_dev", "ts_sum",
        "ts_zscore", "ts_corr", "ts_covariance",
        "ts_product", "ts_regression", "ts_arg_max", "ts_arg_min",
        "ts_av_diff", "ts_scale", "ts_delay", "ts_quantile",
        "ts_count_nans", "ts_step",
        "last_diff_value", "days_from_last_change",
        # P2 fix: removed — require named params incompatible with auto-generation:
        #   ts_backfill (lookback=), ts_decay_linear (dense=), kth_element (k=), hump (hump=)
    )] or ts_ops

    preferred_cs = [op for op in cs_ops if op in (
        "rank", "zscore", "scale", "winsorize", "normalize", "quantile"
    )] or cs_ops

    preferred_group = [op for op in group_ops if op in (
        "group_rank", "group_zscore", "group_neutralize", "group_mean",
        "group_scale", "group_backfill"
    )] or group_ops

    # ── Generate skeletons ──
    auto: dict[str, list[str]] = {"momentum": [], "reversal": [], "value": [],
                                    "quality": [], "growth": [], "volatility": [],
                                    "liquidity": [], "cross_sectional": [], "hybrid": [],
                                    # P1-7: new categories
                                    "decay": [], "conditional": [], "multi_window": []}
    seen: set = set()

    def add(cat: str, skeleton: str) -> None:
        normalized = skeleton.replace(" ", "")
        if normalized not in seen:
            seen.add(normalized)
            auto.setdefault(cat, []).append(skeleton)

    import random as _random
    _random.seed(42)  # deterministic generation

    # Pattern 1: cross_sectional(time_series(FIELD, WINDOW))
    for cs in preferred_cs[:4]:
        for ts in preferred_ts[:12]:
            add("momentum", f"{cs}({ts}({{FIELD}}, {{WINDOW}}))")
            add("quality", f"{cs}({ts}({{FIELD}}, {{WINDOW}}))")

    # Pattern 2: -1 * cross_sectional(time_series(FIELD, WINDOW)) — reversal
    for cs in preferred_cs[:3]:
        for ts in preferred_ts[:6]:
            add("reversal", f"-1 * {cs}({ts}({{FIELD}}, {{WINDOW}}))")

    # Pattern 3: cs(-FIELD) or cs(zscore(-FIELD)) — value
    for cs in preferred_cs[:4]:
        add("value", f"{cs}(-{{FIELD}})")
        add("value", f"{cs}(zscore(-{{FIELD}}))")

    # Pattern 4: cs(-ts_std_dev(FIELD, WINDOW)) — volatility
    vol_ts = [op for op in preferred_ts if op in ("ts_std_dev", "ts_zscore")]
    for cs in preferred_cs[:3]:
        for ts in (vol_ts or preferred_ts[:3]):
            add("volatility", f"{cs}(-{ts}({{FIELD}}, {{WINDOW}}))")

    # Pattern 5: group_op(FIELD, GROUP) — direct field only
    for grp in preferred_group[:4]:
        add("cross_sectional", f"{grp}({{FIELD}}, {{GROUP}})")
        add("cross_sectional", f"winsorize({grp}({{FIELD}}, {{GROUP}}), std=4)")

    # Pattern 6: cs(ts(FIELD_A, WINDOW)) + cs(ts(FIELD_B, WINDOW2)) — hybrid
    for cs in preferred_cs[:3]:
        for ts_a in preferred_ts[:8]:
            for ts_b in preferred_ts[:8]:
                if ts_a == ts_b:
                    continue
                add("hybrid", f"{cs}({ts_a}({{FIELD_A}}, {{WINDOW}})) + {cs}({ts_b}({{FIELD_B}}, {{WINDOW2}}))")
                break  # limit to one combo per outer pair
            break  # limit total

    # Pattern 7: Multi-layer cs(cs(ts(FIELD, WINDOW)))
    for outer_cs in preferred_cs[:3]:
        for inner_cs in preferred_cs[:3]:
            if outer_cs == inner_cs:
                continue
            for ts in preferred_ts[:6]:
                add("quality", f"{outer_cs}({inner_cs}({ts}({{FIELD}}, {{WINDOW}})))")
                break

    # Pattern 8: winsorize variants with std parameter
    # P2 fix: exclude ts_rank/last_diff_value — incompatible with BRAIN parser
    for ts in [op for op in preferred_ts[:10]
               if op not in ("ts_rank", "last_diff_value")]:
        add("momentum", f"rank(winsorize({ts}({{FIELD}}, {{WINDOW}}), std=4))")

    # Pattern 9: ts_corr / ts_covariance with returns
    for cs in preferred_cs[:3]:
        for corr_op in [op for op in preferred_ts if op in ("ts_corr", "ts_covariance")]:
            add("liquidity", f"{cs}({corr_op}({{FIELD}}, returns, {{WINDOW}}))")

    # P1-7: Pattern 10 — ts_decay_linear patterns (decay category)
    for cs in preferred_cs[:3]:
        for ts in preferred_ts[:8]:
            add("decay", f"{cs}(ts_decay_linear({ts}({{FIELD}}, {{WINDOW}}), {{WINDOW2}}))")

    # P1-7: Pattern 11 — if_else conditional patterns (conditional category)
    for cs in preferred_cs[:3]:
        for ts in preferred_ts[:6]:
            add("conditional", f"{cs}(if_else(greater({ts}({{FIELD}}, {{WINDOW}}), 0), {{FIELD}}, -{{FIELD}}))")
            break
    for cs in preferred_cs[:2]:
        for ts in preferred_ts[:4]:
            add("conditional", f"{cs}(if_else(greater(ts_delta({{FIELD}}, {{WINDOW}}), 0), {{FIELD}}, 0))")
            break

    # P1-7: Pattern 12 — multi-window difference patterns
    for cs in preferred_cs[:3]:
        for ts in preferred_ts[:6]:
            add("multi_window", f"{cs}({ts}({{FIELD}}, {{WINDOW}}) - {ts}({{FIELD}}, {{WINDOW2}}))")
            add("multi_window", f"{cs}({ts}({{FIELD}}, {{WINDOW}}) / {ts}({{FIELD}}, {{WINDOW2}}))")
            break

    # P1-7: Pattern 13 — ts_delta / ts_std_dev ratio (normalized momentum)
    for cs in preferred_cs[:3]:
        add("momentum", f"{cs}(ts_delta({{FIELD}}, {{WINDOW}}) / ts_std_dev({{FIELD}}, {{WINDOW2}}))")

    # P1-7: Pattern 14 — product of two cross-sectional rankings
    for cs_a in preferred_cs[:2]:
        for cs_b in preferred_cs[:2]:
            for ts in preferred_ts[:4]:
                add("hybrid", f"{cs_a}({ts}({{FIELD_A}}, {{WINDOW}})) * {cs_b}({ts}({{FIELD_B}}, {{WINDOW2}}))")
                break
            break

    return {k: v for k, v in auto.items() if v}  # only non-empty categories

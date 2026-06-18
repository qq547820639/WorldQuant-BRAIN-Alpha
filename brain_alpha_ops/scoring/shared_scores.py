"""Shared scoring helpers used by runtime scoring and calibration tools."""

from __future__ import annotations

import re
from typing import Any

DEFAULT_PRIOR_WEIGHTS: dict[str, float] = {
    "economic_logic": 0.18,
    "structure": 0.14,
    "field_operator_support": 0.16,
    "data_compliance": 0.12,
    "horizon_turnover_proxy": 0.14,
    "risk_control_proxy": 0.14,
    "diversity": 0.07,
    "explainability": 0.05,
}


def normalize_family_label(family: Any) -> str:
    """Return a stable family label for scoring comparisons."""
    return str(family or "").strip().lower()


def economic_logic_score(
    hypothesis: str,
    expression: str,
    fields: set[str],
    operators: list[str],
) -> dict[str, Any]:
    """Evaluate Alpha economic-logic quality via keyword concept detection."""
    text = f"{hypothesis} {expression} {' '.join(fields)} {' '.join(operators)}".lower()

    concepts = {
        "momentum": {
            "keywords": ["momentum", "trend", "ts_delta", "ts_rank", "ts_mean",
                         "moving_average", "breakout", "continuation"],
        },
        "mean_reversion": {
            "keywords": ["reversal", "mean_revert", "zscore", "ts_zscore",
                         "overbought", "oversold", "-ts_", "bounce", "revert"],
        },
        "value": {
            "keywords": ["value", "cheap", "undervalue", "pe_ratio", "pb_ratio",
                         "market_cap", "book", "dividend_yield", "earnings_yield"],
        },
        "quality": {
            "keywords": ["quality", "profit", "margin", "roe", "roa",
                         "stable", "fundamental", "balance_sheet"],
        },
        "volatility": {
            "keywords": ["volatility", "vol", "ts_std", "std", "ivol",
                         "beta", "risk", "variance", "uncertainty"],
        },
        "liquidity": {
            "keywords": ["liquidity", "volume", "turn", "adv", "vwap",
                         "bid", "spread", "depth", "market_impact"],
        },
        "growth": {
            "keywords": ["growth", "earnings", "revenue", "sales_growth",
                         "expansion", "accelerat"],
        },
        "risk_management": {
            "keywords": ["winsorize", "truncation", "neutralize", "group_neutralize",
                         "hedge", "sector_neutral", "risk_adjust"],
        },
        "cross_sectional": {
            "keywords": ["cross_section", "rank", "group_rank", "sector",
                         "industry", "subindustry", "relative", "peer"],
        },
    }

    detected = [
        concept_name
        for concept_name, info in concepts.items()
        # TODO S-12: prefer \b word-boundary regex over substring match
            if any(keyword in text for keyword in info["keywords"])
    ]

    if not detected:
        if len(hypothesis) >= 60:
            return {"score": 52, "concepts_detected": [], "source": "length_fallback"}
        return {"score": 40, "concepts_detected": [], "source": "insufficient"}

    concept_count = len(detected)
    if concept_count >= 4:
        score = 92
    elif concept_count == 3:
        score = 85
    elif concept_count == 2:
        score = 78
    else:
        score = 68

    return {
        "score": score,
        "concepts_detected": detected,
        "source": "keyword_concept_detection",
    }


def default_prior_dimensions(
    *,
    expression: str,
    fields: set[str],
    operators: list[str],
    hypothesis: str,
    family: str,
    economic_result: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Compute the default eight prior-score dimensions."""
    windows = [int(value) for value in re.findall(r"\b\d+\b", expression)]  # TODO S-13: only extract windows from ts_* calls, not all integers
    has_cross_section = any(op in operators for op in ("rank", "zscore", "scale", "group_rank", "group_zscore"))
    has_time_series = any(op.startswith("ts_") for op in operators)
    has_risk_control = any(op in operators for op in ("winsorize", "zscore", "scale", "group_rank")) or "adv20" in fields
    median_window = sorted(windows)[len(windows) // 2] if windows else 0
    economic_result = economic_result or economic_logic_score(hypothesis, expression, fields, operators)
    family_key = normalize_family_label(family)

    return {
        "economic_logic": economic_result["score"],
        "structure": max(25, 90 - max(0, len(operators) - 4) * 8),
        "field_operator_support": min(92, 42 + len(fields) * 8 + len(set(operators)) * 4),
        "data_compliance": 82 if fields else 35,
        "horizon_turnover_proxy": 82 if 5 <= median_window <= 90 else 68 if median_window else 50,
        "risk_control_proxy": 84 if has_cross_section and has_time_series and has_risk_control else 66 if has_cross_section and has_time_series else 48,
        "diversity": 80 if family_key in {"liquidity", "volatility", "hybrid"} else 65,
        "explainability": 85 if len(expression) < 140 else 60,
    }

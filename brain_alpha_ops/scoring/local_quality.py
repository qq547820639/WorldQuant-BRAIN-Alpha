"""Local quality prefilter scoring heuristics for candidate evaluation."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import (
    ordered_operators,
    profile_expression,
)
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
)

if TYPE_CHECKING:
    from brain_alpha_ops.data import OfficialDataLoader

logger = logging.getLogger(__name__)


@dataclass
class LocalQualityConfig:
    """Configuration for local_quality() scoring heuristics."""
    base_score: float = 55.0
    penalty_no_fields: float = 30.0
    penalty_no_operators: float = 20.0
    penalty_nesting_depth: float = 15.0
    max_nesting_depth: int = 8
    penalty_expression_length: float = 10.0
    max_expression_length: int = 220
    penalty_no_standardization: float = 12.0
    penalty_price_level_no_return: float = 8.0
    penalty_weak_hypothesis: float = 8.0
    min_hypothesis_length: int = 20
    penalty_sell_risk: float = 35.0
    field_bonus_per_field: float = 2.0
    field_bonus_cap: int = 10
    bonus_operators: dict = field(default_factory=lambda: {
        "ts_mean": 8, "ts_decay_linear": 8,
        "ts_std_dev": 4, "ts_rank": 4, "ts_sum": 4,
        "adv20": 4, "vwap": 4,
    })


# ------------------------------------------------------------------
# Field / operator extraction
# ------------------------------------------------------------------

def extract_fields(expression: str, known_fields: set[str] | None = None) -> list[str]:
    """Extract field names from *expression* that match *known_fields*.

    Args:
        expression: Alpha expression string to profile.
        known_fields: Optional pre-resolved set of known field IDs (lowercased).
            If None, fetches from OfficialDataLoader.

    Returns:
        Sorted list of field name strings present in both the expression
        and the known fields set. Returns empty list when field metadata
        is unavailable. Note: returned field names are lowercased — original
        case information is not preserved.
    """
    profile = profile_expression(expression)
    if known_fields is None:
        try:
            from brain_alpha_ops.data import OfficialDataLoader
            loader = OfficialDataLoader.instance()
            known_fields = {f.id.lower() for f in loader.get_fields()}
        except Exception:
            logger.warning("official field metadata unavailable; field extraction fails closed", exc_info=True)
            return []
    tokens = {token.lower() for token in profile.fields}
    return sorted(known_fields & tokens)


def extract_operators(expression: str) -> list[str]:
    """Extract operator names (function-like tokens) from *expression*."""
    return ordered_operators(expression)


def nesting_depth(expression: str) -> int:
    """Compute maximum nesting depth of parentheses in *expression*."""
    profile = profile_expression(expression)
    return max(0, profile.max_depth - 1) if profile.parsed else profile.max_depth


# ------------------------------------------------------------------
# Local quality prefilter
# ------------------------------------------------------------------

def local_quality(
    candidate: Candidate,
    min_quality_level: float,
    config: LocalQualityConfig | None = None,
) -> dict:
    cfg = config or LocalQualityConfig()
    expression = candidate.expression
    score = cfg.base_score
    reasons = []
    profile = profile_expression(expression)
    fields = sorted({*list(candidate.data_fields or []), *extract_fields(expression), *profile.fields})
    operators = list(dict.fromkeys([*list(candidate.operators or []), *extract_operators(expression), *profile.operators]))
    depth = nesting_depth(expression)
    generation_risks = high_turnover_generation_risk_reasons(expression)

    if not fields:
        score -= cfg.penalty_no_fields
        reasons.append("no_known_data_field")
    else:
        score += min(cfg.field_bonus_cap, len(set(fields)) * cfg.field_bonus_per_field)

    if not operators:
        score -= cfg.penalty_no_operators
        reasons.append("no_operator")
    # BRAIN supports deeper nesting; 5 was too conservative.
    if depth > cfg.max_nesting_depth:
        score -= cfg.penalty_nesting_depth
        reasons.append("expression_too_nested")
    if len(expression) > cfg.max_expression_length:
        score -= cfg.penalty_expression_length
        reasons.append("expression_too_long")
    if not re.search(r"\b(rank|zscore|scale|group_rank|ts_)", expression):
        score -= cfg.penalty_no_standardization
        reasons.append("weak_standardization_or_time_series_structure")
    if re.search(r"\b(close|open|vwap)\b", expression) and "ts_delta" not in expression and "returns" not in expression:
        score -= cfg.penalty_price_level_no_return
        reasons.append("price_level_without_return_transform")
    if len(candidate.hypothesis.strip()) < cfg.min_hypothesis_length:
        score -= cfg.penalty_weak_hypothesis
        reasons.append("weak_research_hypothesis")
    for op_name, bonus in cfg.bonus_operators.items():
        if op_name in expression:
            score += bonus
    if generation_risks:
        score -= cfg.penalty_sell_risk
        reasons.extend("high_turnover_generation_risk:" + reason for reason in generation_risks)

    score = max(0.0, min(100.0, round(score, 2)))
    passed = score >= min_quality_level * 10 and not generation_risks
    return {
        "schema_version": "local-quality-v2",
        "score": score,
        "threshold": min_quality_level * 10,
        "passed": passed,
        "reasons": reasons or ["passed_local_prefilter"],
        "field_count": len(set(fields)),
        "operator_count": len(operators),
        "nesting_depth": depth,
    }

"""Prior-score and local-convergence scoring functions.

Contains ``prior_score`` (8-dimension weighted prior), ``_parameterized_dimensions``
(calibrated variant), and ``local_convergence_score`` (queueing score before
spending official API budget).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from brain_alpha_ops.config import ScoringConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.scoring.shared_scores import (
    DEFAULT_PRIOR_WEIGHTS,
    default_prior_dimensions,
    economic_logic_score,
    normalize_family_label,
)

from ._helpers import _bounded_score

if TYPE_CHECKING:
    from brain_alpha_ops.research.scoring_params import ScoringParams

_economic_logic_score = economic_logic_score


def prior_score(
    candidate: Candidate,
    weights_override: dict | None = None,
    params: "ScoringParams | None" = None,
) -> dict:
    """Prior score as a weighted combination of 8 dimensions.

    Args:
        candidate: candidate Alpha
        weights_override: optional dimension weight overrides for backward compatibility
        params: calibratable scoring parameters. None keeps the hard-coded
                formulas for backward compatibility; otherwise parameterized
                formulas are used and params weights take priority.

    Returns:
        {"score": float, "dimensions": dict, "weights": dict, "source": str}
    """
    expression = candidate.expression or ""
    fields = {str(field).lower() for field in (candidate.data_fields or [])}
    operators = [str(operator) for operator in (candidate.operators or [])]

    # P0 improvement: economic_logic now uses keyword concept scoring, not binary scoring.
    economic_result = economic_logic_score(
        candidate.hypothesis, expression, fields, operators
    )

    # Dimension scoring: prefer parameterized formulas.
    if params:
        windows = [int(value) for value in re.findall(r"\b\d+\b", expression)]
        has_cross_section = any(op in operators for op in ("rank", "zscore", "scale", "group_rank", "group_zscore"))
        has_time_series = any(op.startswith("ts_") for op in operators)
        has_risk_control = any(op in operators for op in ("winsorize", "zscore", "scale", "group_rank")) or "adv20" in fields
        median_window = sorted(windows)[len(windows) // 2] if windows else 0
        dims = {"economic_logic": economic_result["score"]}
        dims.update(_parameterized_dimensions(
            params, fields, operators, windows, median_window,
            has_cross_section, has_time_series, has_risk_control,
            candidate, expression, economic_result,
        ))
    else:
        dims = default_prior_dimensions(
            expression=expression,
            fields=fields,
            operators=operators,
            hypothesis=candidate.hypothesis,
            family=candidate.family,
            economic_result=economic_result,
        )
    dims["economic_concepts"] = economic_result["concepts_detected"]

    # Weights: weights_override can inject calibration values; params is the second source.
    source_parts = ["经验"]
    default_weights = DEFAULT_PRIOR_WEIGHTS
    if params and not weights_override:
        # Extract calibrated weights from params.
        calib_weights = params.get_weights_override()
        if calib_weights:
            weights = dict(default_weights, **calib_weights)
            source_parts.append("校准")
        else:
            weights = dict(default_weights)
    else:
        weights = dict(default_weights, **(weights_override or {}))
        if weights_override:
            source_parts.append("校准覆盖")

    score = _bounded_score(sum(dims[key] * weights.get(key, 0) for key in dims if key in weights))
    return {
        "score": score,
        "dimensions": dims,
        "weights": weights,
        "source": "+".join(source_parts),
    }


def _parameterized_dimensions(
    params: "ScoringParams",
    fields: set, operators: list, windows: list,
    median_window: int, has_cs: bool, has_ts: bool, has_rc: bool,
    candidate: Candidate, expression: str, economic_result: dict,
) -> dict:
    """Compute dimension scores using ScoringParams."""
    dims = {}
    op_count = len(operators)
    unique_ops = len(set(operators))
    field_count = len(fields)

    # structure: max(floor, base_score - max(0, op_count - threshold) * penalty)
    p = params.get_dimension("structure")
    if p and p.enabled:
        dims["structure"] = max(p.floor, p.base_score - max(0, op_count - p.penalty_threshold) * p.penalty_per_unit)

    # field_operator_support: min(cap, max(floor, base + fields*bonus + ops*4))
    p = params.get_dimension("field_operator_support")
    if p and p.enabled:
        score = p.base_score + field_count * p.bonus_per_unit + unique_ops * 4
        dims["field_operator_support"] = min(p.cap, max(p.floor, score))

    # data_compliance: high if fields else low
    p = params.get_dimension("data_compliance")
    if p and p.enabled:
        dims["data_compliance"] = p.high_score if fields else p.low_score

    # horizon_turnover_proxy: three tiers (inside window / outside window / no data).
    p = params.get_dimension("horizon_turnover_proxy")
    if p and p.enabled:
        if not median_window:
            dims["horizon_turnover_proxy"] = p.score_no_data
        elif p.threshold_low <= median_window <= p.threshold_high:
            dims["horizon_turnover_proxy"] = p.score_in_range
        else:
            dims["horizon_turnover_proxy"] = p.score_out_range

    # risk_control_proxy: three-condition tiering.
    p = params.get_dimension("risk_control_proxy")
    if p and p.enabled:
        conditions = sum([has_cs, has_ts, has_rc])
        if conditions >= 3:
            dims["risk_control_proxy"] = p.tier_3_score
        elif conditions >= 2:
            dims["risk_control_proxy"] = p.tier_2_score
        else:
            dims["risk_control_proxy"] = p.tier_1_score

    # diversity: category match.
    p = params.get_dimension("diversity")
    if p and p.enabled:
        high_set = {normalize_family_label(value) for value in (p.high_value_set or [])}
        dims["diversity"] = p.high_score if normalize_family_label(candidate.family) in high_set else p.low_score

    # explainability: expression length threshold.
    p = params.get_dimension("explainability")
    if p and p.enabled:
        dims["explainability"] = p.score_in_range if len(expression) < p.threshold_high else p.score_out_range

    # economic_logic is already computed via shared keyword scoring.
    # (its keyword-based detection is hard to parameterize meaningfully)

    return dims


def local_convergence_score(
    candidate: Candidate,
    prior: dict | None = None,
    scoring: ScoringConfig | None = None,
) -> float:
    """Queueing score before spending official API budget."""

    prior = prior or prior_score(candidate)
    local_quality_score = float(candidate.local_quality.get("score", 0.0) or 0.0)
    if not candidate.local_quality:
        local_quality_score = prior["score"]
    # Read weights from ScoringConfig, falling back to the original 0.65/0.35.
    lw = scoring.get_local_weights() if scoring else {"prior": 0.65, "quality": 0.35}
    return _bounded_score(lw["prior"] * prior["score"] + lw["quality"] * local_quality_score)

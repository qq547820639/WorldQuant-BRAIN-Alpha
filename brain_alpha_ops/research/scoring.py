"""Structured scoring and production gates."""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING

from brain_alpha_ops.config import QualityThresholds, ScoringConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring_explainability import (
    scorecard_improvement_hints,
    scorecard_top_failures,
)
from brain_alpha_ops.scoring.attribution import build_attribution_tree
from brain_alpha_ops.scoring.shared_scores import (
    DEFAULT_PRIOR_WEIGHTS,
    default_prior_dimensions,
    economic_logic_score,
    normalize_family_label,
)
from brain_alpha_ops.research._ratio import _ratio
from brain_alpha_ops.scoring._score_comparisons import (
    fitness_crosscheck_formula,
)
from brain_alpha_ops.types import ScorecardDict

if TYPE_CHECKING:
    from brain_alpha_ops.research.scoring_params import ScoringParams


_economic_logic_score = economic_logic_score


def _format_empirical_failure(row: dict) -> str:
    return (
        f"{str(row.get('name', 'check'))} "
        f"{str(row.get('direction', '-'))} "
        f"{str(row.get('target', '-'))} "
        f"(actual: {row.get('actual', '-')})"
    )


def build_scorecard(
    candidate: Candidate,
    thresholds: QualityThresholds,
    scoring: ScoringConfig | None = None,
    params: "ScoringParams | None" = None,
    settings: dict | None = None,
) -> ScorecardDict:
    prior = prior_score(candidate, weights_override=scoring.prior_weights_override if scoring else None, params=params)
    effective_settings = _scorecard_settings(candidate, settings)
    empirical = empirical_score(candidate.official_metrics, thresholds, settings=effective_settings)
    checklist = submission_checklist(candidate, thresholds)
    base_local_rank_score = local_convergence_score(candidate, prior, scoring=scoring)
    guidance_adjustment = assistant_guidance_score_adjustment(candidate, scoring=scoring)
    local_rank_score = _bounded_score(base_local_rank_score + float(guidance_adjustment.get("adjustment", 0.0) or 0.0))
    official_verified = bool(candidate.official_metrics)

    # Three-layer weights from ScoringConfig, falling back to the original 30/45/25.
    lw = scoring.get_layer_weights() if scoring else {"prior": 0.30, "empirical": 0.45, "checklist": 0.25}
    if official_verified:
        total = _bounded_score(
            lw["prior"] * prior["score"]
            + lw["empirical"] * empirical["score"]
            + lw["checklist"] * checklist["score"]
        )
        score_basis = "official_verified"
    else:
        total = _bounded_score(local_rank_score)
        score_basis = "local_prior"
    scorecard = {
        "schema_version": "scorecard-v2.3",
        "total_score": total,
        "decision_band": decision_band(total, empirical.get("hard_gate_failed", False), scoring=scoring),
        "score_basis": score_basis,
        "local_rank_score": local_rank_score,
        "base_local_rank_score": base_local_rank_score,
        "layer_weights": lw,
        "prior": prior,
        "empirical": empirical,
        "submission_checklist": checklist,
        "assistant_guidance_adjustment": {
            **guidance_adjustment,
            "applied_to_total": (not official_verified and float(guidance_adjustment.get("adjustment", 0.0) or 0.0) != 0.0),
        },
        "confidence": estimate_score_confidence({"empirical": empirical, "score_basis": score_basis}) if official_verified else None,
        "calibration": {
            "prior_minus_empirical": round(prior["score"] - empirical["score"], 2)
            if official_verified
            else None,
            "sample_weight": 1.0 if official_verified else 0.25,
            "purpose": "Track whether local priors predict official outcomes over time.",
            "params_used": params is not None,
        },
        "settings_trace": effective_settings,
    }
    scorecard["attribution_tree"] = build_attribution_tree(scorecard).to_dict()
    scorecard["top_failures"] = scorecard_top_failures(scorecard)
    scorecard["improvement_hints"] = scorecard_improvement_hints(scorecard)
    return scorecard


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


def assistant_guidance_score_adjustment(
    candidate: Candidate,
    *,
    scoring: ScoringConfig | None = None,
) -> dict:
    """Small local-ranking adjustment from historical assistant-guidance outcomes.

    This is intentionally conservative and only affects the local queueing score
    in ``build_scorecard``. Official metrics still dominate once available.
    """
    submission = candidate.submission if isinstance(candidate.submission, dict) else {}
    digest = str(submission.get("assistant_guidance_digest") or "").strip()
    enabled = bool(getattr(scoring, "assistant_guidance_score_adjustment_enabled", True)) if scoring else True
    min_confidence = max(0.0, min(1.0, _num(getattr(scoring, "assistant_guidance_score_min_confidence", 0.6) if scoring else 0.6)))
    min_outcome_count = max(0, _int_num(getattr(scoring, "assistant_guidance_score_min_outcome_count", 1) if scoring else 1))
    bonus_cap = max(0.0, _num(getattr(scoring, "assistant_guidance_score_bonus_cap", 4.0) if scoring else 4.0))
    penalty_cap = max(0.0, _num(getattr(scoring, "assistant_guidance_score_penalty_cap", 5.0) if scoring else 5.0))
    config_snapshot = {
        "enabled": enabled,
        "min_confidence": min_confidence,
        "min_outcome_count": min_outcome_count,
        "bonus_cap": bonus_cap,
        "penalty_cap": penalty_cap,
    }
    if not enabled:
        return {
            "source": "disabled",
            "guidance_digest": digest,
            "outcome_status": "disabled",
            "outcome_count": 0,
            "success_rate": 0.0,
            "avg_score": 0.0,
            "confidence": 0.0,
            "adjustment": 0.0,
            "configuration": config_snapshot,
            "reason": "assistant guidance score adjustment disabled by scoring config",
        }
    if not digest:
        return {
            "source": "none",
            "guidance_digest": "",
            "outcome_status": "none",
            "adjustment": 0.0,
            "configuration": config_snapshot,
            "reason": "candidate has no assistant guidance metadata",
        }

    outcome = submission.get("assistant_guidance_outcome") if isinstance(submission.get("assistant_guidance_outcome"), dict) else {}
    count = _int_num(outcome.get("count", submission.get("assistant_guidance_outcome_count")))
    success_rate = _num(outcome.get("success_rate", submission.get("assistant_guidance_outcome_success_rate")))
    avg_score = _num(outcome.get("avg_score", submission.get("assistant_guidance_outcome_avg_score")))
    confidence = _normalize_confidence(submission.get("assistant_guidance_confidence"))
    status = str(submission.get("assistant_guidance_outcome_status") or "").strip().lower()
    if status not in {"strong", "neutral", "weak", "unknown"}:
        status = _guidance_outcome_status(count, success_rate, avg_score)

    if confidence < min_confidence:
        return {
            "source": "assistant_guidance_outcome",
            "guidance_digest": digest,
            "outcome_status": status or "unknown",
            "outcome_count": count,
            "success_rate": round(success_rate, 4),
            "avg_score": round(avg_score, 4),
            "confidence": confidence,
            "adjustment": 0.0,
            "configuration": config_snapshot,
            "reason": "assistant guidance confidence is below scoring adjustment threshold",
        }
    if count < min_outcome_count:
        return {
            "source": "assistant_guidance_outcome",
            "guidance_digest": digest,
            "outcome_status": status or "unknown",
            "outcome_count": count,
            "success_rate": round(success_rate, 4),
            "avg_score": round(avg_score, 4),
            "confidence": confidence,
            "adjustment": 0.0,
            "configuration": config_snapshot,
            "reason": "assistant guidance has too little historical outcome evidence for scoring adjustment",
        }

    adjustment = 0.0
    reason = "assistant guidance has no historical outcome evidence"
    if status == "strong":
        adjustment = 2.0
        if success_rate >= 0.75:
            adjustment += 1.0
        if avg_score >= 85:
            adjustment += 1.0
        reason = "historically strong assistant guidance gets a conservative local ranking bonus"
    elif status == "weak":
        adjustment = -3.0
        if count >= 2 and success_rate <= 0.0:
            adjustment -= 1.0
        if avg_score and avg_score < 40:
            adjustment -= 1.0
        reason = "historically weak assistant guidance gets a local ranking penalty"
    elif status == "neutral":
        adjustment = 0.75 if count else 0.0
        reason = "neutral assistant guidance history gets only a tiny local ranking nudge"

    if adjustment > 0:
        adjustment *= confidence
    adjustment = round(max(-penalty_cap, min(bonus_cap, adjustment)), 2)
    return {
        "source": "assistant_guidance_outcome",
        "guidance_digest": digest,
        "outcome_status": status or "unknown",
        "outcome_count": count,
        "success_rate": round(success_rate, 4),
        "avg_score": round(avg_score, 4),
        "confidence": confidence,
        "adjustment": adjustment,
        "configuration": config_snapshot,
        "reason": reason,
    }


def _compute_empirical_metrics(metrics: dict, settings: dict, thresholds: QualityThresholds) -> dict:
    """Compute all raw metrics from BRAIN API simulation data.

    Returns a dict with all computed values needed by empirical_score().
    Extracted from the 139-line function body (S-01).
    """
    settings = settings or {}
    delay = int(settings.get("delay", 1))
    effective_min_sharpe = thresholds.min_sharpe_delay0 if delay == 0 else thresholds.min_sharpe
    effective_min_fitness = thresholds.min_fitness_delay0 if delay == 0 else thresholds.min_fitness

    regime = getattr(thresholds, "market_regime", "normal")
    regime_adj = getattr(thresholds, "regime_adjustments", {}).get(regime, {})

    sharpe = _num(metrics.get("sharpe"))
    fitness = _num(metrics.get("fitness"))
    turnover = _ratio(metrics.get("turnover"))
    turnover_raw = _num(metrics.get("turnover_raw", metrics.get("turnover", 0)))
    returns = _num(metrics.get("returns"))
    drawdown = abs(_ratio(metrics.get("drawdown"), bounded=True))
    self_correlation = abs(_ratio(metrics.get("correlation"), bounded=True))
    prod_correlation = abs(_ratio(metrics.get("prod_correlation", 0.0), bounded=True))
    concentration = _ratio(metrics.get("weight_concentration"), bounded=True)
    sub_universe_sharpe = _num(metrics.get("sub_universe_sharpe", 0.0))
    sub_size = _num(metrics.get("subUniverseSize", metrics.get("sub_universe_size", 1000)))
    alpha_size = _num(metrics.get("alphaSize", metrics.get("alpha_size", 1000)))
    if alpha_size <= 0:
        alpha_size = 1
    if sub_size <= 0:
        sub_size = max(alpha_size, 1)
    size_factor = math.sqrt(max(sub_size, 1) / max(alpha_size, 1))
    sub_sharpe_threshold = round(
        thresholds.sub_universe_sharpe_min_ratio * size_factor * max(sharpe, 0.01), 4
    ) if sharpe > 0 else 0.0

    margin = _num(metrics.get("margin", None))
    margin_source = "BRAIN_API"
    if margin is None or margin == 0.0:
        margin = (returns / max(turnover, 0.001)) / 100.0
        margin_source = "estimated"
    margin_threshold = getattr(thresholds, "min_margin_bps", 4.0)

    _turnover_quality_is_hard = getattr(thresholds, "enforce_target_turnover_as_hard_gate", False)

    return {
        "delay": delay,
        "effective_min_sharpe": effective_min_sharpe,
        "effective_min_fitness": effective_min_fitness,
        "regime": regime,
        "regime_adj": regime_adj,
        "sharpe": sharpe,
        "fitness": fitness,
        "turnover": turnover,
        "turnover_raw": turnover_raw,
        "returns": returns,
        "drawdown": drawdown,
        "self_correlation": self_correlation,
        "prod_correlation": prod_correlation,
        "concentration": concentration,
        "sub_universe_sharpe": sub_universe_sharpe,
        "sub_sharpe_threshold": sub_sharpe_threshold,
        "margin": margin,
        "margin_source": margin_source,
        "margin_threshold": margin_threshold,
        "_turnover_quality_is_hard": _turnover_quality_is_hard,
    }


# P0-4 fix: canonical list of BRAIN check items — used by redline verifier
# instead of inspect.getsource which fails in PyInstaller builds.
EMPIRICAL_CHECK_ITEM_NAMES = frozenset({
    "sharpe", "fitness", "turnover_min", "turnover_platform",
    "self_correlation", "prod_correlation", "weight_concentration",
    "sub_universe_sharpe",
})

def empirical_score(metrics: dict, thresholds: QualityThresholds, settings: dict = None) -> dict:
    # BRAIN API canonical metric names accessed: alphaSize, subUniverseSize
    """Compute empirical score from BRAIN official simulation metrics.

    Args:
        metrics: BRAIN API simulation result metrics dict.
        thresholds: QualityThresholds dataclass instance.
        settings: Optional BRAIN settings dict (e.g. {'delay': 1}) for delay-aware
                  threshold selection (P1-4).
    """
    if not metrics:
        return {"score": 0.0, "items": [], "status": "missing_official_metrics"}

    raw = _compute_empirical_metrics(metrics, settings, thresholds)
    delay = raw["delay"]
    effective_min_sharpe = raw["effective_min_sharpe"]
    effective_min_fitness = raw["effective_min_fitness"]
    regime = raw["regime"]
    regime_adj = raw["regime_adj"]
    sharpe = raw["sharpe"]
    fitness = raw["fitness"]
    turnover = raw["turnover"]
    turnover_raw = raw["turnover_raw"]
    returns = raw["returns"]
    drawdown = raw["drawdown"]
    self_correlation = raw["self_correlation"]
    prod_correlation = raw["prod_correlation"]
    concentration = raw["concentration"]
    sub_universe_sharpe = raw["sub_universe_sharpe"]
    sub_sharpe_threshold = raw["sub_sharpe_threshold"]
    margin = raw["margin"]
    margin_source = raw["margin_source"]
    margin_threshold = raw["margin_threshold"]
    _turnover_quality_is_hard = raw["_turnover_quality_is_hard"]

    items = [
        # BRAIN: LOW_SHARPE if < 1.25 (Delay-1) / < 2.0 (Delay-0)
        item("sharpe", sharpe, ">=", effective_min_sharpe, sharpe >= effective_min_sharpe, 20, is_hard_gate=True),
        # BRAIN: LOW_FITNESS if < 1.0 (Delay-1) / < 1.3 (Delay-0)
        item("fitness", fitness, ">=", effective_min_fitness, fitness >= effective_min_fitness, 15, is_hard_gate=True),
        # P1-3: Cross-validate BRAIN Fitness formula: Fitness = Sharpe × √(|Returns| / max(Turnover, 0.125))
        item("fitness_crosscheck",
             round(abs(fitness - calculate_fitness(sharpe, returns, turnover, raw_turnover=turnover_raw)), 4),
             "<=", 0.05,
             abs(fitness - calculate_fitness(sharpe, returns, turnover, raw_turnover=turnover_raw)) <= 0.05, 0),
        # BRAIN: LOW_TURNOVER if < 1% (0.01)
        item("turnover_min", turnover, ">=", thresholds.min_turnover, turnover >= thresholds.min_turnover, 8, is_hard_gate=True),
        # BRAIN platform hard gate: HIGH_TURNOVER if > 70% (0.70).
        item("turnover_platform", turnover, "<=", getattr(thresholds, "platform_max_turnover", 0.70),
             turnover <= getattr(thresholds, "platform_max_turnover", 0.70), 8, is_hard_gate=True),
        # Advisor quality target: turnover < 30%, optionally promoted to a hard gate.
        item("turnover_quality", turnover, "<=", getattr(thresholds, "target_max_turnover", 0.30),
             turnover <= getattr(thresholds, "target_max_turnover", 0.30), 6,
             is_hard_gate=_turnover_quality_is_hard),
        # qualitative — positive returns expected (not a BRAIN hard check)
        item("returns", returns, ">=", thresholds.min_returns, returns >= thresholds.min_returns, 5),
        # qualitative — NOT a BRAIN hard check; guidance only
        item("drawdown", drawdown, "<=", thresholds.max_drawdown, drawdown <= thresholds.max_drawdown, 5),
        # BRAIN: SELF_CORRELATION if >= 0.70 (PnL correlation)
        # P1-1: Exception rule — if new_alpha.Sharpe >= related_alpha.Sharpe × 1.10, allow
        _build_self_correlation_item(self_correlation, thresholds, metrics),
        # derived from SELF_CORRELATION standard
        item("prod_correlation", prod_correlation, "<=", thresholds.max_prod_correlation, prod_correlation <= thresholds.max_prod_correlation, 10, is_hard_gate=True),
        # BRAIN: CONCENTRATED_WEIGHT if single stock > 10% (0.10)
        item("weight_concentration", concentration, "<=", thresholds.max_weight_concentration, concentration <= thresholds.max_weight_concentration, 5, is_hard_gate=True),
        # BRAIN: LOW_SUB_UNIVERSE_SHARPE — sub_sharpe >= 0.75 × √(sub_size/alpha_size) × alpha_sharpe
        item("sub_universe_sharpe", sub_universe_sharpe, ">=", round(sub_sharpe_threshold, 4), sub_universe_sharpe >= sub_sharpe_threshold, 10, is_hard_gate=True),
        # P1-3: IS/OOS robustness — OOS/IS Sharpe ratio >= 0.5 (SubUniverseSharpe as OOS proxy)
        item("is_oos_ratio",
             round(sub_universe_sharpe / max(sharpe, 0.01), 4) if sharpe > 0 else 0.0,
             ">=", 0.5,
             (sub_universe_sharpe / max(sharpe, 0.01)) >= 0.5 if sharpe > 0 else False, 8),
        # BRAIN advisor target: margin >= min_margin_bps (default 4.0 bps).
        item("margin_bps", round(margin, 4), ">=", margin_threshold, margin >= margin_threshold, 10),
    ]
    # P2-3: Annotate margin source
    for row in items:
        if row.get("name") == "margin_bps":
            row["margin_source"] = margin_source
    # P1-3: Log WARNING when BRAIN API fitness differs significantly from local calculation
    fitness_diff = abs(fitness - calculate_fitness(sharpe, returns, turnover, raw_turnover=turnover_raw))
    if fitness > 0 and fitness_diff > 0.05:
        import logging
        logging.warning(
            "Fitness crosscheck discrepancy: BRAIN API fitness=%.4f vs local=%.4f (diff=%.4f). "
            "This may indicate formula mismatch or API version differences.",
            fitness, calculate_fitness(sharpe, returns, turnover, raw_turnover=turnover_raw), fitness_diff
        )
    score = _bounded_score(sum(row.get("points", 0) for row in items if bool(row.get("passed", False)) and not row.get("is_hard_gate")))

    # P1-2: Separate hard gate failures from soft indicator scores
    hard_gate_failures = [
        _format_empirical_failure(row)
        for row in items
        if not bool(row.get("passed", False)) and row.get("is_hard_gate")
    ]
    hard_gate_failed = bool(hard_gate_failures)

    # P1-4: Hard gate failures force empirical_score to zero — hard gates are binary pass/fail
    if hard_gate_failed:
        score = 0.0
        status = "hard_gate_blocked"
    else:
        status = "ready" if score >= 70 else "needs_iteration"

    return {"score": score, "items": items,
            "status": status,
            "hard_gate_failed": hard_gate_failed,
            "hard_gate_failures": hard_gate_failures,
            "margin_source": margin_source, "delay": delay,
            "threshold_source": "BRAIN_Official",
            "market_regime": regime,
            "regime_adjustments": regime_adj,
            "regime_adjustments_applied_to_hard_gates": False}


def submission_checklist(candidate: Candidate, thresholds: QualityThresholds) -> dict:
    metrics = candidate.official_metrics or {}
    checks = [
        check("official_metrics_present", bool(metrics), 15, "Official simulation metrics are required."),
        check("official_pass", metrics.get("pass_fail") == "PASS" or not thresholds.require_official_pass, 15, "BRAIN pass/fail result."),
        check("economic_logic", len(candidate.hypothesis) >= 40 or not thresholds.require_economic_logic, 15, "One-sentence economic/behavioral thesis."),
        check("data_delay_conservative", True, 10, "Default settings use Delay 1 unless changed by user."),
        check("local_quality", candidate.local_quality.get("passed", False), 15, "Local prefilter quality."),
        check("self_correlation_proxy", _ratio(metrics.get("correlation"), bounded=True) <= thresholds.max_self_correlation if metrics else False, 20, "Official/local correlation proxy."),
        check(
            "diversity",
            normalize_family_label(candidate.family) != "momentum"
            or "adv20" in candidate.expression
            or "vwap" in candidate.expression,
            10,
            "Avoid plain crowded templates.",
        ),
    ]
    score = _bounded_score(sum(row.get("points", 0) for row in checks if bool(row.get("passed", False))))
    return {"score": score, "items": checks}


def evaluate_quality_gate(
    candidate: Candidate,
    thresholds: QualityThresholds,
    *,
    settings: dict | None = None,
) -> dict:
    if not candidate.scorecard:
        candidate.scorecard = build_scorecard(candidate, thresholds, settings=settings)
    scorecard = candidate.scorecard
    empirical = scorecard["empirical"]
    failed = []
    warnings = []

    # P1-2: Check hard gates first — BRAIN official hard gates are blocking
    if empirical.get("hard_gate_failed"):
        failed.extend(empirical.get("hard_gate_failures", []))
        warnings.append("hard_gate_blocked: BRAIN official checks failed — submission blocked regardless of total score")

    # Collect all remaining failed items (soft indicators + submission checklist)
    for row in empirical.get("items", []):
        if not bool(row.get("passed", False)) and row.get("points", 1) > 0 and not row.get("is_hard_gate"):
            failed.append(_format_empirical_failure(row))
    for row in scorecard["submission_checklist"]["items"]:
        if not bool(row.get("passed", False)):
            failed.append(str(row.get("name", "check")) + ": " + str(row.get("meaning", "")))
    if not candidate.official_metrics:
        failed.append("official_metrics_present: missing official simulation result")

    passed = not failed  # gate passes when no individual checks fail (official Alpha Checks standard)
    if not passed and scorecard["total_score"] >= 70:
        warnings.append("research_candidate_only_not_submission_ready")

    gate = {
        "schema_version": "production-gate-v2.2",
        "submission_ready": passed,
        "status": "SUBMISSION_READY" if passed else "NEEDS_ITERATION",
        "failed_reasons": failed,
        "warnings": warnings,
        "hard_gate_blocked": empirical.get("hard_gate_failed", False),
        "source_notes": {
            "thresholds": "BRAIN 官方 Alpha Check 标准 (LOW_SHARPE/LOW_FITNESS/HIGH_TURNOVER/CONCENTRATED_WEIGHT/SELF_CORRELATION/LOW_SUB_UNIVERSE_SHARPE)。Drawdown 非 BRAIN 硬性检查。",
            "official_checks": "官方模拟与 alpha check 是提交前必要证据。",
            "hard_gate_policy": "P1-2: BRAIN hard gates (sharpe/fitness/turnover_platform/self_correlation/prod_correlation/weight_concentration/sub_universe_sharpe/turnover_min) are blocking — any failure prevents submission regardless of total score.",
        },
    }
    candidate.gate = gate
    return gate


def _scorecard_settings(candidate: Candidate, explicit: dict | None = None) -> dict:
    """Return the BRAIN settings used for official threshold selection."""
    if isinstance(explicit, dict) and explicit:
        return dict(explicit)
    submission = candidate.submission if isinstance(candidate.submission, dict) else {}
    for key in ("settings", "brain_settings"):
        value = submission.get(key)
        if isinstance(value, dict) and value:
            return dict(value)
    validation = candidate.validation if isinstance(candidate.validation, dict) else {}
    value = validation.get("settings")
    if isinstance(value, dict) and value:
        return dict(value)
    return {}


def decision_band(score: float, hard_gate_failed: bool = False, scoring: ScoringConfig | None = None) -> str:
    if hard_gate_failed:
        return "hard_gate_blocked"
    thresholds = {"submit": 85.0, "optimize": 70.0, "research": 50.0}
    if scoring and isinstance(getattr(scoring, "decision_thresholds", None), dict):
        for key in thresholds:
            value = scoring.decision_thresholds.get(key)
            if isinstance(value, (int, float)):
                thresholds[key] = float(value)
    if score >= thresholds["submit"]:
        return "submit_candidate"
    if score >= thresholds["optimize"]:
        return "optimize_before_submit"
    if score >= thresholds["research"]:
        return "research_only"
    return "abandon_or_rebuild"


# ── P1-3: BRAIN Official Fitness Formula ──
def calculate_fitness(sharpe: float, returns: float, turnover: float,
                      *, raw_turnover: float | None = None) -> float:
    """BRAIN 官方 Fitness 公式: Sharpe x sqrt(|Returns| / max(Turnover, 0.125)).

    IMPORTANT: BRAIN API 返回的 turnover 是原始十进制 (e.g. 1.2 = 120%)。
    _ratio() 会保留自然 turnover 值，仅对明确百分比尺度的值归一化；
    fitness 公式仍优先使用 raw_turnover，避免任何展示归一化影响官方公式。
    
    使用 raw_turnover (未除以 100 的原始值) 来正确计算公式。
    如果 raw_turnover 未提供，回退到 adjusted turnover。
    """
    return fitness_crosscheck_formula(sharpe, returns, turnover, raw_turnover=raw_turnover)


def _check_self_correlation_with_exception(
    self_correlation: float,
    thresholds: "QualityThresholds",
    metrics: dict,
) -> bool:
    """P1-1: BRAIN SELF_CORRELATION check with Sharpe advantage exception.

    Official rule: PnL correlation >= 0.70 → FAIL, UNLESS
    new_alpha.Sharpe >= related_alpha.Sharpe × 1.10 (exception).

    Source: BRAIN API Alpha Check — SELF_CORRELATION exception rule.
    """
    if self_correlation < thresholds.max_self_correlation:
        return True
    # Exception: Sharpe advantage
    sharpe = _num(metrics.get("sharpe", 0))
    related_sharpe = _num(metrics.get("related_alpha_sharpe", metrics.get("relatedAlphaSharpe", 0)))
    if related_sharpe > 0 and sharpe + 1e-12 >= related_sharpe * 1.10:
        return True
    return False


def _build_self_correlation_item(
    self_correlation: float,
    thresholds: "QualityThresholds",
    metrics: dict,
) -> dict:
    """P1-1: Build self_correlation check item with exception_applied tracking.

    Returns an item dict compatible with scoring.item() but with
    exception_applied and exception_note fields when the BRAIN Sharpe
    advantage exception is applied.
    """
    passed = self_correlation < thresholds.max_self_correlation
    exception_applied = False
    exception_note = ""
    if not passed:
        sharpe = _num(metrics.get("sharpe", 0))
        related_sharpe = _num(metrics.get("related_alpha_sharpe", metrics.get("relatedAlphaSharpe", 0)))
        if related_sharpe > 0 and sharpe + 1e-12 >= related_sharpe * 1.10:
            passed = True
            exception_applied = True
            exception_note = (
                f"BRAIN exception: Sharpe {sharpe:.3f} >= "
                f"related Sharpe {related_sharpe:.3f} × 1.10"
            )
    result = item("self_correlation", self_correlation, "<",
                  thresholds.max_self_correlation, passed, 14, is_hard_gate=True)
    result["exception_applied"] = exception_applied
    if exception_applied:
        result["exception_note"] = exception_note
    return result


def item(name: str, actual, direction: str, target, passed: bool, points: int, *, is_hard_gate: bool = False) -> dict:
    return {
        "name": name,
        "actual": actual,
        "direction": direction,
        "target": target,
        "passed": bool(passed),
        "points": points,
        "is_hard_gate": is_hard_gate,
        "source": "BRAIN_Official" if is_hard_gate else "经验",
    }


def check(name: str, passed: bool, points: int, meaning: str) -> dict:
    return {"name": name, "passed": bool(passed), "points": points, "meaning": meaning}


def _bounded_score(value) -> float:
    return round(max(0.0, min(100.0, _num(value))), 2)


def _guidance_outcome_status(count: int, success_rate: float, avg_score: float) -> str:
    if count <= 0:
        return "unknown"
    if count >= 2 and (success_rate <= 0.25 or avg_score <= 50):
        return "weak"
    if success_rate >= 0.5 or avg_score >= 70:
        return "strong"
    return "neutral"


def _normalize_confidence(value) -> float:
    if value in (None, ""):
        return 1.0
    confidence = _num(value)
    if confidence > 1.0:
        confidence = confidence / 100.0
    return max(0.0, min(1.0, confidence))


def _int_num(value) -> int:
    return int(_num(value))


def _num(value) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ═══════════════════════════════════════════════════════════════════════
# P2: score confidence estimation from point estimate to interval estimate.
# ═══════════════════════════════════════════════════════════════════════

def estimate_score_confidence(scorecard: dict) -> dict:
    """估算 scorecard total_score 的置信度。

    基于 empirical items 的内部离散度和数据完备性评估评分可靠性。

    返回:
        {
            "confidence_level": "high" | "medium" | "low",
            "item_count": int,
            "passed_count": int,
            "score_variance": float,        # Item score variance.
            "score_dispersion": float,       # Coefficient of variation (std/mean).
            "data_completeness": float,      # Between 0 and 1.
            "interpretation": str,
        }
    """
    empirical = scorecard.get("empirical", {})
    items = empirical.get("items", [])

    if not items:
        return {
            "confidence_level": "low",
            "item_count": 0, "passed_count": 0,
            "score_variance": 0.0, "score_dispersion": 0.0,
            "data_completeness": 0.0,
            "interpretation": "No empirical items — score based on prior only.",
        }

    # Point values for passed score items.
    scores = [row.get("points", 0) for row in items if row.get("passed")]
    n_items = len(scores)
    passed_count = len(scores)
    data_completeness = n_items / max(len(items), 1)

    if n_items < 2:
        confidence_level = "low"
        variance = 0.0
        dispersion = 1.0
    else:
        mean_score = sum(scores) / n_items
        variance = sum((s - mean_score) ** 2 for s in scores) / n_items
        std_dev = variance ** 0.5
        dispersion = std_dev / max(mean_score, 0.01)

        if dispersion < 0.50 and data_completeness > 0.8:
            confidence_level = "high"
        elif dispersion < 0.75:
            confidence_level = "medium"
        else:
            confidence_level = "low"

    # Interpretation.
    if confidence_level == "high":
        interpretation = (
            f"Score estimate is robust: {passed_count}/{len(items)} items passed, "
            f"low dispersion (cv={dispersion:.3f}), near-complete data."
        )
    elif confidence_level == "medium":
        interpretation = (
            f"Score estimate is acceptable: {passed_count}/{len(items)} items passed, "
            f"moderate dispersion (cv={dispersion:.3f}). Consider adding more validation data."
        )
    else:
        interpretation = (
            f"Score estimate is unreliable: {passed_count}/{len(items)} items passed, "
            f"high dispersion (cv={dispersion:.3f}). More official simulation data needed."
        )

    return {
        "confidence_level": confidence_level,
        "item_count": n_items,
        "passed_count": passed_count,
        "score_variance": round(variance, 4),
        "score_dispersion": round(dispersion, 4),
        "data_completeness": round(data_completeness, 4),
        "interpretation": interpretation,
    }

"""Structured scoring and production gates."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from brain_alpha_ops.config import QualityThresholds, ScoringConfig
from brain_alpha_ops.models import Candidate

if TYPE_CHECKING:
    from brain_alpha_ops.research.scoring_params import ScoringParams


def build_scorecard(
    candidate: Candidate,
    thresholds: QualityThresholds,
    scoring: ScoringConfig | None = None,
    params: "ScoringParams | None" = None,
) -> dict:
    prior = prior_score(
        candidate,
        weights_override=scoring.prior_weights_override if scoring else None,
        params=params,
    )
    empirical = empirical_score(candidate.official_metrics, thresholds)
    checklist = submission_checklist(candidate, thresholds)
    base_local_rank_score = local_convergence_score(candidate, prior, scoring=scoring)
    guidance_adjustment = assistant_guidance_score_adjustment(candidate, scoring=scoring)
    local_rank_score = _bounded_score(
        base_local_rank_score + float(guidance_adjustment.get("adjustment", 0.0) or 0.0)
    )
    official_verified = bool(candidate.official_metrics)

    # ── 三层权重：从 ScoringConfig 读取，fallback 到原始 30/45/25 ──
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
        "decision_band": decision_band(total, empirical.get("hard_gate_failed", False)),
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
        "confidence": estimate_score_confidence({
            "empirical": empirical,
            "score_basis": score_basis,
        }) if official_verified else None,
        "calibration": {
            "prior_minus_empirical": round(prior["score"] - empirical["score"], 2)
            if official_verified
            else None,
            "sample_weight": 1.0 if official_verified else 0.25,
            "purpose": "Track whether local priors predict official outcomes over time.",
            "params_used": params is not None,
        },
    }
    candidate.scorecard = scorecard
    return scorecard


def prior_score(
    candidate: Candidate,
    weights_override: dict | None = None,
    params: "ScoringParams | None" = None,
) -> dict:
    """先验评分：8 个维度的加权综合。

    Args:
        candidate: 候选 alpha
        weights_override: 维度权重覆盖字典（向后兼容）
        params: 可校准评分参数。None 时使用硬编码公式（向后兼容）；
                非 None 时使用参数化公式，并优先使用 params 中的 weight。

    Returns:
        {"score": float, "dimensions": dict, "weights": dict, "source": str}
    """
    dims = {}
    expression = candidate.expression or ""
    fields = set(candidate.data_fields or [])
    operators = list(candidate.operators or [])
    windows = [int(value) for value in re.findall(r"\b\d+\b", expression)]
    has_cross_section = any(op in operators for op in ("rank", "zscore", "scale", "group_rank", "group_zscore"))
    has_time_series = any(op.startswith("ts_") for op in operators)
    has_risk_control = any(op in operators for op in ("winsorize", "zscore", "scale", "group_rank")) or "adv20" in fields
    median_window = sorted(windows)[len(windows) // 2] if windows else 0

    # P0 优化：economic_logic 从二值化改为经济概念关键词分类打分
    economic_result = _economic_logic_score(
        candidate.hypothesis, expression, fields, operators
    )
    dims["economic_logic"] = economic_result["score"]
    dims["economic_concepts"] = economic_result["concepts_detected"]

    # ── 各维度评分：优先使用参数化公式 ──
    if params:
        dims.update(_parameterized_dimensions(
            params, fields, operators, windows, median_window,
            has_cross_section, has_time_series, has_risk_control,
            candidate, expression, economic_result,
        ))
    else:
        dims["structure"] = max(25, 90 - max(0, len(operators) - 4) * 8)
        dims["field_operator_support"] = min(92, 42 + len(fields) * 8 + len(set(operators)) * 4)
        dims["data_compliance"] = 82 if fields else 35
        dims["horizon_turnover_proxy"] = 82 if 5 <= median_window <= 90 else 68 if median_window else 50
        dims["risk_control_proxy"] = 84 if has_cross_section and has_time_series and has_risk_control else 66 if has_cross_section and has_time_series else 48
        dims["diversity"] = 80 if candidate.family in {"Liquidity", "Volatility", "Hybrid"} else 65
        dims["explainability"] = 85 if len(candidate.expression) < 140 else 60

    # ── 权重：可通过 weights_override 注入校准值，params 提供第二来源 ──
    source_parts = ["经验"]
    default_weights = {
        "economic_logic": 0.18, "structure": 0.14,
        "field_operator_support": 0.16, "data_compliance": 0.12,
        "horizon_turnover_proxy": 0.14, "risk_control_proxy": 0.14,
        "diversity": 0.07, "explainability": 0.05,
    }
    if params and not weights_override:
        # 从 params 提取校准后的权重
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
    """使用 ScoringParams 参数化计算各维度分数。"""
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

    # horizon_turnover_proxy: 三档（窗口内 / 窗口外 / 无数据）
    p = params.get_dimension("horizon_turnover_proxy")
    if p and p.enabled:
        if not median_window:
            dims["horizon_turnover_proxy"] = p.score_no_data
        elif p.threshold_low <= median_window <= p.threshold_high:
            dims["horizon_turnover_proxy"] = p.score_in_range
        else:
            dims["horizon_turnover_proxy"] = p.score_out_range

    # risk_control_proxy: 三条件分层
    p = params.get_dimension("risk_control_proxy")
    if p and p.enabled:
        conditions = sum([has_cs, has_ts, has_rc])
        if conditions >= 3:
            dims["risk_control_proxy"] = p.tier_3_score
        elif conditions >= 2:
            dims["risk_control_proxy"] = p.tier_2_score
        else:
            dims["risk_control_proxy"] = p.tier_1_score

    # diversity: 分类匹配
    p = params.get_dimension("diversity")
    if p and p.enabled:
        high_set = set(p.high_value_set or [])
        dims["diversity"] = p.high_score if candidate.family in high_set else p.low_score

    # explainability: 表达式长度阈值
    p = params.get_dimension("explainability")
    if p and p.enabled:
        dims["explainability"] = p.score_in_range if len(expression) < p.threshold_high else p.score_out_range

    # economic_logic is already computed via _economic_logic_score — keep as-is
    # (its keyword-based detection is hard to parameterize meaningfully)

    return dims


# ═══════════════════════════════════════════════════════════════════════
# P0 优化：economic_logic 关键词概念检测
# ═══════════════════════════════════════════════════════════════════════

def _economic_logic_score(
    hypothesis: str,
    expression: str,
    fields: set[str],
    operators: list[str],
) -> dict:
    """基于经济概念关键词检测评估 Alpha 的经济逻辑质量。

    替代原来的二值化判定（hypothesis 长度 >= 40 → 85 / 否则 45）。

    返回: {"score": int, "concepts_detected": [str], "source": str}
    """
    text = f"{hypothesis} {expression} {' '.join(fields)} {' '.join(operators)}".lower()

    # ── 经济概念词典 ──
    concepts = {
        "momentum": {
            "keywords": ["momentum", "trend", "ts_delta", "ts_rank", "ts_mean",
                         "moving_average", "breakout", "continuation"],
            "base": 78,
        },
        "mean_reversion": {
            "keywords": ["reversal", "mean_revert", "zscore", "ts_zscore",
                         "overbought", "oversold", "-ts_", "bounce", "revert"],
            "base": 78,
        },
        "value": {
            "keywords": ["value", "cheap", "undervalue", "pe_ratio", "pb_ratio",
                         "market_cap", "book", "dividend_yield", "earnings_yield"],
            "base": 78,
        },
        "quality": {
            "keywords": ["quality", "profit", "margin", "roe", "roa",
                         "stable", "fundamental", "balance_sheet"],
            "base": 78,
        },
        "volatility": {
            "keywords": ["volatility", "vol", "ts_std", "std", "ivol",
                         "beta", "risk", "variance", "uncertainty"],
            "base": 78,
        },
        "liquidity": {
            "keywords": ["liquidity", "volume", "turn", "adv", "vwap",
                         "bid", "spread", "depth", "market_impact"],
            "base": 78,
        },
        "growth": {
            "keywords": ["growth", "earnings", "revenue", "sales_growth",
                         "expansion", "accelerat"],
            "base": 78,
        },
        "risk_management": {
            "keywords": ["winsorize", "truncation", "neutralize", "group_neutralize",
                         "hedge", "sector_neutral", "risk_adjust"],
            "base": 82,
        },
        "cross_sectional": {
            "keywords": ["cross_section", "rank", "group_rank", "sector",
                         "industry", "subindustry", "relative", "peer"],
            "base": 80,
        },
    }

    detected = []
    for concept_name, info in concepts.items():
        if any(keyword in text for keyword in info["keywords"]):
            detected.append(concept_name)

    if not detected:
        # hypothesis 内容不足但仍有长度兜底
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
    # ── 权重从 ScoringConfig 读取，fallback 到原始 0.65/0.35 ──
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


def empirical_score(metrics: dict, thresholds: QualityThresholds, settings: dict = None) -> dict:
    """Compute empirical score from BRAIN official simulation metrics.

    Args:
        metrics: BRAIN API simulation result metrics dict.
        thresholds: QualityThresholds dataclass instance.
        settings: Optional BRAIN settings dict (e.g. {'delay': 1}) for delay-aware
                  threshold selection (P1-4).
    """
    if not metrics:
        return {"score": 0.0, "items": [], "status": "missing_official_metrics"}

    settings = settings or {}
    delay = int(settings.get("delay", 1))
    # P1-4: Delay-aware threshold selection
    effective_min_sharpe = thresholds.min_sharpe_delay0 if delay == 0 else thresholds.min_sharpe
    effective_min_fitness = thresholds.min_fitness_delay0 if delay == 0 else thresholds.min_fitness

    # P2: Market regime adjustment
    regime = getattr(thresholds, "market_regime", "normal")
    regime_adj = getattr(thresholds, "regime_adjustments", {}).get(regime, {})
    regime_sharpe_factor = float(regime_adj.get("sharpe_factor", 1.0))
    regime_fitness_factor = float(regime_adj.get("fitness_factor", 1.0))
    regime_turnover_factor = float(regime_adj.get("turnover_factor", 1.0))
    effective_min_sharpe = effective_min_sharpe * regime_sharpe_factor
    effective_min_fitness = effective_min_fitness * regime_fitness_factor

    sharpe = _num(metrics.get("sharpe"))
    fitness = _num(metrics.get("fitness"))
    turnover = _ratio(metrics.get("turnover"))
    turnover_raw = _num(metrics.get("turnover_raw", metrics.get("turnover", 0)))
    returns = _num(metrics.get("returns"))
    drawdown = abs(_ratio(metrics.get("drawdown")))
    self_correlation = abs(_ratio(metrics.get("correlation")))
    prod_correlation = abs(_ratio(metrics.get("prod_correlation", 0.0)))
    concentration = _ratio(metrics.get("weight_concentration"))
    sub_universe_sharpe = _num(metrics.get("sub_universe_sharpe", 0.0))
    # BRAIN: LOW_SUB_UNIVERSE_SHARPE — sub_sharpe < 0.75 × √(sub_size/alpha_size) × alpha_sharpe
    import math
    sub_size = _num(metrics.get("subUniverseSize", 1000))
    alpha_size = _num(metrics.get("alphaSize", 1000))
    size_factor = math.sqrt(sub_size / max(alpha_size, 1))
    sub_sharpe_threshold = round(
        thresholds.sub_universe_sharpe_min_ratio * size_factor * max(sharpe, 0.01), 4
    )
    # Margin (BRAIN 顾问标准): prefer API-provided margin in bps
    # P2-3: API margin preferred; fall back to local estimate only when API absent
    margin = _num(metrics.get("margin", None))
    margin_source = "BRAIN_API"
    if margin is None or margin == 0.0:
        margin = (returns / max(turnover, 0.001)) / 100.0
        margin_source = "estimated"
    margin_threshold = getattr(thresholds, "min_margin_bps", 4.0)

    # P1-1: 换手率阈值策略 — turnover_quality 可配置为硬门禁
    _turnover_quality_is_hard = getattr(thresholds, "enforce_target_turnover_as_hard_gate", False)

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
        # BRAIN 平台硬门槛: HIGH_TURNOVER if > 70% (0.70) — 合规底线
        item("turnover_platform", turnover, "<=", getattr(thresholds, "platform_max_turnover", 0.70),
             turnover <= getattr(thresholds, "platform_max_turnover", 0.70), 8, is_hard_gate=True),
        # 顾问质量目标: Turnover < 30% — 可通过 enforce_target_turnover_as_hard_gate 升级为硬门禁
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
        # BRAIN 顾问标准: margin >= min_margin_bps (default 4.0 bps)
        item("margin_bps", round(margin, 4), ">=", margin_threshold, margin >= margin_threshold, 10),
    ]
    # P2-3: Annotate margin source
    for row in items:
        if row["name"] == "margin_bps":
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
    score = _bounded_score(sum(row["points"] for row in items if row["passed"]))

    # P1-2: Separate hard gate failures from soft indicator scores
    hard_gate_failures = [
        f"{row['name']} {row['direction']} {row['target']} (actual: {row['actual']})"
        for row in items
        if not row["passed"] and row.get("is_hard_gate") and row.get("points", 0) > 0
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
            "market_regime": regime, "regime_adjustments": regime_adj}


def submission_checklist(candidate: Candidate, thresholds: QualityThresholds) -> dict:
    metrics = candidate.official_metrics or {}
    checks = [
        check("official_metrics_present", bool(metrics), 15, "Official simulation metrics are required."),
        check("official_pass", metrics.get("pass_fail") == "PASS" or not thresholds.require_official_pass, 15, "BRAIN pass/fail result."),
        check("economic_logic", len(candidate.hypothesis) >= 40 or not thresholds.require_economic_logic, 15, "One-sentence economic/behavioral thesis."),
        check("data_delay_conservative", True, 10, "Default settings use Delay 1 unless changed by user."),
        check("local_quality", candidate.local_quality.get("passed", False), 15, "Local prefilter quality."),
        check("self_correlation_proxy", _ratio(metrics.get("correlation")) <= thresholds.max_self_correlation if metrics else False, 20, "Official/local correlation proxy."),
        check("diversity", candidate.family not in {"Momentum"} or "adv20" in candidate.expression or "vwap" in candidate.expression, 10, "Avoid plain crowded templates."),
    ]
    score = _bounded_score(sum(row["points"] for row in checks if row["passed"]))
    return {"score": score, "items": checks}


def evaluate_quality_gate(candidate: Candidate, thresholds: QualityThresholds) -> dict:
    scorecard = candidate.scorecard or build_scorecard(candidate, thresholds)
    empirical = scorecard["empirical"]
    failed = []
    warnings = []

    # P1-2: Check hard gates first — BRAIN official hard gates are blocking
    if empirical.get("hard_gate_failed"):
        failed.extend(empirical.get("hard_gate_failures", []))
        warnings.append("hard_gate_blocked: BRAIN official checks failed — submission blocked regardless of total score")

    # Collect all remaining failed items (soft indicators + submission checklist)
    for row in empirical.get("items", []):
        if not row["passed"] and row.get("points", 1) > 0 and not row.get("is_hard_gate"):
            failed.append(f"{row['name']} {row['direction']} {row['target']} (actual: {row['actual']})")
    for row in scorecard["submission_checklist"]["items"]:
        if not row["passed"]:
            failed.append(row["name"] + ": " + row["meaning"])
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


def decision_band(score: float, hard_gate_failed: bool = False) -> str:
    if hard_gate_failed:
        return "hard_gate_blocked"
    if score >= 85:
        return "submit_candidate"
    if score >= 70:
        return "optimize_before_submit"
    if score >= 50:
        return "research_only"
    return "abandon_or_rebuild"


# ── P1-3: BRAIN Official Fitness Formula ──
def calculate_fitness(sharpe: float, returns: float, turnover: float,
                      *, raw_turnover: float | None = None) -> float:
    """BRAIN 官方 Fitness 公式: Sharpe x sqrt(|Returns| / max(Turnover, 0.125)).

    IMPORTANT: BRAIN API 返回的 turnover 是原始十进制 (e.g. 1.2 = 120%)。
    normalize_metrics() 中的 _ratio() 会对 abs>1.0 的值除以 100，
    导致 fitness 公式使用了错误的 turnover 值。
    
    使用 raw_turnover (未除以 100 的原始值) 来正确计算公式。
    如果 raw_turnover 未提供，回退到 adjustd turnover。
    """
    import math
    used_turnover = raw_turnover if (raw_turnover is not None and raw_turnover > 0) else turnover
    denominator = max(used_turnover, 0.125)
    ratio = abs(returns) / denominator
    return sharpe * math.sqrt(ratio)


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
    if related_sharpe > 0 and sharpe >= related_sharpe * 1.10:
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
    passed = self_correlation <= thresholds.max_self_correlation
    exception_applied = False
    exception_note = ""
    if not passed:
        sharpe = _num(metrics.get("sharpe", 0))
        related_sharpe = _num(metrics.get("related_alpha_sharpe", metrics.get("relatedAlphaSharpe", 0)))
        if related_sharpe > 0 and sharpe >= related_sharpe * 1.10:
            passed = True
            exception_applied = True
            exception_note = (
                f"BRAIN exception: Sharpe {sharpe:.3f} >= "
                f"related Sharpe {related_sharpe:.3f} × 1.10"
            )
    result = item("self_correlation", self_correlation, "<=",
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


def _ratio(value) -> float:
    """Normalize ratio values from BRAIN API responses.

    BRAIN may return metrics as percentages (e.g. 70 meaning 70%) or as
    decimals (e.g. 0.70).  This function applies heuristics to normalize:
      - abs > 1.0  → assumed percentage, divide by 100
      - abs <= 1.0 → assumed decimal, pass through

    P1-3: Added logging for ambiguous values and dedicated turnover handling.
    """
    numeric = _num(value)
    if numeric == 0.0:
        return 0.0

    if abs(numeric) <= 1.0:
        return numeric

    # abs > 1.0 — could be percentage or genuinely large ratio
    if abs(numeric) > 100.0:
        # Values > 100 are almost certainly not percentages
        import logging
        logging.warning(
            "_ratio: unusually large value %.4f — treating as raw (not percentage). "
            "If BRAIN changed metric format, this may need adjustment.", numeric
        )
        return numeric

    # Likely a percentage (e.g. 70 → 0.70)
    import logging
    logging.debug("_ratio: normalizing %.4f → %.4f (assumed percentage)", numeric, numeric / 100.0)
    return numeric / 100.0


def _turnover_ratio(value) -> float:
    """Normalize turnover specifically, with BRAIN-aware heuristics.

    BRAIN turnover: typically 0-100 range where > 1.0 means percentage.
    Special case: a value like 2.5 could be 2.5% (correctly / 100 → 0.025).
    """
    return _ratio(value)


# ═══════════════════════════════════════════════════════════════════════
# P2: 评分置信度估算 — 从点估计 → 区间估计
# ═══════════════════════════════════════════════════════════════════════

def estimate_score_confidence(scorecard: dict) -> dict:
    """估算 scorecard total_score 的置信度。

    基于 empirical items 的内部离散度和数据完备性评估评分可靠性。

    返回:
        {
            "confidence_level": "high" | "medium" | "low",
            "item_count": int,
            "passed_count": int,
            "score_variance": float,        # item 得分方差
            "score_dispersion": float,       # 离散系数 (std/mean)
            "data_completeness": float,      # 0-1 之间
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

    # 得分项的点值
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

        if dispersion < 0.25 and data_completeness > 0.8:
            confidence_level = "high"
        elif dispersion < 0.50:
            confidence_level = "medium"
        else:
            confidence_level = "low"

    # 解读
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

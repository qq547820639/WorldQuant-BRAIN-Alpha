"""Empirical scoring from BRAIN official simulation metrics.

Contains ``empirical_score``, ``_compute_empirical_metrics``,
``calculate_fitness`` (BRAIN official formula), self-correlation checks with
Sharpe-advantage exception, and ``EMPIRICAL_CHECK_ITEM_NAMES``.
"""

from __future__ import annotations

import logging
import math

from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.research._ratio import _ratio
from brain_alpha_ops.scoring._score_comparisons import (
    fitness_crosscheck_formula,
)

from ._helpers import (
    _bounded_score,
    _format_empirical_failure,
    _num,
    item,
)


# P0-4 fix: canonical list of BRAIN check items — used by redline verifier
# instead of inspect.getsource which fails in PyInstaller builds.
EMPIRICAL_CHECK_ITEM_NAMES = frozenset({
    "sharpe", "fitness", "turnover_min", "turnover_platform",
    "self_correlation", "prod_correlation", "weight_concentration",
    "sub_universe_sharpe",
})


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

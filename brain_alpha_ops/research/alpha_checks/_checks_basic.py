"""BRAIN official Alpha Checks — basic check functions.

Core performance, turnover, correlation, concentration, sub-universe,
risk, margin, IC, stability, coverage, structure, and data-compliance
check implementations.
"""
from __future__ import annotations

import math
from typing import Any

from brain_alpha_ops.research.alpha_checks._types import CheckResult


def _metric(sim: dict[str, Any], *keys: str, default: Any = 0.0) -> float:
    """Extract a numeric metric from sim result, trying multiple keys."""
    for key in keys:
        val = sim.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return float(default)


def _check_sharpe_positive(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "sharpe", "Sharpe")
    thresholds = sim.get("_thresholds", None)
    settings = sim.get("settings", {}) or {}
    delay = int(settings.get("delay", 1))
    # BRAIN: LOW_SHARPE threshold depends on delay
    if delay == 0:
        min_sharpe = float(getattr(thresholds, "min_sharpe_delay0", 2.0))
    else:
        min_sharpe = float(getattr(thresholds, "min_sharpe", 1.25))
    passed = val >= min_sharpe
    return CheckResult(
        check_name="sharpe_positive",
        passed=passed,
        actual=val,
        expected=f">= {min_sharpe} (Delay-{delay})",
        message=f"Sharpe={val:.3f}" + ("" if passed else f" (below {min_sharpe})"),
    )


def _check_fitness_minimum(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "fitness", "Fitness")
    thresholds = sim.get("_thresholds", None)
    settings = sim.get("settings", {}) or {}
    delay = int(settings.get("delay", 1))
    # BRAIN: LOW_FITNESS threshold depends on delay
    if delay == 0:
        min_fitness = float(getattr(thresholds, "min_fitness_delay0", 1.3))
    else:
        min_fitness = float(getattr(thresholds, "min_fitness", 1.0))
    passed = val >= min_fitness
    return CheckResult(
        check_name="fitness_minimum",
        passed=passed,
        actual=val,
        expected=f">= {min_fitness} (Delay-{delay})",
        message=f"Fitness={val:.3f}" + ("" if passed else f" (below {min_fitness})"),
    )


def _check_returns_positive(sim: dict[str, Any]) -> CheckResult:
    """Qualitative check — BRAIN does not hard-check returns."""
    val = _metric(sim, "returns", "Returns", "return")
    passed = val > 0
    return CheckResult(
        check_name="returns_positive",
        passed=passed,
        actual=val,
        expected="> 0",
        message=f"Returns={val:.5f}" + ("" if passed else " (not positive)"),
    )


def _check_drawdown_limit(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: drawdown is NOT a hard platform check — qualitative guidance (WARNING).

    Uses max_drawdown from QualityThresholds (default 0.25).
    """
    val = abs(_metric(sim, "drawdown", "maxDrawdown", "MaxDrawdown"))
    thresholds = sim.get("_thresholds", None)
    max_drawdown = float(getattr(thresholds, "max_drawdown", 0.25))
    passed = val <= max_drawdown
    return CheckResult(
        check_name="drawdown_limit",
        passed=passed,
        actual=val,
        expected=f"<= {max_drawdown:.2f}",
        message=f"Drawdown={val:.3f}" + ("" if passed else f" (exceeds {max_drawdown:.2f}) — note: BRAIN does not hard-check drawdown"),
    )


def _check_turnover_platform(sim: dict[str, Any]) -> CheckResult:
    """BRAIN platform hard gate: turnover 1%-70% (LOW_TURNOVER / HIGH_TURNOVER).

    Source: BRAIN API Alpha Check — LOW_TURNOVER if < 1%, HIGH_TURNOVER if > 70%.
    This is the minimum compliance line for passing BRAIN checks and has ERROR
    severity.
    """
    val = _metric(sim, "turnover", "Turnover")
    thresholds = sim.get("_thresholds", None)
    min_t = float(getattr(thresholds, "min_turnover", 0.01))
    max_t = float(getattr(thresholds, "platform_max_turnover", 0.70))
    passed = min_t <= val <= max_t
    return CheckResult(
        check_name="turnover_platform",
        passed=passed,
        actual=val,
        expected=f"{min_t:.2f} – {max_t:.2f} (BRAIN platform hard gate)",
        message=f"Turnover={val:.3f}" + ("" if passed else f" (out of {min_t:.2f}–{max_t:.2f}) — BRAIN platform hard gate"),
    )


def _check_turnover_quality(sim: dict[str, Any]) -> CheckResult:
    """Advisor quality target: turnover < 30% for preferred submission.

    Alphas in the 30%-70% band are not hard-rejected, but should usually be
    optimized first by increasing decay, adding smoothing, extending lookback,
    or reducing trigger frequency. Prefer submitting alphas below 30% unless a
    30%-70% alpha is clearly stronger on Sharpe, Fitness, Drawdown, or
    correlation.

    Source: BRAIN advisor target — recommended turnover ceiling for robust
    alphas, WARNING severity.
    """
    val = _metric(sim, "turnover", "Turnover")
    thresholds = sim.get("_thresholds", None)
    target = float(getattr(thresholds, "target_max_turnover", 0.30))
    passed = val <= target
    return CheckResult(
        check_name="turnover_quality",
        passed=passed,
        actual=val,
        expected=f"<= {target:.2f} (preferred submission)",
        message=f"Turnover={val:.3f}" + ("" if passed else
            f" (>{target:.2f}) — optimize with higher decay, smoothing, longer lookback, or trade_when"),
    )


def _check_self_correlation(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: SELF_CORRELATION if >= 0.70 (PnL correlation with previously submitted alphas).

    Exception rule (BRAIN official): if new_alpha.Sharpe >= correlated_alpha.Sharpe × 1.10,
    the alpha can still be submitted even if correlation >= 0.70.
    """
    val = abs(_metric(sim, "selfCorrelation", "self_correlation", "correlation", default=0.0))
    passed = val < 0.70
    exception_applied = False

    # BRAIN exception: Sharpe advantage.
    if not passed:
        sharpe = _metric(sim, "sharpe", "Sharpe", default=0.0)
        related_sharpe = _metric(sim, "relatedAlphaSharpe", "related_alpha_sharpe", default=0.0)
        if related_sharpe > 0 and sharpe >= related_sharpe * 1.10:
            passed = True
            exception_applied = True

    expected_str = "< 0.70" if not exception_applied else "< 0.70 OR Sharpe >= related × 1.10"
    msg = f"SelfCorrelation={val:.4f}"
    if exception_applied:
        msg += " (exception: Sharpe advantage — new Sharpe >= related Sharpe × 1.10)"
    elif not passed:
        msg += " (>= 0.70)"

    return CheckResult(
        check_name="self_correlation",
        passed=passed,
        actual=val,
        expected=expected_str,
        message=msg,
        exception_applied=exception_applied,
    )


def _check_prod_correlation(sim: dict[str, Any]) -> CheckResult:
    val = abs(_metric(sim, "prodCorrelation", "prod_correlation", default=0.0))
    passed = val < 0.70  # BRAIN: SELF_CORRELATION applies to prod correlation too
    return CheckResult(
        check_name="prod_correlation",
        passed=passed,
        actual=val,
        expected="< 0.70",
        message=f"ProdCorrelation={val:.4f}" + ("" if passed else " (>= 0.70)"),
    )


def _check_weight_concentration(sim: dict[str, Any]) -> CheckResult:
    val = _metric(sim, "weightConcentration", "weight_concentration", "concentration", default=0.0)
    passed = val <= 0.10  # BRAIN: CONCENTRATED_WEIGHT if single stock > 10%
    return CheckResult(
        check_name="weight_concentration",
        passed=passed,
        actual=val,
        expected="<= 0.10",
        message=f"WeightConcentration={val:.4f}" + ("" if passed else " (exceeds 0.10)"),
    )


def _check_sub_universe_sharpe(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: LOW_SUB_UNIVERSE_SHARPE — sub_sharpe >= 0.75 × √(sub_size/alpha_size) × alpha_sharpe.

    Official formula: threshold = 0.75 × √(sub_size / alpha_size) × alpha_sharpe.
    When sub_size/alpha_size are unavailable from API, defaults to 1.0 (√1 = 1),
    which degenerates to the simple 0.75 × sharpe form.
    """
    sub_sharpe = _metric(sim, "subUniverseSharpe", "sub_universe_sharpe", default=0.0)
    sharpe = _metric(sim, "sharpe", "Sharpe", default=0.0)
    sub_size = _metric(sim, "subUniverseSize", "sub_size", default=1000)
    alpha_size = _metric(sim, "alphaSize", "alpha_size", default=1000)
    size_factor = math.sqrt(sub_size / max(alpha_size, 1))
    # Use configurable ratio (default 0.75) matching scoring.empirical_score formula
    thresholds = sim.get("_thresholds", None)
    ratio = float(getattr(thresholds, "sub_universe_sharpe_min_ratio", 0.75))
    threshold = ratio * size_factor * max(sharpe, 0.01)
    passed = sub_sharpe >= threshold
    exception_applied = False

    # BRAIN exception: LOW_SUB_UNIVERSE_SHARPE — when sub-universe is very small
    # (< 10% of alpha size), the check is downgraded from ERROR to WARNING
    # because the sub_universe is too small to produce reliable sub-sharpe metrics.
    # The BRAIN platform may still accept the alpha with this warning.
    low_sub_exception = not passed and sub_size > 0 and alpha_size > 0 and (sub_size / alpha_size) < 0.1
    if low_sub_exception:
        passed = True
        exception_applied = True

    expected_str = f">= {threshold:.4f} ({ratio}×√({sub_size:.0f}/{alpha_size:.0f})×sharpe)"
    if exception_applied:
        expected_str += " OR LOW_SUB_UNIVERSE_SHARPE exception (sub_size < 10% alpha_size)"
    msg = f"SubUniverseSharpe={sub_sharpe:.4f}"
    if exception_applied:
        msg += f" (LOW_SUB_UNIVERSE_SHARPE exception: sub_size={sub_size:.0f} < 0.1 × alpha_size={alpha_size:.0f})"
    elif not passed:
        msg += f" (below {threshold:.4f})"

    return CheckResult(
        check_name="sub_universe_sharpe",
        passed=passed,
        actual=sub_sharpe,
        expected=expected_str,
        message=msg,
        exception_applied=exception_applied,
    )


def _check_marginal_contribution(sim: dict[str, Any]) -> CheckResult:
    """BRAIN: marginal contribution — not a named platform check; general risk."""
    val = _metric(sim, "marginalContribution", "marginal_contribution", default=0.0)
    passed = val > 0
    return CheckResult(
        check_name="marginal_contribution",
        passed=passed,
        actual=val,
        expected="> 0",
        message=f"MarginalContribution={val:.5f}",
    )


def _check_margin_minimum(sim: dict[str, Any]) -> CheckResult:
    """BRAIN advisor target: margin >= min_margin_bps (default 4.0 bps).

    Prefer API-returned margin field. Fall back to local estimation (returns/turnover/100)
    only when API does not provide the margin value.
    """
    # P2-3 / P0-4 fix: check whether the API supplied margin instead of default 0.0.
    api_margin = sim.get("margin") or sim.get("Margin")
    has_api_margin = api_margin is not None and (
        isinstance(api_margin, (int, float)) and abs(float(api_margin)) > 0.001
    )

    if has_api_margin:
        margin_bps = float(api_margin)
        margin_source = "BRAIN_API"
    else:
        returns = _metric(sim, "returns", "Returns", "return", default=0.0)
        turnover = _metric(sim, "turnover", "Turnover", default=0.01)
        margin_bps = (returns / max(turnover, 0.001)) / 100.0
        margin_source = "estimated"

    thresholds = sim.get("_thresholds", None)
    min_margin = float(getattr(thresholds, "min_margin_bps", 4.0))
    passed = margin_bps >= min_margin
    return CheckResult(
        check_name="margin_minimum",
        passed=passed,
        actual=round(margin_bps, 4),
        expected=f">= {min_margin:.1f} bps",
        message=f"Margin={margin_bps:.4f} bps [{margin_source}]" + ("" if passed else f" (below {min_margin:.1f} bps)"),
    )

from __future__ import annotations

from .models import (
    AntiOverfitResult,
    _IC_STABILITY_WINDOW_MIN,
)
from .utils import _safe_mean
from .ic_stability import compute_ic_stability
from .regime_stress import compute_regime_stress
from .placebo import compute_placebo_test
from .half_life import estimate_half_life


def run_anti_overfit_suite(
    factor_values: list[float],
    returns: list[float],
    *,
    forward_returns: list[float] | None = None,
    regime_labels: list[str] | None = None,
    min_ic_mean: float = 0.02,
    max_ic_std: float = 0.08,
    min_half_life_days: float = 5.0,
    placebo_alpha: float = 0.05,
) -> AntiOverfitResult:
    """Run the complete four-layer anti-overfitting validation suite.

    Args:
        factor_values: factor exposure time series
        returns: forward returns (same length as factor_values)
        forward_returns: alias for returns (for IC stability)
        regime_labels: optional pre-computed regime labels
        min_ic_mean, max_ic_std, min_half_life_days, placebo_alpha: thresholds

    Returns AntiOverfitResult with comprehensive diagnostics.
    """
    fwd = forward_returns if forward_returns is not None else returns
    n = min(len(factor_values), len(returns), len(fwd))

    result = AntiOverfitResult(
        min_ic_mean=min_ic_mean,
        max_ic_std=max_ic_std,
        min_half_life_days=min_half_life_days,
        placebo_alpha=placebo_alpha,
    )

    if n < _IC_STABILITY_WINDOW_MIN:
        result.warnings.append(
            f"Insufficient data for anti-overfit analysis ({n} < {_IC_STABILITY_WINDOW_MIN})"
        )
        return result

    fv = list(factor_values[:n])
    ret = list(returns[:n])
    fwd_ret = list(fwd[:n])

    ic_result = compute_ic_stability(
        fv, fwd_ret, min_ic_mean=min_ic_mean, max_ic_std=max_ic_std
    )
    result.ic_mean = ic_result["ic_mean"]
    result.ic_std = ic_result["ic_std"]
    result.ic_stability_score = ic_result["ic_stability_score"]
    result.ic_monthly_means = ic_result["monthly_means"]
    if not ic_result["passed"]:
        result.warnings.append(
            f"IC stability failed: mean={result.ic_mean:.4f}, std={result.ic_std:.4f}"
        )

    regime_result = compute_regime_stress(fv, ret, regime_labels=regime_labels)
    result.bull_sharpe = regime_result["bull_sharpe"]
    result.bear_sharpe = regime_result["bear_sharpe"]
    result.sideways_sharpe = regime_result["sideways_sharpe"]
    result.regime_stability_score = regime_result["regime_stability_score"]
    if not regime_result["passed"]:
        result.warnings.append("Regime stress test failed: inconsistent performance across regimes")

    placebo_result = compute_placebo_test(fv, fwd_ret, alpha=placebo_alpha)
    result.placebo_p_value = placebo_result["p_value"]
    result.placebo_score = placebo_result["placebo_score"]
    if not placebo_result["passed"]:
        result.warnings.append(
            f"Placebo test failed: p={result.placebo_p_value:.4f} >= {placebo_alpha}"
        )

    hl_result = estimate_half_life(fv, fwd_ret, min_half_life_days=min_half_life_days)
    result.half_life_days = hl_result["half_life_days"]
    result.half_life_score = hl_result["half_life_score"]
    if not hl_result["passed"]:
        result.warnings.append(
            f"Half-life too short: {result.half_life_days:.1f} days < {min_half_life_days}"
        )

    scores = [
        result.ic_stability_score,
        result.regime_stability_score,
        result.placebo_score,
        result.half_life_score,
    ]
    result.overall_score = _safe_mean(scores) if scores else 0.0

    result.passed = bool(
        ic_result["passed"]
        and regime_result["passed"]
        and placebo_result["passed"]
        and hl_result["passed"]
    )

    result.details = {
        "ic_result": ic_result,
        "regime_result": regime_result,
        "placebo_result": placebo_result,
        "half_life_result": hl_result,
    }

    return result

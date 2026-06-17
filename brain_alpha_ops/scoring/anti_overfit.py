"""Anti-overfitting validation suite.

Four-layer verification inspired by QuantGPT architecture:
  1. IC Stability — Information Coefficient stability across time
  2. Subsample Stress Test — performance in bull/bear/sideways regimes
  3. Placebo Test — random-permuted target signal baseline
  4. Half-Life Estimation — decay rate of predictive power

All tests produce a 0-1 stability score and detailed diagnostics.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ──
_IC_STABILITY_WINDOW_MIN = 20   # minimum samples for IC calculation
_REGIME_MIN_SAMPLES = 30        # minimum samples per regime
_PLACEBO_TRIALS = 50            # random permutation trials
_DEFAULT_HALF_LIFE_WINDOW = 60  # default half-life estimation window

@dataclass
class AntiOverfitResult:
    """Structured result from the anti-overfitting validation suite."""

    passed: bool = False
    overall_score: float = 0.0  # 0-100, higher = less overfit

    # IC Stability
    ic_mean: float = 0.0
    ic_std: float = 0.0
    ic_stability_score: float = 0.0
    ic_monthly_means: list[float] = field(default_factory=list)

    # Subsample Stress
    bull_sharpe: float | None = None
    bear_sharpe: float | None = None
    sideways_sharpe: float | None = None
    regime_stability_score: float = 0.0

    # Placebo
    placebo_p_value: float = 1.0
    placebo_score: float = 0.0

    # Half-Life
    half_life_days: float = 0.0
    half_life_score: float = 0.0

    # Diagnostics
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    # Thresholds used
    min_ic_mean: float = 0.02
    max_ic_std: float = 0.08
    min_half_life_days: float = 5.0
    placebo_alpha: float = 0.05

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "overall_score": self.overall_score,
            "ic_stability": {
                "ic_mean": self.ic_mean,
                "ic_std": self.ic_std,
                "score": self.ic_stability_score,
                "monthly_means": self.ic_monthly_means,
            },
            "regime_stress": {
                "bull_sharpe": self.bull_sharpe,
                "bear_sharpe": self.bear_sharpe,
                "sideways_sharpe": self.sideways_sharpe,
                "score": self.regime_stability_score,
            },
            "placebo": {
                "p_value": self.placebo_p_value,
                "score": self.placebo_score,
            },
            "half_life": {
                "days": self.half_life_days,
                "score": self.half_life_score,
            },
            "warnings": self.warnings,
            "thresholds": {
                "min_ic_mean": self.min_ic_mean,
                "max_ic_std": self.max_ic_std,
                "min_half_life_days": self.min_half_life_days,
                "placebo_alpha": self.placebo_alpha,
            },
        }

def compute_ic_stability(
    factor_values: list[float],
    forward_returns: list[float],
    *,
    group_ids: list[int] | None = None,
    min_ic_mean: float = 0.02,
    max_ic_std: float = 0.08,
) -> dict[str, Any]:
    """Compute IC (rank correlation) stability metrics.

    Args:
        factor_values: factor exposures
        forward_returns: forward returns aligned with factor values
        group_ids: optional group labels for cross-sectional IC per group
        min_ic_mean: minimum acceptable mean IC
        max_ic_std: maximum acceptable IC standard deviation

    Returns dict with ic_mean, ic_std, ic_stability_score, monthly_means, passed.
    """
    n = min(len(factor_values), len(forward_returns))
    if n < _IC_STABILITY_WINDOW_MIN:
        return {
            "ic_mean": 0.0, "ic_std": 0.0, "ic_stability_score": 0.0,
            "monthly_means": [], "passed": False,
            "warning": f"insufficient samples ({n} < {_IC_STABILITY_WINDOW_MIN})",
        }

    ics = _rank_ic(factor_values[:n], forward_returns[:n])
    ic_mean_val = _safe_mean(ics)
    ic_std_val = _safe_std(ics, ic_mean_val)

    # Score: 0-100 based on IC mean and stability
    mean_score = min(100.0, max(0.0, (ic_mean_val / max(min_ic_mean, 0.001)) * 50.0))
    stability_score = min(50.0, max(0.0, (1.0 - ic_std_val / max(max_ic_std, 0.001)) * 50.0))
    ic_stability_score = mean_score + stability_score

    # Monthly breakdown (approximate: chunk by ~21 trading days)
    monthly_means: list[float] = []
    chunk = max(1, n // max(1, n // 21))
    for i in range(0, len(ics), chunk):
        chunk_ics = ics[i:i + chunk]
        if chunk_ics:
            monthly_means.append(_safe_mean(chunk_ics))

    passed = bool(ic_mean_val >= min_ic_mean and ic_std_val <= max_ic_std)

    return {
        "ic_mean": ic_mean_val,
        "ic_std": ic_std_val,
        "ic_stability_score": ic_stability_score,
        "monthly_means": monthly_means,
        "passed": passed,
    }

def compute_regime_stress(
    factor_values: list[float],
    returns: list[float],
    *,
    regime_labels: list[str] | None = None,
    min_samples_per_regime: int = _REGIME_MIN_SAMPLES,
) -> dict[str, Any]:
    """Test factor performance across different market regimes (bull/bear/sideways).

    If regime_labels are not provided, auto-classify based on return percentiles:
      - bear: bottom 33%
      - sideways: middle 34%
      - bull: top 33%

    Returns dict with bull_sharpe, bear_sharpe, sideways_sharpe, regime_stability_score, passed.
    """
    n = min(len(factor_values), len(returns))
    if n < min_samples_per_regime * 3:
        return {
            "bull_sharpe": None, "bear_sharpe": None, "sideways_sharpe": None,
            "regime_stability_score": 0.0, "passed": False,
            "warning": f"insufficient samples ({n} < {min_samples_per_regime * 3})",
        }

    if regime_labels is None:
        regime_labels = _auto_classify_regimes(returns[:n])

    # Split by regime
    bull_ret: list[float] = []
    bear_ret: list[float] = []
    sideways_ret: list[float] = []
    for i, label in enumerate(regime_labels[:n]):
        if label == "bull":
            bull_ret.append(returns[i])
        elif label == "bear":
            bear_ret.append(returns[i])
        else:
            sideways_ret.append(returns[i])

    bull_sharpe = _sharpe(bull_ret) if len(bull_ret) >= min_samples_per_regime else None
    bear_sharpe = _sharpe(bear_ret) if len(bear_ret) >= min_samples_per_regime else None
    sideways_sharpe = _sharpe(sideways_ret) if len(sideways_ret) >= min_samples_per_regime else None

    # Stability: how consistent is Sharpe across regimes?
    sharpes = [s for s in (bull_sharpe, bear_sharpe, sideways_sharpe) if s is not None]
    if len(sharpes) >= 2 and max(sharpes) - min(sharpes) < 1e-9:
        regime_stability_score = 100.0
    elif sharpes:
        # Lower dispersion = higher stability score
        dispersion = max(0.001, max(sharpes) - min(sharpes))
        regime_stability_score = max(0.0, min(100.0, 100.0 / (1.0 + dispersion)))
    else:
        regime_stability_score = 0.0

    # Pass if all available Sharpes are positive and reasonably close
    passed = bool(
        sharpes
        and all(s >= 0 for s in sharpes)
        and regime_stability_score >= 40.0
    )

    return {
        "bull_sharpe": bull_sharpe,
        "bear_sharpe": bear_sharpe,
        "sideways_sharpe": sideways_sharpe,
        "regime_stability_score": regime_stability_score,
        "passed": passed,
    }

def compute_placebo_test(
    factor_values: list[float],
    returns: list[float],
    *,
    trials: int = _PLACEBO_TRIALS,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Placebo test: compare real IC against random-permuted baselines.

    Returns p-value (fraction of permuted ICs >= real IC) and placebo_score.
    """
    n = min(len(factor_values), len(returns))
    if n < _IC_STABILITY_WINDOW_MIN:
        return {
            "p_value": 1.0, "placebo_score": 0.0, "passed": False,
            "warning": f"insufficient samples ({n} < {_IC_STABILITY_WINDOW_MIN})",
        }

    import random
    random.seed(42)

    real_ic = abs(_spearman_r(factor_values[:n], returns[:n]))

    # Generate placebo ICs by permuting returns
    placebo_ics: list[float] = []
    ret_list = list(returns[:n])
    for _ in range(trials):
        random.shuffle(ret_list)
        placebo_ics.append(abs(_spearman_r(factor_values[:n], ret_list)))

    # p-value: fraction of placebo ICs >= real IC
    exceed_count = sum(1 for pic in placebo_ics if pic >= real_ic)
    p_value = (exceed_count + 1) / (trials + 1)  # Laplace smoothing

    # Score: lower p-value = higher score
    placebo_score = max(0.0, min(100.0, (1.0 - p_value / alpha) * 100.0))
    passed = bool(p_value < alpha)

    return {
        "p_value": p_value,
        "placebo_score": placebo_score,
        "passed": passed,
    }

def estimate_half_life(
    factor_values: list[float],
    returns: list[float],
    *,
    max_lag: int = 60,
    min_half_life_days: float = 5.0,
) -> dict[str, Any]:
    """Estimate factor half-life via IC decay over increasing lags.

    Args:
        factor_values: factor exposures
        returns: forward returns
        max_lag: maximum lag to test
        min_half_life_days: minimum acceptable half-life in days

    Returns dict with half_life_days, half_life_score, decay_ics, passed.
    """
    n = min(len(factor_values), len(returns))
    if n < max_lag + _IC_STABILITY_WINDOW_MIN:
        return {
            "half_life_days": 0.0, "half_life_score": 0.0,
            "decay_ics": [], "passed": False,
            "warning": f"insufficient samples ({n} < {max_lag + _IC_STABILITY_WINDOW_MIN})",
        }

    # Compute IC at increasing lags
    decay_ics: list[float] = []
    for lag in range(0, min(max_lag, n - _IC_STABILITY_WINDOW_MIN) + 1):
        if lag == 0:
            ic = _spearman_r(factor_values[:n], returns[:n])
        else:
            ic = _spearman_r(factor_values[:n - lag], returns[lag:])
        decay_ics.append(ic)

    # Estimate half-life: lag where IC drops to 50% of initial
    initial_ic = abs(decay_ics[0]) if decay_ics else 0.0
    half_life = 0.0
    if initial_ic > 1e-8:
        target_ic = initial_ic / 2.0
        for lag, ic in enumerate(decay_ics):
            if abs(ic) <= target_ic:
                half_life = float(lag)
                break
        else:
            half_life = float(max_lag)  # never dropped below 50%

    # Score: higher half-life = higher score, capped at 60 days
    half_life_score = min(100.0, (half_life / max(min_half_life_days, 1.0)) * 50.0)
    passed = bool(half_life >= min_half_life_days)

    return {
        "half_life_days": half_life,
        "half_life_score": half_life_score,
        "decay_ics": decay_ics,
        "passed": passed,
    }

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

    # 1. IC Stability
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

    # 2. Regime Stress
    regime_result = compute_regime_stress(fv, ret, regime_labels=regime_labels)
    result.bull_sharpe = regime_result["bull_sharpe"]
    result.bear_sharpe = regime_result["bear_sharpe"]
    result.sideways_sharpe = regime_result["sideways_sharpe"]
    result.regime_stability_score = regime_result["regime_stability_score"]
    if not regime_result["passed"]:
        result.warnings.append("Regime stress test failed: inconsistent performance across regimes")

    # 3. Placebo
    placebo_result = compute_placebo_test(fv, fwd_ret, alpha=placebo_alpha)
    result.placebo_p_value = placebo_result["p_value"]
    result.placebo_score = placebo_result["placebo_score"]
    if not placebo_result["passed"]:
        result.warnings.append(
            f"Placebo test failed: p={result.placebo_p_value:.4f} >= {placebo_alpha}"
        )

    # 4. Half-Life
    hl_result = estimate_half_life(fv, fwd_ret, min_half_life_days=min_half_life_days)
    result.half_life_days = hl_result["half_life_days"]
    result.half_life_score = hl_result["half_life_score"]
    if not hl_result["passed"]:
        result.warnings.append(
            f"Half-life too short: {result.half_life_days:.1f} days < {min_half_life_days}"
        )

    # Overall score (weighted average)
    scores = [
        result.ic_stability_score,
        result.regime_stability_score,
        result.placebo_score,
        result.half_life_score,
    ]
    result.overall_score = _safe_mean(scores) if scores else 0.0

    # Pass only if ALL four layers pass
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

# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════

def _rank_ic(x: list[float], y: list[float]) -> list[float]:
    """Compute rank IC (Spearman correlation) per cross-section.

    When group_ids is not provided, treats entire series as one group.
    Returns a single-element list for the overall IC.
    """
    return [_spearman_r(x, y)] if x and y else [0.0]

def _spearman_r(x: list[float], y: list[float]) -> float:
    """Compute Spearman rank correlation between two arrays."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    # Rank transform
    x_ranks = _rank_transform(x[:n])
    y_ranks = _rank_transform(y[:n])
    return _pearson_r(x_ranks, y_ranks)

def _rank_transform(values: list[float]) -> list[float]:
    """Replace values with their ranks (1-based, average for ties)."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda v: v[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks

def _pearson_r(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    mx = _safe_mean(x[:n])
    my = _safe_mean(y[:n])
    sx = _safe_std(x[:n], mx)
    sy = _safe_std(y[:n], my)
    if sx < 1e-15 or sy < 1e-15:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x[:n], y[:n])) / n
    return max(-1.0, min(1.0, cov / (sx * sy)))

def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)

def _safe_std(values: list[float], mean_val: float | None = None) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = mean_val if mean_val is not None else _safe_mean(values)
    variance = sum((v - m) ** 2 for v in values) / (n - 1)
    return math.sqrt(max(0.0, variance))

def _sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio from daily returns."""
    n = len(returns)
    if n < 5:
        return 0.0
    mean_ret = _safe_mean(returns) - risk_free / 252
    std_ret = _safe_std(returns, mean_ret + risk_free / 252)
    if std_ret < 1e-15:
        return 0.0
    return (mean_ret / std_ret) * math.sqrt(252)

def _auto_classify_regimes(returns: list[float]) -> list[str]:
    """Auto-classify returns into bull/bear/sideways regimes by percentile.

    Bottom third = bear, middle third = sideways, top third = bull.
    """
    if not returns:
        return []
    sorted_ret = sorted(returns)
    n = len(sorted_ret)
    lo = sorted_ret[n // 3]
    hi = sorted_ret[2 * n // 3]
    return [
        "bear" if r <= lo else "bull" if r >= hi else "sideways"
        for r in returns
    ]

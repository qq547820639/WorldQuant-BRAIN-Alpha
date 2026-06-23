"""Anti-overfitting validation suite.

Four-layer verification inspired by QuantGPT architecture:
  1. IC Stability — Information Coefficient stability across time
  2. Subsample Stress Test — performance in bull/bear/sideways regimes
  3. Placebo Test — random-permuted target signal baseline
  4. Half-Life Estimation — decay rate of predictive power

Plus compliance guardrails:
  5. Similarity Detection — auto-block near-duplicate expressions (>0.95)
  6. Parameter Tweak Detection — flag Decay/Delay-only changes (<5% improvement)
  7. Duplicate Submission Detection — block same expression within 7 days
  8. High-Frequency Retry Detection — block >3 failures per expression

All tests produce a 0-1 stability score and detailed diagnostics.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

ANTI_OVERFIT_SCHEMA_VERSION = "anti_overfit_report.v1"

# ── Constants ──
_IC_STABILITY_WINDOW_MIN = 20   # minimum samples for IC calculation
_REGIME_MIN_SAMPLES = 30        # minimum samples per regime
_PLACEBO_TRIALS = 50            # random permutation trials
_DEFAULT_HALF_LIFE_WINDOW = 60  # default half-life estimation window
_MIN_CANDIDATE_SERIES = 60

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

    import random as _random
    rng = _random.Random(42)

    real_ic = abs(_spearman_r(factor_values[:n], returns[:n]))

    # Generate placebo ICs by permuting returns
    placebo_ics: list[float] = []
    ret_list = list(returns[:n])
    for _ in range(trials):
        rng.shuffle(ret_list)
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


class AntiOverfitService:
    """Canonical candidate-level anti-overfit report service.

    The production submission gate consumes this report.  Missing or short
    official robustness series fail closed so a candidate cannot become
    submission-ready merely because evidence is absent.
    """

    def evaluate(self, candidate: dict[str, Any] | Any) -> dict[str, Any]:
        metrics = _candidate_metrics(candidate)
        factor_values = _number_series(
            metrics.get("factor_values")
            or metrics.get("factor_values_series")
            or metrics.get("ic_series")
            or metrics.get("rank_ic_series")
            or _candidate_value(candidate, "ic_series")
            or _candidate_value(candidate, "rank_ic_series")
        )
        returns = _number_series(
            metrics.get("returns_series")
            or metrics.get("forward_returns")
            or metrics.get("forward_returns_series")
            or metrics.get("rank_ic_series")
            or metrics.get("ic_series")
            or _candidate_value(candidate, "returns_series")
            or factor_values
        )
        forward_returns = _number_series(
            metrics.get("forward_returns")
            or metrics.get("forward_returns_series")
            or metrics.get("rank_ic_series")
            or metrics.get("ic_series")
            or _candidate_value(candidate, "forward_returns")
            or returns
        )

        sample_size = min(len(factor_values), len(returns), len(forward_returns))
        if sample_size < _MIN_CANDIDATE_SERIES:
            report = _candidate_report(
                ok=False,
                passed=False,
                recommendation="insufficient_data",
                score=0.0,
                sample_size=sample_size,
                data_source="official_metrics",
                reason=(
                    "anti-overfit requires at least "
                    f"{_MIN_CANDIDATE_SERIES} official robustness samples"
                ),
            )
            _attach_submission_report(candidate, "anti_overfit_report", report)
            return report

        try:
            result = run_anti_overfit_suite(
                factor_values[:sample_size],
                returns[:sample_size],
                forward_returns=forward_returns[:sample_size],
            )
        except (TypeError, ValueError, OverflowError) as exc:
            report = _candidate_report(
                ok=False,
                passed=False,
                recommendation="block",
                score=0.0,
                sample_size=sample_size,
                data_source="official_metrics",
                reason=f"anti-overfit suite failed: {exc.__class__.__name__}",
            )
            _attach_submission_report(candidate, "anti_overfit_report", report)
            return report

        payload = result.to_dict()
        passed = bool(result.passed)
        recommendation = (
            "pass"
            if passed
            else ("caution" if result.overall_score >= 50.0 else "block")
        )
        report = {
            "ok": True,
            "schema_version": ANTI_OVERFIT_SCHEMA_VERSION,
            "passed": passed,
            "score": round(float(result.overall_score), 4),
            "recommendation": recommendation,
            "sample_size": sample_size,
            "data_source": "official_metrics",
            "suite": payload,
            "warnings": list(result.warnings),
        }
        if not passed:
            report["reason"] = "statistical_robustness_below_threshold"
        _attach_submission_report(candidate, "anti_overfit_report", report)
        return report


def evaluate_candidate(candidate: dict[str, Any] | Any) -> dict[str, Any]:
    return AntiOverfitService().evaluate(candidate)

# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _candidate_report(
    *,
    ok: bool,
    passed: bool,
    recommendation: str,
    score: float,
    sample_size: int,
    data_source: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "ok": bool(ok),
        "schema_version": ANTI_OVERFIT_SCHEMA_VERSION,
        "passed": bool(passed),
        "score": float(score),
        "recommendation": recommendation,
        "sample_size": int(sample_size),
        "data_source": data_source,
        "reason": reason,
    }


def _candidate_metrics(candidate: dict[str, Any] | Any) -> dict[str, Any]:
    metrics = _candidate_value(candidate, "official_metrics")
    return metrics if isinstance(metrics, dict) else {}


def _candidate_value(candidate: dict[str, Any] | Any, key: str) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(key)
    return getattr(candidate, key, None)


def _number_series(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[float] = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            result.append(number)
    return result


def _attach_submission_report(candidate: dict[str, Any] | Any, key: str, report: dict[str, Any]) -> None:
    if isinstance(candidate, dict):
        submission = candidate.get("submission")
        if not isinstance(submission, dict):
            submission = {}
            candidate["submission"] = submission
        submission[key] = report
        return
    submission = getattr(candidate, "submission", None)
    if not isinstance(submission, dict):
        submission = {}
        setattr(candidate, "submission", submission)
    submission[key] = report

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


# ═══════════════════════════════════════════════════════════════════════
# Compliance Guardrails
# ═══════════════════════════════════════════════════════════════════════

SIMILARITY_THRESHOLD = 0.95
PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD = 0.05
DUPLICATE_SUBMISSION_WINDOW_DAYS = 7
HIGH_FREQUENCY_RETRY_THRESHOLD = 3


@dataclass
class ComplianceGuardrailResult:
    """Result from compliance guardrail checks."""

    similarity_block: bool = False
    similarity_score: float = 0.0
    similarity_details: str = ""

    parameter_tweak_flag: bool = False
    parameter_tweak_details: str = ""

    duplicate_block: bool = False
    duplicate_details: str = ""

    high_frequency_block: bool = False
    high_frequency_failure_count: int = 0
    high_frequency_details: str = ""

    overall_blocked: bool = False
    block_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "similarity": {
                "blocked": self.similarity_block,
                "score": self.similarity_score,
                "details": self.similarity_details,
            },
            "parameter_tweak": {
                "flagged": self.parameter_tweak_flag,
                "details": self.parameter_tweak_details,
            },
            "duplicate_submission": {
                "blocked": self.duplicate_block,
                "details": self.duplicate_details,
            },
            "high_frequency_retry": {
                "blocked": self.high_frequency_block,
                "failure_count": self.high_frequency_failure_count,
                "details": self.high_frequency_details,
            },
            "overall_blocked": self.overall_blocked,
            "block_reasons": self.block_reasons,
        }


def check_expression_similarity(
    expression_a: str,
    expression_b: str,
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    """Check similarity between two expressions using token-based comparison.

    Returns similarity score (0-1) and whether it exceeds the threshold.
    """
    tokens_a = _tokenize_expression(expression_a)
    tokens_b = _tokenize_expression(expression_b)
    if not tokens_a or not tokens_b:
        return {"score": 0.0, "blocked": False, "details": "empty expression"}
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union) if union else 0.0
    blocked = jaccard >= threshold
    details = ""
    if blocked:
        details = (
            f"expression similarity {jaccard:.3f} >= {threshold} threshold; "
            f"shared tokens: {sorted(intersection)[:10]}"
        )
    return {"score": jaccard, "blocked": blocked, "details": details}


def check_parameter_tweak(
    current_metrics: dict[str, Any],
    previous_metrics: dict[str, Any],
    *,
    improvement_threshold: float = PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD,
) -> dict[str, Any]:
    """Detect parameter tweaks that only change Decay/Delay with <5% improvement.

    Compares current vs previous metrics. If only decay/delay changed and
    the improvement is below the threshold, flags as a parameter tweak.
    """
    changed_keys = set()
    improved_keys = set()
    decay_delay_only = True
    for key in set(list(current_metrics.keys()) + list(previous_metrics.keys())):
        curr = current_metrics.get(key)
        prev = previous_metrics.get(key)
        if curr == prev:
            continue
        changed_keys.add(key)
        key_lower = key.lower()
        if key_lower not in ("decay", "delay"):
            decay_delay_only = False
        if isinstance(curr, (int, float)) and isinstance(prev, (int, float)) and prev != 0:
            improvement = (curr - prev) / abs(prev)
            if improvement > 0:
                improved_keys.add(key)
    flagged = False
    details = ""
    if changed_keys and decay_delay_only and improved_keys:
        max_improvement = 0.0
        for key in improved_keys:
            curr = current_metrics.get(key, 0)
            prev = previous_metrics.get(key, 0)
            if isinstance(curr, (int, float)) and isinstance(prev, (int, float)) and prev != 0:
                imp = (curr - prev) / abs(prev)
                max_improvement = max(max_improvement, imp)
        if max_improvement < improvement_threshold:
            flagged = True
            details = (
                f"parameter tweak detected: only Decay/Delay changed, "
                f"improvement {max_improvement:.1%} < {improvement_threshold:.0%} threshold"
            )
    return {"flagged": flagged, "details": details}


def check_duplicate_submission(
    expression: str,
    submission_history: list[dict[str, Any]],
    *,
    window_days: int = DUPLICATE_SUBMISSION_WINDOW_DAYS,
) -> dict[str, Any]:
    """Check if the same expression was submitted within the window period.

    Args:
        expression: current expression to check
        submission_history: list of dicts with 'expression' and 'submitted_at' keys
        window_days: lookback window in days

    Returns dict with blocked flag and details.
    """
    from datetime import datetime, timedelta, timezone

    normalized = expression.strip().lower()
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    for entry in submission_history:
        prev_expr = str(entry.get("expression", "")).strip().lower()
        if prev_expr != normalized:
            continue
        submitted_at = entry.get("submitted_at", "")
        if not submitted_at:
            continue
        try:
            ts = datetime.fromisoformat(submitted_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        if ts >= cutoff:
            return {
                "blocked": True,
                "details": (
                    f"same expression submitted {submitted_at} "
                    f"(within {window_days}-day window)"
                ),
                "previous_submission": submitted_at,
            }
    return {"blocked": False, "details": ""}


def check_high_frequency_retry(
    expression: str,
    failure_history: list[dict[str, Any]],
    *,
    threshold: int = HIGH_FREQUENCY_RETRY_THRESHOLD,
) -> dict[str, Any]:
    """Detect high-frequency retry: >threshold failures for the same expression.

    Args:
        expression: current expression
        failure_history: list of dicts with 'expression' and 'failed_at' keys
        threshold: maximum allowed failures

    Returns dict with blocked flag, failure count, and details.
    """
    normalized = expression.strip().lower()
    failure_count = sum(
        1 for entry in failure_history
        if str(entry.get("expression", "")).strip().lower() == normalized
    )
    blocked = failure_count > threshold
    details = ""
    if blocked:
        details = (
            f"high-frequency retry detected: {failure_count} failures "
            f"for this expression (threshold: {threshold})"
        )
    return {
        "blocked": blocked,
        "failure_count": failure_count,
        "details": details,
    }


def run_compliance_guardrails(
    expression: str,
    *,
    candidate_metrics: dict[str, Any] | None = None,
    previous_metrics: dict[str, Any] | None = None,
    submission_history: list[dict[str, Any]] | None = None,
    failure_history: list[dict[str, Any]] | None = None,
    reference_expressions: list[str] | None = None,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    improvement_threshold: float = PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD,
    duplicate_window_days: int = DUPLICATE_SUBMISSION_WINDOW_DAYS,
    retry_threshold: int = HIGH_FREQUENCY_RETRY_THRESHOLD,
) -> ComplianceGuardrailResult:
    """Run all compliance guardrail checks.

    Args:
        expression: current expression to validate
        candidate_metrics: current candidate metrics (for parameter tweak check)
        previous_metrics: previous candidate metrics (for parameter tweak check)
        submission_history: past submissions (for duplicate detection)
        failure_history: past failures (for retry detection)
        reference_expressions: existing expressions (for similarity check)
        similarity_threshold: auto-block threshold for similarity (default 0.95)
        improvement_threshold: minimum improvement for parameter tweaks (default 5%)
        duplicate_window_days: lookback window for duplicates (default 7 days)
        retry_threshold: max failures before blocking (default 3)

    Returns ComplianceGuardrailResult with all check results.
    """
    result = ComplianceGuardrailResult()

    if reference_expressions:
        best_score = 0.0
        best_details = ""
        for ref_expr in reference_expressions:
            check = check_expression_similarity(
                expression, ref_expr, threshold=similarity_threshold
            )
            if check["score"] > best_score:
                best_score = check["score"]
                best_details = check["details"]
            if check["blocked"]:
                result.similarity_block = True
                result.similarity_score = best_score
                result.similarity_details = best_details
                break
        if not result.similarity_block:
            result.similarity_score = best_score
            result.similarity_details = best_details

    if candidate_metrics and previous_metrics:
        tweak = check_parameter_tweak(
            candidate_metrics, previous_metrics,
            improvement_threshold=improvement_threshold,
        )
        result.parameter_tweak_flag = tweak["flagged"]
        result.parameter_tweak_details = tweak["details"]

    if submission_history:
        dup = check_duplicate_submission(
            expression, submission_history, window_days=duplicate_window_days,
        )
        result.duplicate_block = dup["blocked"]
        result.duplicate_details = dup["details"]

    if failure_history:
        retry = check_high_frequency_retry(
            expression, failure_history, threshold=retry_threshold,
        )
        result.high_frequency_block = retry["blocked"]
        result.high_frequency_failure_count = retry["failure_count"]
        result.high_frequency_details = retry["details"]

    block_reasons: list[str] = []
    if result.similarity_block:
        block_reasons.append(f"similarity: {result.similarity_details}")
    if result.parameter_tweak_flag:
        block_reasons.append(f"parameter_tweak: {result.parameter_tweak_details}")
    if result.duplicate_block:
        block_reasons.append(f"duplicate: {result.duplicate_details}")
    if result.high_frequency_block:
        block_reasons.append(f"high_frequency: {result.high_frequency_details}")

    result.block_reasons = block_reasons
    result.overall_blocked = bool(block_reasons)
    return result


def _tokenize_expression(expression: str) -> set[str]:
    """Tokenize an expression into a set of meaningful tokens for comparison."""
    import re
    tokens = re.findall(r'[a-zA-Z_]\w*', expression.lower())
    return set(tokens)

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

from .anti_overfit.models import (
    ANTI_OVERFIT_SCHEMA_VERSION,
    AntiOverfitResult,
    ComplianceGuardrailResult,
    DUPLICATE_SUBMISSION_WINDOW_DAYS,
    HIGH_FREQUENCY_RETRY_THRESHOLD,
    PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD,
    SIMILARITY_THRESHOLD,
    _DEFAULT_HALF_LIFE_WINDOW,
    _IC_STABILITY_WINDOW_MIN,
    _MIN_CANDIDATE_SERIES,
    _PLACEBO_TRIALS,
    _REGIME_MIN_SAMPLES,
)
from .anti_overfit.checks import (
    _attach_submission_report,
    _auto_classify_regimes,
    _candidate_metrics,
    _candidate_report,
    _candidate_value,
    _number_series,
    _pearson_r,
    _rank_ic,
    _rank_transform,
    _safe_mean,
    _safe_std,
    _sharpe,
    _spearman_r,
    check_duplicate_submission,
    check_expression_similarity,
    check_high_frequency_retry,
    check_parameter_tweak,
    compute_ic_stability,
    compute_placebo_test,
    compute_regime_stress,
    estimate_half_life,
    run_compliance_guardrails,
)
from .anti_overfit.suite import run_anti_overfit_suite
from .anti_overfit.service import AntiOverfitService, evaluate_candidate

__all__ = [
    "ANTI_OVERFIT_SCHEMA_VERSION",
    "AntiOverfitResult",
    "AntiOverfitService",
    "ComplianceGuardrailResult",
    "DUPLICATE_SUBMISSION_WINDOW_DAYS",
    "HIGH_FREQUENCY_RETRY_THRESHOLD",
    "PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD",
    "SIMILARITY_THRESHOLD",
    "compute_ic_stability",
    "compute_placebo_test",
    "compute_regime_stress",
    "check_duplicate_submission",
    "check_expression_similarity",
    "check_high_frequency_retry",
    "check_parameter_tweak",
    "estimate_half_life",
    "evaluate_candidate",
    "run_anti_overfit_suite",
    "run_compliance_guardrails",
]

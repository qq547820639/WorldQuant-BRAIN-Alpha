from .models import (
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
from .dsr import compute_dsr
from .permutation import PermutationFilter, PermutationResult
from .checks import (
    _auto_classify_regimes,
    _pearson_r,
    _rank_ic,
    _rank_transform,
    _safe_mean,
    _safe_std,
    _sharpe,
    _spearman_r,
)
from .checks import compute_ic_stability
from .checks import compute_regime_stress
from .checks import compute_placebo_test
from .checks import estimate_half_life
from .checks import compute_permutation_test
from .suite import run_anti_overfit_suite
from .checks import (
    _attach_submission_report,
    _candidate_metrics,
    _candidate_report,
    _candidate_value,
    _number_series,
)
from .service import AntiOverfitService, evaluate_candidate
from .checks import (
    check_duplicate_submission,
    check_expression_similarity,
    check_high_frequency_retry,
    check_parameter_tweak,
    run_compliance_guardrails,
)

__all__ = [
    "ANTI_OVERFIT_SCHEMA_VERSION",
    "AntiOverfitResult",
    "AntiOverfitService",
    "ComplianceGuardrailResult",
    "DUPLICATE_SUBMISSION_WINDOW_DAYS",
    "HIGH_FREQUENCY_RETRY_THRESHOLD",
    "PARAMETER_TWEAK_IMPROVEMENT_THRESHOLD",
    "SIMILARITY_THRESHOLD",
    "compute_dsr",
    "compute_ic_stability",
    "compute_permutation_test",
    "compute_placebo_test",
    "compute_regime_stress",
    "check_duplicate_submission",
    "check_expression_similarity",
    "check_high_frequency_retry",
    "check_parameter_tweak",
    "estimate_half_life",
    "evaluate_candidate",
    "PermutationFilter",
    "PermutationResult",
    "run_anti_overfit_suite",
    "run_compliance_guardrails",
]

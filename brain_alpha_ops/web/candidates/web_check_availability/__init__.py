"""Alpha availability checks, batch job results, and risk guidance.

Subpackage of ``brain_alpha_ops.web.candidates``. Splits the original
``web_check_availability.py`` monolith into focused modules while preserving
the public API surface via re-exports.
"""

from __future__ import annotations

# Risk explanation builders + thresholds
from ._risk_explanations import (
    CLOUD_SELF_CORRELATION_THRESHOLD,
    CLOUD_SELF_CORRELATION_WARNING_THRESHOLD,
    _default_resolution_steps,
    _float,
    _int,
    _risk_level,
    build_cloud_self_correlation_explanation,
    build_context_health_explanation,
    build_state_navigation,
)

# Candidate availability checks
from ._availability import (
    CHECK_LABELS,
    ObservabilityPreflight,
    SafeErrorMessage,
    _cloud_self_correlation_check_context,
    _submission_decision_band,
    check_candidate_availability,
    cloud_row_expression,
    cloud_similarity_risk,
    cloud_status_for,
)

# Batch job helpers (types + helpers)
from ._batch_helpers import (
    ApiFromRunConfig,
    CheckAvailability,
    ErrorPayload,
    JobStoreLike,
    LedgerFactory,
    ObservabilityPreflight as _ObservabilityPreflightBatch,
    PassedCandidates,
    PayloadTruthy,
    RefreshCloudContext,
    RepositoryFactory,
    RunConfigFromPayload,
    SafeErrorMessage as _SafeErrorMessageBatch,
    _store_is_cancelled,
    _timing_payload,
    _update_check_batch_cancelled,
)

# Batch job main entrypoint
from ._batch_job import run_check_batch_job_service

__all__ = [
    # Constants
    "CLOUD_SELF_CORRELATION_THRESHOLD",
    "CLOUD_SELF_CORRELATION_WARNING_THRESHOLD",
    "CHECK_LABELS",
    # Type aliases
    "SafeErrorMessage",
    "ObservabilityPreflight",
    "JobStoreLike",
    "PassedCandidates",
    "RunConfigFromPayload",
    "ApiFromRunConfig",
    "RepositoryFactory",
    "LedgerFactory",
    "PayloadTruthy",
    "RefreshCloudContext",
    "CheckAvailability",
    "ErrorPayload",
    # Risk explanation builders
    "build_state_navigation",
    "build_cloud_self_correlation_explanation",
    "build_context_health_explanation",
    # Availability checks
    "check_candidate_availability",
    "cloud_status_for",
    "cloud_similarity_risk",
    "cloud_row_expression",
    # Batch job
    "run_check_batch_job_service",
]

"""Structured scoring and production gates.

This package splits the original ``scoring.py`` into focused sub-modules
while preserving the public API.  All public symbols are re-exported here
so that ``from brain_alpha_ops.research.scoring import build_scorecard``
continues to work unchanged.

Sub-modules:
  - ``_helpers``    : pure utility functions (``_num``, ``item``, ``check``, ...)
  - ``prior``       : prior_score, local_convergence_score, _parameterized_dimensions
  - ``empirical``   : empirical_score, calculate_fitness, self-correlation checks
  - ``guidance``    : assistant_guidance_score_adjustment
  - ``scorecard``   : build_scorecard, evaluate_quality_gate, decision_band,
                      submission_checklist, estimate_score_confidence,
                      SCORECARD_SCHEMA_VERSION, PRODUCTION_GATE_SCHEMA_VERSION
"""

from __future__ import annotations

from brain_alpha_ops.research._ratio import _ratio

from ._helpers import (
    _bounded_score,
    _format_empirical_failure,
    _guidance_outcome_status,
    _int_num,
    _normalize_confidence,
    _num,
    check,
    item,
)
from .empirical import (
    EMPIRICAL_CHECK_ITEM_NAMES,
    _build_self_correlation_item,
    _check_self_correlation_with_exception,
    _compute_empirical_metrics,
    calculate_fitness,
    empirical_score,
)
from .guidance import assistant_guidance_score_adjustment
from .prior import (
    _economic_logic_score,
    _parameterized_dimensions,
    local_convergence_score,
    prior_score,
)
from .scorecard import (
    PRODUCTION_GATE_SCHEMA_VERSION,
    SCORECARD_SCHEMA_VERSION,
    _scorecard_settings,
    build_scorecard,
    decision_band,
    estimate_score_confidence,
    evaluate_quality_gate,
    submission_checklist,
)

__all__ = [
    # Constants
    "SCORECARD_SCHEMA_VERSION",
    "PRODUCTION_GATE_SCHEMA_VERSION",
    "EMPIRICAL_CHECK_ITEM_NAMES",
    # Top-level API
    "build_scorecard",
    "prior_score",
    "local_convergence_score",
    "empirical_score",
    "submission_checklist",
    "evaluate_quality_gate",
    "decision_band",
    "estimate_score_confidence",
    "calculate_fitness",
    "assistant_guidance_score_adjustment",
    # Helpers (used externally by tests and compliance modules)
    "item",
    "check",
    "_ratio",
    "_num",
    "_int_num",
    "_bounded_score",
    "_economic_logic_score",
    "_format_empirical_failure",
    "_compute_empirical_metrics",
    "_check_self_correlation_with_exception",
    "_build_self_correlation_item",
    "_parameterized_dimensions",
    "_scorecard_settings",
    "_guidance_outcome_status",
    "_normalize_confidence",
]

"""Structured Alpha output configuration and quality diagnostics.

Subpackage split (formerly ``alpha_quality.py`` monolith):
  - ``constants``: module-level constants
  - ``utils``: pure utility helpers shared across builders
  - ``output_config``: ``build_alpha_output_config`` builder
  - ``reasons_format``: missing-field / config / expression-format reason builders
  - ``reasons_quality``: local-quality / scorecard / official-evidence / gate builders
  - ``diagnosis``: top-level ``diagnose_alpha_candidate`` and summary
"""

from __future__ import annotations

from .constants import (
    _REQUIRED_ALPHA_FIELDS,
    _REQUIRED_OFFICIAL_METRICS,
    _REQUIRED_SETTINGS_FIELDS,
    _RESERVED_WORDS,
)
from .utils import (
    _expression_profile,
    _extract_bracketed,
    _finite_number,
    _has_only_submission_blockers,
    _is_missing,
    _json_safe,
    _metric_value,
    _numeric_bounds,
    _ops_from_config,
    _parentheses_balance_error,
    _ratio,
    _reason,
    _split_args,
    _status_label,
)
from .output_config import build_alpha_output_config
from .reasons_format import (
    _add_expression_reasons,
    _add_generation_risk_reasons,
    _add_missing_candidate_reasons,
    _add_missing_config_reasons,
    _add_operator_signature_reasons,
)
from .reasons_quality import (
    _add_gate_reasons,
    _add_local_quality_reasons,
    _add_metric_bound,
    _add_official_evidence_reasons,
    _add_scorecard_reasons,
)
from .diagnosis import diagnose_alpha_candidate, summarize_quality_diagnostics

__all__ = [
    "build_alpha_output_config",
    "diagnose_alpha_candidate",
    "summarize_quality_diagnostics",
]

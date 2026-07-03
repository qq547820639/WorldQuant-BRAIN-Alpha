"""Compliance verification layer — enforces six technical red lines.

Merged module layout (Task 3.4 of extreme-consolidation-pass2):
  - ``redline_core.py``      : data structures + shared helpers (models + helpers)
  - ``redline_checks.py``    : six red-line verification checks (1-6)
  - ``redline_verifier.py``  : RedLineVerifier engine + CLI entry point

All former submodule paths (``redline_models``, ``redline_helpers``,
``redline_check_*``) are re-exported below for backward compatibility.
"""

from brain_alpha_ops.compliance.redline_checks import (
    _verify_redline_1_no_custom_extension,
    _verify_redline_2_threshold_zero_deviation,
    _verify_redline_3_dataset_ids,
    _verify_redline_4_parameter_traceability,
    _verify_redline_5_factor_coverage,
    _verify_redline_6_code_alignment,
)
from brain_alpha_ops.compliance.redline_core import (
    ComplianceReport,
    RedLineBlockedError,
    RedLineViolation,
    VALID_SEVERITIES,
    _candidate_generator_fallback_templates,
    _project_root,
    _runtime_storage_dir,
    _sample_official_fields_for_templates,
    _verification_blocked,
    _verify_generator_templates_against_official_context,
    logger,
)
from brain_alpha_ops.compliance.redline_verifier import RedLineVerifier

__all__ = [
    "RedLineVerifier",
    "ComplianceReport",
    "RedLineViolation",
    "RedLineBlockedError",
    "VALID_SEVERITIES",
    "logger",
    "_project_root",
    "_runtime_storage_dir",
    "_verification_blocked",
    "_verify_generator_templates_against_official_context",
    "_candidate_generator_fallback_templates",
    "_sample_official_fields_for_templates",
    "_verify_redline_1_no_custom_extension",
    "_verify_redline_2_threshold_zero_deviation",
    "_verify_redline_3_dataset_ids",
    "_verify_redline_4_parameter_traceability",
    "_verify_redline_5_factor_coverage",
    "_verify_redline_6_code_alignment",
]

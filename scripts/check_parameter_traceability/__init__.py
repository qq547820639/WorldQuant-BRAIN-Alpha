"""Automated parameter-to-documentation traceability validation.

Verifies that every production parameter used in the codebase can be traced
back to the official BRAIN API documentation, with zero configuration deviation.

Checks:
  1. All BrainSettings fields match official API parameter names.
  2. All thresholds in QualityThresholds match official BRAIN gate values.
  3. All API paths in OfficialAPIConfig match the documented endpoints.
  4. All dataset IDs used in generation come from official_datasets.json.
  5. All field/operator references come exclusively from official_*.json.
  6. No hardcoded fields or operators exist outside the official list.

Usage:
    python3 -m scripts.check_parameter_traceability --config config/run_config.json --json

Re-export subpackage: the former ``scripts/check_parameter_traceability.py``
monolith (798 lines) was split into ``_reference``, ``_checks``, and ``_audit``
submodules (Task A2 of deep-optimization-phase12). External import paths
``from scripts.check_parameter_traceability import ...`` continue to resolve
to this ``__init__.py``.
"""

from __future__ import annotations

from brain_alpha_ops.brain_api.canonical import (
    CANONICAL_API_PATHS,
    CANONICAL_SETTINGS,
    CANONICAL_THRESHOLDS,
)
from brain_alpha_ops.brain_api.rate_limit_policy import (
    OFFICIAL_RATE_LIMITS,
    validate_rate_limit_policy,
)

from ._audit import (
    _identity_values,
    load_official_data,
    main,
    run_parameter_audit,
)
from ._checks import (
    _coverage_path,
    _OPERATOR_ALIASES,
    _surface_warnings,
    check_official_element_coverage,
    validate_api_paths,
    validate_brain_settings,
    validate_dataset_ids,
    validate_generation_mutation_no_custom_extensions,
    validate_generator_templates_no_custom_extensions,
    validate_no_hardcoded_extensions,
    validate_thresholds,
)
from ._reference import (
    _API_ATTR_TO_CANONICAL,
    _canonical_allowed,
    _THRESHOLD_DOC_SOURCES,
    INTERNAL_ORCHESTRATION_SETTINGS,
    OFFICIAL_API_PATHS,
    OFFICIAL_BRAIN_SETTINGS,
    OFFICIAL_GATE_THRESHOLDS,
    OFFICIAL_SECURITY_RULES,
)

__all__ = [
    # Reference data
    "OFFICIAL_BRAIN_SETTINGS",
    "OFFICIAL_GATE_THRESHOLDS",
    "OFFICIAL_API_PATHS",
    "INTERNAL_ORCHESTRATION_SETTINGS",
    "OFFICIAL_SECURITY_RULES",
    # Re-exported canonical symbols
    "CANONICAL_API_PATHS",
    "CANONICAL_SETTINGS",
    "CANONICAL_THRESHOLDS",
    # Re-exported rate-limit policy symbols
    "OFFICIAL_RATE_LIMITS",
    "validate_rate_limit_policy",
    # Loaders
    "load_official_data",
    # Validation checks
    "validate_brain_settings",
    "validate_thresholds",
    "validate_api_paths",
    "validate_dataset_ids",
    "validate_no_hardcoded_extensions",
    "validate_generator_templates_no_custom_extensions",
    "validate_generation_mutation_no_custom_extensions",
    "check_official_element_coverage",
    # Runner / CLI
    "run_parameter_audit",
    "main",
]

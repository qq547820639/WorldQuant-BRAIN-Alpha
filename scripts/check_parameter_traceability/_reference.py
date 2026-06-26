"""BRAIN official API reference data for parameter traceability.

Constants describing the official BRAIN API parameter names, allowed values,
quality-gate thresholds, endpoint paths, and security rules. Sourced from
``brain_alpha_ops.brain_api.canonical`` so traceability, release gates,
scoring, and config validation cannot drift.

Split from the former ``scripts/check_parameter_traceability.py`` monolith
(Task A2 of deep-optimization-phase12).
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.brain_api.canonical import (
    CANONICAL_API_PATHS,
    CANONICAL_SETTINGS,
    CANONICAL_THRESHOLDS,
)

# ═══════════════════════════════════════════════════════════════════════
# BRAIN Official API Reference (from https://api.worldquantbrain.com docs)
# ═══════════════════════════════════════════════════════════════════════


def _canonical_allowed(setting_key: str) -> list[Any]:
    values = CANONICAL_SETTINGS.get(setting_key, set())
    return sorted(values)


# All official BRAIN settings with their expected types and allowed values.
OFFICIAL_BRAIN_SETTINGS: dict[str, dict[str, Any]] = {
    "instrumentType": {
        "type": "str",
        "allowed": _canonical_allowed("instrumentType"),
        "api_path": "/simulations",
        "doc_note": "Instrument type; BRAIN currently supports EQUITY only.",
    },
    "region": {
        "type": "str",
        "allowed": _canonical_allowed("region"),
        "api_path": "/simulations",
        "doc_note": (
            "Region options are sourced from brain_alpha_ops.brain_api.canonical "
            "to keep config schema, web settings, and parameter traceability aligned."
        ),
    },
    "universe": {
        "type": "str",
        "allowed": _canonical_allowed("universe"),
        "api_path": "/simulations",
        "doc_note": (
            "Universe options are sourced from brain_alpha_ops.brain_api.canonical "
            "to keep config schema, web settings, and parameter traceability aligned."
        ),
    },
    "delay": {
        "type": "int",
        "allowed": _canonical_allowed("delay"),
        "api_path": "/simulations",
        "doc_note": "Data delay in days. Allowed: 0 or 1. Default: 1.",
    },
    "decay": {
        "type": "int",
        "allowed": list(range(1, 21)),
        "api_path": "/simulations",
        "doc_note": "Weight decay factor. Range: 1-20. Default: 10.",
    },
    "neutralization": {
        "type": "str",
        "allowed": _canonical_allowed("neutralization"),
        "api_path": "/simulations",
        "doc_note": "Neutralization method for alpha weights.",
    },
    "truncation": {
        "type": "float",
        "allowed": [0.01, 0.02, 0.05, 0.10],
        "api_path": "/simulations",
        "doc_note": "Weight truncation percentile. Default: 0.05.",
    },
    "pasteurization": {
        "type": "str",
        "allowed": _canonical_allowed("pasteurization"),
        "api_path": "/simulations",
        "doc_note": "Pasteurization toggle for data integrity.",
    },
    "unitHandling": {
        "type": "str",
        "allowed": _canonical_allowed("unitHandling"),
        "api_path": "/simulations",
        "doc_note": (
            "Unit handling options are sourced from brain_alpha_ops.brain_api.canonical "
            "to avoid drift between validation, web dropdowns, and traceability checks."
        ),
    },
    "nanHandling": {
        "type": "str",
        "allowed": _canonical_allowed("nanHandling"),
        "api_path": "/simulations",
        "doc_note": "NaN handling toggle. Default: ON.",
    },
    "language": {
        "type": "str",
        "allowed": _canonical_allowed("language"),
        "api_path": "/simulations",
        "doc_note": "Expression language. Currently FASTEXPR only.",
    },
    "visualization": {
        "type": "bool",
        "allowed": [True, False],
        "api_path": "/simulations",
        "doc_note": "Return visualization data with simulation.",
    },
    "type": {
        "type": "str",
        "allowed": _canonical_allowed("type"),
        "api_path": "/simulations",
        "doc_note": "Alpha type. Default: REGULAR.",
    },
}

_THRESHOLD_DOC_SOURCES = {
    "min_sharpe": ("LOW_SHARPE check", ">="),
    "min_sharpe_delay0": ("LOW_SHARPE delay=0 check", ">="),
    "min_fitness": ("LOW_FITNESS check", ">="),
    "min_fitness_delay0": ("LOW_FITNESS delay=0 check", ">="),
    "min_turnover": ("LOW_TURNOVER check", ">="),
    "platform_max_turnover": ("HIGH_TURNOVER check", "<="),
    "max_self_correlation": ("SELF_CORRELATION check", "<"),
    "max_prod_correlation": ("PROD_CORRELATION check", "<"),
    "max_weight_concentration": ("CONCENTRATED_WEIGHT check", "<="),
    "sub_universe_sharpe_min_ratio": ("SUB_UNIVERSE_SHARPE check", ">="),
}

# Official BRAIN quality gate thresholds. Values are sourced from the canonical
# module so traceability, release gates, scoring, and config validation cannot drift.
OFFICIAL_GATE_THRESHOLDS: dict[str, dict[str, Any]] = {
    key: {
        "value": value,
        "comparison": _THRESHOLD_DOC_SOURCES.get(key, ("BRAIN Alpha Check", "=="))[1],
        "doc_source": _THRESHOLD_DOC_SOURCES.get(key, ("BRAIN Alpha Check", "=="))[0],
        "config_key": key,
    }
    for key, value in CANONICAL_THRESHOLDS.items()
}

_API_ATTR_TO_CANONICAL = {
    "authentication_path": "authentication",
    "simulations_path": "simulations",
    "data_categories_path": "data_categories",
    "data_sets_path": "data_sets",
    "data_set_path_template": "data_set_detail",
    "data_fields_path": "data_fields",
    "data_field_path_template": "data_field_detail",
    "operators_path": "operators",
    "user_alphas_path": "user_alphas",
    "alpha_correlations_path": "alpha_correlations",
    "user_profile_path": "user_profile",
    "alpha_check_path_template": "alpha_check",
    "alpha_submit_path_template": "alpha_submit",
    "alpha_path_template": "alpha_detail",
}

# Official BRAIN API endpoint paths. The path values come from canonical.py.
OFFICIAL_API_PATHS: dict[str, str] = {
    attr: CANONICAL_API_PATHS[canonical_key]
    for attr, canonical_key in _API_ATTR_TO_CANONICAL.items()
}

# Internal-only settings that are not BRAIN API parameters but used for
# pipeline orchestration. These are expected to be present and are NOT errors.
INTERNAL_ORCHESTRATION_SETTINGS: set[str] = {
    "dataset",  # used by DatasetSelector for generation, not a BRAIN API param
}

# Official BRAIN security requirements
OFFICIAL_SECURITY_RULES: list[dict[str, Any]] = [
    {
        "rule": "token_memory_only",
        "description": "JWT tokens must be stored in memory only, never persisted to disk.",
        "check": "Verify BrainAPI._session token is not written to filesystem.",
    },
    {
        "rule": "credential_redaction",
        "description": "Credentials must be redacted from all log output.",
        "check": "Verify redact_error_message() is used in all except blocks.",
    },
    {
        "rule": "credential_file_permissions",
        "description": "Credential files should have restricted file permissions.",
        "check": "Verify credential files have 600 permissions (owner read/write only).",
    },
    {
        "rule": "auto_reauthenticate_on_401",
        "description": "API client must automatically re-authenticate on HTTP 401.",
        "check": "Verify BrainAPI handles 401 with re-auth and retry.",
    },
]

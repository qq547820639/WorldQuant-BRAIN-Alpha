#!/usr/bin/env python3
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
    python3 scripts/check_parameter_traceability.py --config config/run_config.json --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS, CANONICAL_SETTINGS, CANONICAL_THRESHOLDS
from brain_alpha_ops.brain_api.rate_limit_policy import OFFICIAL_RATE_LIMITS, validate_rate_limit_policy

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

def load_official_data(data_dir: str) -> dict[str, Any]:
    """Load all official data files for validation."""
    result: dict[str, Any] = {
        "fields": [],
        "operators": [],
        "datasets": [],
    }
    base = Path(data_dir)

    for key, filename in [
        ("fields", "official_fields.json"),
        ("operators", "official_operators.json"),
        ("datasets", "official_datasets.json"),
    ]:
        path = base / filename
        if path.exists():
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
                result[key] = content if isinstance(content, list) else list(content.values())
            except (json.JSONDecodeError, OSError):
                pass

    return result


def _identity_values(rows: list[Any], keys: tuple[str, ...]) -> list[str]:
    """Return stable official identifiers from mixed official context rows."""
    values: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in keys:
                value = str(row.get(key) or "").strip()
                if value:
                    values.append(value)
        else:
            value = str(row or "").strip()
            if value:
                values.append(value)
    return values


def validate_brain_settings(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate BrainSettings against official API parameter definitions.

    Returns list of issues found.
    """
    issues: list[dict[str, Any]] = []

    # Check that all used settings are known
    for key, value in settings.items():
        if key in INTERNAL_ORCHESTRATION_SETTINGS:
            continue  # Internal pipeline settings, not BRAIN API parameters
        if key not in OFFICIAL_BRAIN_SETTINGS:
            issues.append({
                "severity": "ERROR",
                "check": "unknown_setting",
                "details": f"Setting '{key}' is not in the official BRAIN API parameter list.",
                "fix": "Remove non-standard setting or verify with BRAIN documentation.",
            })
            continue

        spec = OFFICIAL_BRAIN_SETTINGS[key]
        allowed = spec.get("allowed", [])

        if allowed and value not in allowed:
            issues.append({
                "severity": "ERROR",
                "check": "invalid_setting_value",
                "details": f"Setting '{key}' has value '{value}', "
                           f"but BRAIN API allows: {allowed}",
                "fix": f"Change '{key}' to one of: {allowed}",
            })

    # Check that all required settings are present (optional settings check)
    for key in ["instrumentType", "region", "universe", "delay", "language", "type"]:
        if key not in settings:
            issues.append({
                "severity": "WARNING",
                "check": "missing_required_setting",
                "details": f"Required setting '{key}' is missing from configuration.",
                "fix": f"Add '{key}' to BrainSettings with a valid value.",
            })

    return issues


def validate_thresholds(thresholds: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate QualityThresholds against official BRAIN gate values.

    Returns list of issues found.
    """
    issues: list[dict[str, Any]] = []

    for key, spec in OFFICIAL_GATE_THRESHOLDS.items():
        config_key = spec.get("config_key", key)
        actual = thresholds.get(config_key)
        if actual is None:
            issues.append({
                "severity": "WARNING",
                "check": "missing_threshold",
                "details": f"Threshold '{key}' is not defined. "
                           f"BRAIN official value: {spec['value']} ({spec['doc_source']}).",
                "fix": f"Set '{key}' to {spec['value']}.",
            })
            continue

        expected = spec["value"]
        if float(actual) != expected:
            issues.append({
                "severity": "ERROR",
                "check": "threshold_deviation",
                "details": f"Threshold '{key}' is {actual}, but BRAIN official value is {expected} "
                           f"({spec['doc_source']}). This is a ZERO-DEVIATION requirement.",
                "fix": f"Set '{key}' to exactly {expected}.",
            })

    return issues


def validate_api_paths(api_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate OfficialAPIConfig paths against documented endpoints.

    Returns list of issues found.
    """
    issues: list[dict[str, Any]] = []

    for config_key, official_path in OFFICIAL_API_PATHS.items():
        actual = api_config.get(config_key)
        if actual is None:
            issues.append({
                "severity": "WARNING",
                "check": "missing_api_path",
                "details": f"API path '{config_key}' is not configured.",
                "fix": f"Set '{config_key}' to '{official_path}'.",
            })
            continue

        if str(actual).strip("/") != official_path.strip("/"):
            issues.append({
                "severity": "ERROR",
                "check": "api_path_deviation",
                "details": f"API path '{config_key}' is '{actual}', "
                           f"but BRAIN official endpoint is '{official_path}'.",
                "fix": f"Set '{config_key}' to '{official_path}'.",
            })

    return issues


def validate_dataset_ids(
    datasets: list[str],
    official_dataset_ids: list[str],
) -> list[dict[str, Any]]:
    """Validate that all used dataset IDs come from the official list.

    Returns list of issues found.
    """
    issues: list[dict[str, Any]] = []

    official_set = set(official_dataset_ids)
    for ds_id in datasets:
        if ds_id and ds_id not in official_set:
            issues.append({
                "severity": "ERROR",
                "check": "unknown_dataset_id",
                "details": f"Dataset ID '{ds_id}' is not in the official dataset list: "
                           f"{sorted(official_set)}",
                "fix": f"Use one of the official datasets from official_datasets.json.",
            })

    return issues


def validate_no_hardcoded_extensions(
    fields: list[str],
    operators: list[str],
    official_fields: list[str],
    official_operators: list[str],
) -> list[dict[str, Any]]:
    """Verify no custom fields or operators exist outside the official list.

    Returns list of issues found.
    """
    issues: list[dict[str, Any]] = []
    official_field_set = {str(f).lower() for f in official_fields}
    official_operator_set = {str(o).lower() for o in official_operators}

    for field in fields:
        if str(field).lower() not in official_field_set:
            issues.append({
                "severity": "ERROR",
                "check": "custom_field",
                "details": f"Field '{field}' is not in the official BRAIN field list. "
                           f"Custom fields are STRICTLY FORBIDDEN.",
                "fix": "Remove the custom field or verify it exists in the BRAIN platform.",
            })

    for operator in operators:
        if str(operator).lower() not in official_operator_set:
            issues.append({
                "severity": "ERROR",
                "check": "custom_operator",
                "details": f"Operator '{operator}' is not in the official BRAIN operator list. "
                           f"Custom operators are STRICTLY FORBIDDEN.",
                "fix": "Remove the custom operator or verify it exists in the BRAIN platform.",
            })

    return issues


def validate_generator_templates_no_custom_extensions(
    official_fields: list[str],
    official_operators: list[str],
) -> list[dict[str, Any]]:
    """Validate fallback templates by rendering them with official sample fields."""
    from brain_alpha_ops.compliance.redline_helpers import (
        _candidate_generator_fallback_templates,
        _sample_official_fields_for_templates,
    )

    issues: list[dict[str, Any]] = []
    official_field_set = {str(item).lower() for item in official_fields if str(item).strip()}
    official_operator_set = {str(item).lower() for item in official_operators if str(item).strip()}
    templates = _candidate_generator_fallback_templates()
    if not official_field_set:
        return [{
            "severity": "ERROR",
            "check": "official_fields_empty",
            "details": "official_fields.json has no usable field identifiers.",
            "fix": "Refresh official_fields.json from the BRAIN platform before generation.",
        }]
    if not official_operator_set:
        return [{
            "severity": "ERROR",
            "check": "official_operators_empty",
            "details": "official_operators.json has no usable operator identifiers.",
            "fix": "Refresh official_operators.json from the BRAIN platform before generation.",
        }]

    sample_fields = _sample_official_fields_for_templates(official_field_set)
    allowed_literals = {"nan", "inf", "std"}
    for template in templates:
        rendered = (
            template
            .replace("{f1}", sample_fields["f1"])
            .replace("{f2}", sample_fields["f2"])
            .replace("{w}", "20")
        )
        called_operators = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", rendered.lower()))
        tokens = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", rendered.lower()))
        field_tokens = sorted(tokens - called_operators - allowed_literals)
        issues.extend(
            validate_no_hardcoded_extensions(
                field_tokens,
                sorted(called_operators),
                list(official_field_set),
                list(official_operator_set),
            )
        )
    for issue in issues:
        issue["details"] = f"CandidateGenerator fallback template violation: {issue['details']}"
    return issues


_OPERATOR_ALIASES = {
    "+": "add", "-": "subtract", "*": "multiply", "/": "divide",
    "group_z_score": "group_zscore", "ts_std": "ts_std_dev", "ts_z_score": "ts_zscore",
}


def validate_generation_mutation_no_custom_extensions(
    official_fields: list[str],
    official_operators: list[str],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    coverage_paths: list[dict[str, Any]] = []

    template_issues = validate_generator_templates_no_custom_extensions(official_fields, official_operators)
    issues.extend(template_issues)
    coverage_paths.append(_coverage_path("generator_fallback_templates", "brain_alpha_ops.research.generator.CandidateGenerator._generate_fallback", "blocking", "render fallback templates with official sample fields and validate rendered fields/operators", template_issues))

    try:
        from brain_alpha_ops.research import evolution
        evolution_fields = sorted(str(item).lower() for item in evolution._COMMON_FIELDS)
        evolution_ops = sorted(str(item).lower() for item in (evolution._UNARY_OPERATORS | evolution._BINARY_OPERATORS | evolution._GROUP_OPERATORS | evolution._WINDOW_OPERATORS))
        evolution_issues, evolution_details = _surface_warnings(
            "evolution_mutation", evolution_fields, evolution_ops, official_fields, official_operators
        )
    except Exception as exc:
        evolution_issues = [{"severity": "ERROR", "check": "generation_surface_import_failed", "details": f"Failed to inspect evolution mutation surface: {exc}", "fix": "Fix the evolution import and rerun traceability."}]
        evolution_details = {}
    issues.extend(evolution_issues)
    coverage_paths.append(_coverage_path("evolution_mutation_engine", "brain_alpha_ops.research.evolution.MutationEngine", "warning", "inspect mutation field/operator constants against official context names or FASTEXPR aliases", evolution_issues, evolution_details))

    try:
        from brain_alpha_ops.research.generator import OFFICIAL_OPERATOR_SUBSTITUTE_FAMILIES
        legacy_ops = sorted({str(operator).lower() for operators in OFFICIAL_OPERATOR_SUBSTITUTE_FAMILIES.values() for operator in operators})
        legacy_issues, legacy_details = _surface_warnings("legacy_mutation", [], legacy_ops, official_fields, official_operators)
        legacy_details["operator_source"] = "OFFICIAL_OPERATOR_SUBSTITUTE_FAMILIES"
        legacy_details["field_source"] = "caller-provided field_pool; no new fields when field_pool is absent"
    except Exception as exc:
        legacy_issues = [{"severity": "ERROR", "check": "generation_surface_import_failed", "details": f"Failed to inspect legacy operator substitution surface: {exc}", "fix": "Fix the generator import and rerun traceability."}]
        legacy_details = {}
    issues.extend(legacy_issues)
    coverage_paths.append(_coverage_path("legacy_mutate_expression", "brain_alpha_ops.research.generator.mutate_expression", "warning", "inspect legacy mutation operator family constants against official context names or FASTEXPR aliases", legacy_issues, legacy_details))

    return {
        "coverage_scope": ["generator_fallback_templates", "evolution_mutation_engine", "legacy_mutate_expression"],
        "coverage_statement": (
            "no_custom_extension covers generator/evolution/legacy mutation key paths; "
            "fallback templates are the blocking rendered-expression check, while evolution and legacy mutation paths "
            "are explicitly tracked as source-constant coverage so fallback-only evidence is not reported as full coverage."
        ),
        "coverage_paths": coverage_paths,
        "issues": issues,
    }


def _surface_warnings(check: str, fields: list[str], operators: list[str], official_fields: list[str], official_operators: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    official_field_set = {str(item).lower() for item in official_fields if str(item).strip()}
    official_operator_set = {str(item).lower() for item in official_operators if str(item).strip()}
    missing_fields = [field for field in fields if field not in official_field_set]
    missing_operators = [op for op in operators if _OPERATOR_ALIASES.get(op, op) not in official_operator_set]
    issues = []
    if missing_fields:
        issues.append({"severity": "WARNING", "check": f"{check}_field_source_unverified", "details": "Unverified field constants: " + ", ".join(missing_fields), "fix": "Refresh official_fields.json or supply official runtime fields."})
    if missing_operators:
        issues.append({"severity": "WARNING", "check": f"{check}_operator_source_unverified", "details": "Unverified operator constants: " + ", ".join(missing_operators), "fix": "Align operator constants with official_operators.json or document an official FASTEXPR alias."})
    return issues, {
        "field_constants_checked": len(fields),
        "operator_literals_checked": len(operators),
        "unverified_fields": missing_fields,
        "unverified_operators": missing_operators,
    }


def _coverage_path(path: str, source: str, enforcement: str, method: str, issues: list[dict[str, Any]], details: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {"path": path, "source": source, "checked": True, "enforcement": enforcement, "method": method, "issues_found": len(issues), "passed": not any(issue["severity"] == "ERROR" for issue in issues)}
    if details:
        result["details"] = details
    return result


def check_official_element_coverage(
    official_fields: list[str],
    official_operators: list[str],
    official_datasets: list[str],
) -> dict[str, Any]:
    """Check that all official BRAIN elements are accounted for in the system.

    Returns coverage report.
    """
    return {
        "total_fields": len(official_fields),
        "total_operators": len(official_operators),
        "total_datasets": len(official_datasets),
        "note": (
            "All BRAIN platform elements are available for use. "
            "The system does not limit which official elements can be used; "
            "generation strategy determines which subset is active at any time."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# Main runner
# ═══════════════════════════════════════════════════════════════════════

def run_parameter_audit(
    config_path: str | None = None,
    *,
    data_dir: str = "data",
) -> dict[str, Any]:
    """Run the full parameter traceability audit.

    Args:
        config_path: optional path to run_config.json.
        data_dir: directory containing official_*.json files.

    Returns:
        dict with audit results, issues list, and pass/fail status.
    """
    all_issues: list[dict[str, Any]] = []
    audit_results: dict[str, Any] = {}

    # Load official data
    official_data = load_official_data(data_dir)
    official_field_names = _identity_values(official_data.get("fields", []), ("id", "name"))
    official_operator_names = _identity_values(official_data.get("operators", []), ("name", "id"))
    official_dataset_ids = _identity_values(official_data.get("datasets", []), ("id",))

    # Load config if available
    config: dict[str, Any] = {}
    if config_path:
        try:
            config_data = json.loads(Path(config_path).read_text(encoding="utf-8"))
            config = config_data
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    # 1. Validate BrainSettings
    settings = config.get("ops", {}).get("settings", {})
    if settings:
        issues = validate_brain_settings(settings)
        all_issues.extend(issues)
        audit_results["settings_check"] = {
            "checked": len(OFFICIAL_BRAIN_SETTINGS),
            "issues_found": len(issues),
            "passed": not any(i["severity"] == "ERROR" for i in issues),
        }

    # 2. Validate thresholds
    thresholds = config.get("ops", {}).get("thresholds", {})
    if thresholds:
        issues = validate_thresholds(thresholds)
        all_issues.extend(issues)
        audit_results["thresholds_check"] = {
            "checked": len(OFFICIAL_GATE_THRESHOLDS),
            "issues_found": len(issues),
            "passed": not any(i["severity"] == "ERROR" for i in issues),
        }

    # 3. Validate API paths
    api_config = config.get("ops", {}).get("official_api", {})
    if api_config:
        issues = validate_api_paths(api_config)
        all_issues.extend(issues)
        audit_results["api_paths_check"] = {
            "checked": len(OFFICIAL_API_PATHS),
            "issues_found": len(issues),
            "passed": not any(i["severity"] == "ERROR" for i in issues),
        }

    # 4. Validate official-call rate limit and retry policy
    budget = config.get("ops", {}).get("budget", {})
    if budget or api_config:
        issues = validate_rate_limit_policy(budget, api_config)
        all_issues.extend(issues)
        audit_results["rate_limit_policy_check"] = {
            "checked": 5,
            "issues_found": len(issues),
            "passed": not any(i["severity"] == "ERROR" for i in issues),
        }

    # 5. Validate dataset IDs
    ds_config = config.get("ops", {}).get("settings", {}).get("dataset", "")
    if ds_config:
        issues = validate_dataset_ids([ds_config], official_dataset_ids)
        all_issues.extend(issues)
        audit_results["dataset_ids_check"] = {
            "checked": 1,
            "issues_found": len(issues),
            "passed": not any(i["severity"] == "ERROR" for i in issues),
        }

    # 6. Field/operator no-custom-extension check
    extension_result = validate_generation_mutation_no_custom_extensions(
        official_field_names,
        official_operator_names,
    )
    extension_issues = extension_result["issues"]
    all_issues.extend(extension_issues)
    blocking_extension_issues = [issue for issue in extension_issues if issue["severity"] == "ERROR"]
    warning_extension_issues = [issue for issue in extension_issues if issue["severity"] == "WARNING"]
    audit_results["no_custom_extension_check"] = {
        "checked": len(official_field_names) + len(official_operator_names),
        "surfaces_checked": len(extension_result["coverage_paths"]),
        "surface_coverage": extension_result["coverage_paths"],
        "coverage_scope": extension_result["coverage_scope"],
        "coverage_paths": extension_result["coverage_paths"],
        "coverage_statement": extension_result["coverage_statement"],
        "template_checks": next(
            (
                item["issues_found"]
                for item in extension_result["coverage_paths"]
                if item["path"] == "generator_fallback_templates"
            ),
            0,
        ),
        "issues_found": len(extension_issues),
        "warnings_found": len(warning_extension_issues),
        "passed": not blocking_extension_issues,
    }

    # 7. Official context lineage check.  This is enforced only when a config is
    # supplied so read-only inventory runs without a config remain informational.
    if config_path:
        from brain_alpha_ops.data.official_context_validation import validate_official_context

        context_validation = validate_official_context(data_dir=data_dir)
        context_issues: list[dict[str, Any]] = []
        for finding in context_validation.get("findings", []):
            severity = "ERROR" if finding.get("severity") == "BLOCKING" else "WARNING"
            context_issues.append({
                "severity": severity,
                "check": f"official_context_{finding.get('code', 'finding')}",
                "details": str(finding.get("message") or "Official context validation failed."),
                "fix": "Refresh official context from BRAIN and verify metadata/lineage before release.",
            })
        all_issues.extend(context_issues)
        audit_results["official_context_validation"] = {
            "checked": 3,
            "issues_found": len(context_issues),
            "blocking_count": context_validation.get("blocking_count", 0),
            "passed": bool(context_validation.get("blocking_ok")),
            "lineage": context_validation.get("lineage", {}),
        }

    # 8. Element coverage check
    coverage = check_official_element_coverage(
        official_field_names, official_operator_names, official_dataset_ids
    )
    audit_results["element_coverage"] = coverage

    # Overall status
    errors = [i for i in all_issues if i["severity"] == "ERROR"]
    warnings = [i for i in all_issues if i["severity"] == "WARNING"]

    return {
        "audit_version": "parameter_traceability.v1",
        "passed": len(errors) == 0,
        "total_issues": len(all_issues),
        "errors": len(errors),
        "warnings": len(warnings),
        "errors_list": errors,
        "warnings_list": warnings,
        "checks": audit_results,
        "official_reference": {
            "settings_documented": len(OFFICIAL_BRAIN_SETTINGS),
            "thresholds_documented": len(OFFICIAL_GATE_THRESHOLDS),
            "api_paths_documented": len(OFFICIAL_API_PATHS),
            "source": "https://api.worldquantbrain.com documentation",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BRAIN parameter-to-documentation traceability audit."
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to run_config.json for parameter validation.",
    )
    parser.add_argument(
        "--data-dir", default="data",
        help="Directory containing official_*.json files.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output machine-readable JSON.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    result = run_parameter_audit(
        config_path=args.config,
        data_dir=args.data_dir,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        status = "✅ PASSED" if result["passed"] else "❌ FAILED"
        print(f"BRAIN Parameter Traceability Audit: {status}")
        print(f"  Errors: {result['errors']}, Warnings: {result['warnings']}")
        print()

        for check_name, check_result in result["checks"].items():
            if isinstance(check_result, dict) and "passed" in check_result:
                icon = "✅" if check_result["passed"] else "❌"
                print(f"  {icon} {check_name}: {check_result['checked']} checked, "
                      f"{check_result['issues_found']} issue(s)")

        if result["errors_list"]:
            print(f"\n🔴 ERRORS ({len(result['errors_list'])}):")
            for issue in result["errors_list"]:
                print(f"  - [{issue['check']}] {issue['details']}")
                print(f"    Fix: {issue['fix']}")

        if result["warnings_list"]:
            print(f"\n🟡 WARNINGS ({len(result['warnings_list'])}):")
            for issue in result["warnings_list"]:
                print(f"  - [{issue['check']}] {issue['details']}")

    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

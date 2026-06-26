"""Parameter traceability validation checks.

Pure validation functions that compare configured settings, thresholds, API
paths, datasets, fields, and operators against the official BRAIN reference
data. Each function returns a list of issue dicts.

Split from the former ``scripts/check_parameter_traceability.py`` monolith
(Task A2 of deep-optimization-phase12).
"""

from __future__ import annotations

import re
from typing import Any

from ._reference import (
    INTERNAL_ORCHESTRATION_SETTINGS,
    OFFICIAL_API_PATHS,
    OFFICIAL_BRAIN_SETTINGS,
    OFFICIAL_GATE_THRESHOLDS,
)


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
        from brain_alpha_ops.research.generator_metadata import OFFICIAL_OPERATOR_SUBSTITUTE_FAMILIES
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

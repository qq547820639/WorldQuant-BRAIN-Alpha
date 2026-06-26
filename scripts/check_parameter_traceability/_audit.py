"""Parameter traceability audit runner and official-data loaders.

Loads official BRAIN reference data (``official_*.json``), orchestrates the
full traceability audit, and exposes the ``main`` CLI entry point.

Split from the former ``scripts/check_parameter_traceability.py`` monolith
(Task A2 of deep-optimization-phase12).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from brain_alpha_ops.brain_api.rate_limit_policy import validate_rate_limit_policy

from ._checks import (
    check_official_element_coverage,
    validate_api_paths,
    validate_brain_settings,
    validate_dataset_ids,
    validate_generation_mutation_no_custom_extensions,
    validate_thresholds,
)
from ._reference import (
    OFFICIAL_API_PATHS,
    OFFICIAL_BRAIN_SETTINGS,
    OFFICIAL_GATE_THRESHOLDS,
)


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
        status = "PASSED" if result["passed"] else "FAILED"
        print(f"BRAIN Parameter Traceability Audit: {status}")
        print(f"  Errors: {result['errors']}, Warnings: {result['warnings']}")
        print()

        for check_name, check_result in result["checks"].items():
            if isinstance(check_result, dict) and "passed" in check_result:
                icon = "OK" if check_result["passed"] else "FAIL"
                print(f"  {icon} {check_name}: {check_result['checked']} checked, "
                      f"{check_result['issues_found']} issue(s)")

        if result["errors_list"]:
            print(f"\nERRORS ({len(result['errors_list'])}):")
            for issue in result["errors_list"]:
                print(f"  - [{issue['check']}] {issue['details']}")
                print(f"    Fix: {issue['fix']}")

        if result["warnings_list"]:
            print(f"\nWARNINGS ({len(result['warnings_list'])}):")
            for issue in result["warnings_list"]:
                print(f"  - [{issue['check']}] {issue['details']}")

    return 0 if result["passed"] else 1

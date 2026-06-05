#!/usr/bin/env python3
"""Automated BRAIN canonical compliance verification.

Performs zero-deviation comparison between:
1. Configured thresholds vs BRAIN canonical thresholds
2. Configured API paths vs BRAIN canonical API paths
3. Configured settings vs BRAIN allowed enum values
4. Scoring simulation output vs BRAIN official API output
5. Field/operator definitions vs BRAIN official context

Usage:
    python scripts/verify_canonical_compliance.py
    python scripts/verify_canonical_compliance.py --json
    python scripts/verify_canonical_compliance.py --strict
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent


def _load_config(config_path: str | None = None) -> Any:
    """Load RunConfig from the specified or default config path."""
    sys.path.insert(0, str(_PROJECT_ROOT))
    from brain_alpha_ops.config import load_run_config

    return load_run_config(
        Path(config_path) if config_path else None
    )


def _context_validation_for_data_dir(data_dir: Path) -> dict[str, Any]:
    """Validate persisted official context without falling back to heuristics."""
    from brain_alpha_ops.data.official_context_validation import validate_official_context

    return validate_official_context(data_dir=data_dir)


# ═══════════════════════════════════════════════════════════════════════
# Check 1: Threshold Zero Deviation
# ═══════════════════════════════════════════════════════════════════════

def _check_thresholds(run_config: Any) -> dict[str, Any]:
    """Verify all configured thresholds match BRAIN canonical values."""
    from brain_alpha_ops.brain_api.canonical import CANONICAL_THRESHOLDS

    thresholds = run_config.ops.thresholds
    results: dict[str, dict[str, Any]] = {}
    deviations: list[str] = []

    for key, canonical in CANONICAL_THRESHOLDS.items():
        try:
            configured = getattr(thresholds, key, None)
        except AttributeError:
            configured = None

        match = configured == canonical
        results[key] = {
            "configured": configured,
            "canonical": canonical,
            "match": match,
            "deviation": (configured - canonical) if configured is not None and not match else 0,
        }
        if not match:
            deviations.append(f"{key}: configured={configured}, canonical={canonical}")

    return {
        "name": "threshold_zero_deviation",
        "passed": len(deviations) == 0,
        "details": results,
        "deviations": deviations,
        "total": len(CANONICAL_THRESHOLDS),
        "matching": sum(1 for r in results.values() if r["match"]),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 2: API Path Alignment
# ═══════════════════════════════════════════════════════════════════════

def _check_api_paths(run_config: Any) -> dict[str, Any]:
    """Verify all configured API paths match BRAIN canonical paths."""
    from brain_alpha_ops.brain_api.canonical import CANONICAL_API_PATHS

    api_config = run_config.ops.official_api
    deviations: list[str] = []
    results: dict[str, dict[str, Any]] = {}

    path_mapping = {
        "authentication": "authentication_path",
        "simulations": "simulations_path",
        "data_sets": "data_sets_path",
        "data_fields": "data_fields_path",
        "operators": "operators_path",
        "user_alphas": "user_alphas_path",
        "user_profile": "user_profile_path",
        "alpha_check": "alpha_check_path_template",
        "alpha_submit": "alpha_submit_path_template",
        "alpha_detail": "alpha_path_template",
        "alpha_correlations": "alpha_correlations_path",
    }

    for canonical_key, config_attr in path_mapping.items():
        canonical_path = CANONICAL_API_PATHS[canonical_key]
        configured = getattr(api_config, config_attr, None)
        match = configured == canonical_path
        results[config_attr] = {
            "configured": configured,
            "canonical": canonical_path,
            "match": match,
        }
        if not match:
            deviations.append(
                f"{config_attr}: configured='{configured}', canonical='{canonical_path}'"
            )

    # Check base_url
    base_match = api_config.base_url == "https://api.worldquantbrain.com"
    results["base_url"] = {
        "configured": api_config.base_url,
        "canonical": "https://api.worldquantbrain.com",
        "match": base_match,
    }
    if not base_match:
        deviations.append(
            f"base_url: configured='{api_config.base_url}', canonical='https://api.worldquantbrain.com'"
        )

    return {
        "name": "api_path_alignment",
        "passed": len(deviations) == 0,
        "details": results,
        "deviations": deviations,
        "total": len(path_mapping) + 1,
        "matching": sum(1 for r in results.values() if r["match"]),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 3: Settings Enum Alignment
# ═══════════════════════════════════════════════════════════════════════

def _check_settings_enums(run_config: Any) -> dict[str, Any]:
    """Verify settings values are within BRAIN allowed enum sets."""
    from brain_alpha_ops.brain_api.canonical import CANONICAL_SETTINGS

    settings = run_config.ops.settings
    results: dict[str, dict[str, Any]] = {}
    deviations: list[str] = []

    # Check settings fields against canonical enums
    setting_checks = [
        ("instrumentType", settings.instrumentType),
        ("region", settings.region),
        ("universe", settings.universe),
        ("neutralization", settings.neutralization),
        ("pasteurization", settings.pasteurization),
        ("unitHandling", settings.unitHandling),
        ("nanHandling", settings.nanHandling),
        ("language", settings.language),
        ("type", settings.type),
    ]

    for field_name, value in setting_checks:
        allowed = CANONICAL_SETTINGS.get(field_name, set())
        if not isinstance(allowed, (set, frozenset)):
            allowed = set()
        match = value in allowed
        results[field_name] = {
            "configured": value,
            "allowed": sorted(allowed),
            "match": match,
        }
        if not match:
            deviations.append(
                f"{field_name}: configured='{value}', allowed={sorted(allowed)}"
            )

    # Check delay separately (integer, not string enum)
    if settings.delay not in CANONICAL_SETTINGS.get("delay", {0, 1}):
        deviations.append(
            f"delay: configured={settings.delay}, allowed=[0, 1]"
        )
        results["delay"] = {
            "configured": settings.delay,
            "allowed": sorted(CANONICAL_SETTINGS.get("delay", {0, 1})),
            "match": False,
        }
    else:
        results["delay"] = {
            "configured": settings.delay,
            "allowed": sorted(CANONICAL_SETTINGS.get("delay", {0, 1})),
            "match": True,
        }

    return {
        "name": "settings_enum_alignment",
        "passed": len(deviations) == 0,
        "details": results,
        "deviations": deviations,
        "total": len(results),
        "matching": sum(1 for r in results.values() if r["match"]),
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 4: Scoring Simulation Zero Deviation
# ═══════════════════════════════════════════════════════════════════════

def _check_scoring_simulation(run_config: Any) -> dict[str, Any]:
    """Verify scoring system produces zero-deviation API output."""
    from brain_alpha_ops.config import BrainSettings
    from brain_alpha_ops.models import Candidate
    from brain_alpha_ops.scoring.official_scoring import OfficialScoringSystem

    # Build a diagnostic probe candidate
    probe = Candidate(
        alpha_id="canonical_compliance_probe",
        expression="rank(ts_delta(close, 20)) + rank(ts_mean(volume / adv20, 20))",
        family="Hybrid",
        hypothesis="Cross-sectional price momentum confirmed by liquidity participation",
        data_fields=["close", "volume", "adv20"],
        operators=["rank", "ts_delta", "ts_mean"],
        dataset_id="fundamental6",
        local_quality={"passed": True, "score": 85},
        official_metrics={
            "pass_fail": "PASS",
            "sharpe": 1.6,
            "fitness": 1.012,
            "turnover": 0.2,
            "returns": 0.08,
            "drawdown": 0.05,
            "correlation": 0.2,
            "prod_correlation": 0.2,
            "weight_concentration": 0.04,
            "sub_universe_sharpe": 1.3,
            "subUniverseSize": 1000,
            "alphaSize": 1000,
            "margin": 5.0,
        },
    )
    probe.official_alpha_id = "canonical_compliance_probe_official"

    scoring_system = OfficialScoringSystem(run_config.ops)
    result = scoring_system.evaluate(probe)

    return {
        "name": "scoring_simulation_zero_deviation",
        "passed": result.api_output_deviation == 0.0,
        "details": {
            "api_status": result.simulated_api_output.get("status"),
            "zero_deviation": result.api_output_deviation == 0.0,
            "deviation_value": result.api_output_deviation,
            "deviation_details": result.deviation_details,
            "total_score": result.total_score,
            "decision_band": result.decision_band,
            "passed_gate": result.passed_gate,
            "config_hash": result.config_hash,
            "threshold_trace": result.threshold_trace,
            "settings_trace": result.settings_trace,
        },
        "deviations": result.deviation_details,
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 5: Field/Operator No Custom Extension
# ═══════════════════════════════════════════════════════════════════════

def _check_no_custom_extension(run_config: Any) -> dict[str, Any]:
    """Verify field/operator definitions are from official BRAIN context only."""
    from brain_alpha_ops.compliance.redline_helpers import (
        _verify_generator_templates_against_official_context,
    )
    from brain_alpha_ops.data.loader import OfficialDataLoader

    data_dir = Path(run_config.ops.storage_dir)
    loader = OfficialDataLoader()
    loader.load_all(data_dir)

    fields = loader.get_fields()
    operators = loader.get_operators()

    field_count = len(fields)
    operator_count = len(operators)

    # Check that all field IDs are non-empty strings
    valid_fields = [
        f for f in fields if isinstance(f.id, str) and f.id.strip()
    ]
    invalid_field_count = field_count - len(valid_fields)

    # Check that all operators have names
    valid_operators = [
        o for o in operators if isinstance(o.name, str) and o.name.strip()
    ]
    invalid_operator_count = operator_count - len(valid_operators)

    deviations = []
    if field_count == 0:
        deviations.append("No official fields loaded — run fetch_official_context.py")
    if operator_count == 0:
        deviations.append("No official operators loaded — run fetch_official_context.py")
    if invalid_field_count:
        deviations.append(f"{invalid_field_count} fields have invalid/missing IDs")
    if invalid_operator_count:
        deviations.append(f"{invalid_operator_count} operators have invalid/missing names")

    template_result = _verify_generator_templates_against_official_context(data_dir)
    if not template_result.get("ok"):
        deviations.append(
            "CandidateGenerator fallback templates reference fields/operators "
            "outside the official context"
        )

    return {
        "name": "no_custom_extension",
        "passed": (
            field_count > 0
            and operator_count > 0
            and invalid_field_count == 0
            and invalid_operator_count == 0
            and bool(template_result.get("ok"))
        ),
        "details": {
            "field_count": field_count,
            "operator_count": operator_count,
            "valid_fields": len(valid_fields),
            "valid_operators": len(valid_operators),
            "invalid_field_count": invalid_field_count,
            "invalid_operator_count": invalid_operator_count,
            "generator_template_check": template_result,
        },
        "deviations": deviations,
    }


# ═══════════════════════════════════════════════════════════════════════
# Check 6: Dataset ID Availability
# ═══════════════════════════════════════════════════════════════════════

def _check_dataset_ids(data_dir: Path) -> dict[str, Any]:
    """Verify all official dataset IDs are available and valid."""
    datasets_path = data_dir / "official_datasets.json"
    deviations = []

    if not datasets_path.exists():
        return {
            "name": "dataset_id_availability",
            "passed": False,
            "details": {"path": str(datasets_path)},
            "deviations": ["official_datasets.json not found"],
            "dataset_ids": [],
        }

    try:
        datasets = json.loads(datasets_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "name": "dataset_id_availability",
            "passed": False,
            "details": {"path": str(datasets_path), "error": str(exc)},
            "deviations": [f"Failed to parse official_datasets.json: {exc}"],
            "dataset_ids": [],
        }

    if not isinstance(datasets, list):
        deviations.append("official_datasets.json is not a list")
        return {
            "name": "dataset_id_availability",
            "passed": False,
            "details": {"path": str(datasets_path)},
            "deviations": deviations,
            "dataset_ids": [],
        }

    ids = [d.get("id", "") for d in datasets if isinstance(d, dict)]
    valid_ids = [i for i in ids if isinstance(i, str) and i.strip()]
    missing_ids = len(ids) - len(valid_ids)
    duplicate_ids = len(valid_ids) - len(set(valid_ids))

    if len(valid_ids) < 10:
        deviations.append(f"Only {len(valid_ids)} valid dataset IDs (expected >= 10)")
    if missing_ids:
        deviations.append(f"{missing_ids} datasets missing valid IDs")
    if duplicate_ids:
        deviations.append(f"{duplicate_ids} duplicate dataset IDs detected")

    context_validation = _context_validation_for_data_dir(data_dir)
    blocking_findings = [
        item
        for item in context_validation.get("findings", [])
        if item.get("severity") == "BLOCKING"
    ]
    for finding in blocking_findings:
        deviations.append(
            f"{finding.get('code', 'official_context')}: "
            f"{finding.get('message', 'official context validation failed')}"
        )

    return {
        "name": "dataset_id_availability",
        "passed": (
            len(valid_ids) >= 10
            and missing_ids == 0
            and duplicate_ids == 0
            and not blocking_findings
        ),
        "details": {
            "total": len(datasets),
            "valid_ids": len(valid_ids),
            "missing_ids": missing_ids,
            "duplicate_ids": duplicate_ids,
            "official_context_blocking_count": len(blocking_findings),
            "official_context_lineage": context_validation.get("lineage", {}),
        },
        "deviations": deviations,
        "dataset_ids": valid_ids,
    }


# ═══════════════════════════════════════════════════════════════════════
# Main Aggregation
# ═══════════════════════════════════════════════════════════════════════

def verify_all(config_path: str | None = None) -> dict[str, Any]:
    """Run all canonical compliance checks and return a unified report."""
    run_config = _load_config(config_path)
    data_dir = Path(run_config.ops.storage_dir)

    checks = [
        _check_thresholds(run_config),
        _check_api_paths(run_config),
        _check_settings_enums(run_config),
        _check_scoring_simulation(run_config),
        _check_no_custom_extension(run_config),
        _check_dataset_ids(data_dir),
    ]

    all_passed = all(check["passed"] for check in checks)
    total_deviations = sum(len(check.get("deviations", [])) for check in checks)

    return {
        "ok": all_passed,
        "schema_version": "canonical_compliance_verification.v1",
        "total_checks": len(checks),
        "passed_checks": sum(1 for check in checks if check["passed"]),
        "failed_checks": sum(1 for check in checks if not check["passed"]),
        "total_deviations": total_deviations,
        "results": checks,
        "all_deviations": [
            {"check": check["name"], "deviation": deviation}
            for check in checks
            for deviation in check.get("deviations", [])
        ],
    }


def _format_report(report: dict[str, Any]) -> str:
    """Format the verification report as human-readable text."""
    lines = [
        "=" * 72,
        "  BRAIN Canonical Compliance Verification Report",
        "=" * 72,
        f"  Schema Version : {report['schema_version']}",
        f"  Overall        : {'PASS' if report['ok'] else 'FAIL'}",
        f"  Checks Passed  : {report['passed_checks']}/{report['total_checks']}",
        f"  Total Devs     : {report['total_deviations']}",
        "",
    ]

    for check in report["results"]:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"  [{status}] {check['name']}")
        for deviation in check.get("deviations", []):
            lines.append(f"        → {deviation}")
        details = check.get("details", {})
        if details:
            key_lines = []
            for key, value in details.items():
                if not isinstance(value, dict) and not isinstance(value, list):
                    key_lines.append(f"        {key}: {value}")
            if key_lines and len(key_lines) <= 6:
                lines.extend(key_lines)
        lines.append("")

    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BRAIN canonical compliance verification",
    )
    parser.add_argument("--config", help="Path to run_config.json")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any deviation")
    args = parser.parse_args()

    try:
        report = verify_all(args.config)
    except Exception as exc:
        error_report = {
            "ok": False,
            "schema_version": "canonical_compliance_verification.v1",
            "error": str(exc),
            "message": "Verification failed with an unexpected error. "
                        "Ensure the project is installed and config/run_config.json is valid.",
        }
        if args.json:
            print(json.dumps(error_report, ensure_ascii=False, indent=2))
        else:
            print(f"ERROR: Verification failed — {exc}")
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_format_report(report))

    if args.strict and not report["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

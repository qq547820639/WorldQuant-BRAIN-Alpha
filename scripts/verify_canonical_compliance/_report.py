"""Aggregation, reporting, and CLI for canonical compliance verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ._checks import (
    _check_api_paths,
    _check_settings_enums,
    _check_thresholds,
)
from ._checks_more import (
    _check_dataset_ids,
    _check_no_custom_extension,
    _check_scoring_simulation,
)
from ._config import _load_config

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

"""Check that the production diagnosis report matches current code facts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_REPORT = ROOT / "docs" / "ALPHA_PRODUCTION_DIAGNOSIS_20260522.md"
REQUIRED_DIMENSIONS = [
    "Functional closure",
    "Technical compliance",
    "Parameter accuracy",
    "Data lineage",
    "Experience",
    "Scoring",
]
REQUIRED_UPGRADE_AREAS = [
    "Architecture",
    "Data efficiency",
    "LLM prompting",
    "Backtest execution",
    "Errors and logs",
]


def check_diagnostic_report(
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    report_path: str | Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    from brain_alpha_ops.production_diagnostics import build_diagnostic_snapshot

    path = Path(report_path)
    findings: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
        findings.append(_finding("missing_report", str(path), "diagnostic report file does not exist"))
    except OSError as exc:
        text = ""
        findings.append(_finding("read_error", str(path), str(exc)))

    snapshot = build_diagnostic_snapshot(config_path)
    _expect(text, "# Alpha Production Diagnosis and Gap Matrix", "header", findings)
    _expect(text, "## Gap Matrix", "gap_matrix_section", findings)
    _expect(text, "## Current Execution Checklist", "execution_checklist_section", findings)
    _expect(text, "QuantGPT-Aligned Upgrade Plan", "quantgpt_section", findings)

    redline = snapshot["redline"]
    context = snapshot["official_context"]
    scoring = snapshot["scoring_probe"]
    refresh = snapshot.get("official_refresh", {})
    validation = snapshot.get("official_context_validation", {})
    history = snapshot.get("history_replay", {})
    parameter_audit = snapshot.get("parameter_audit", {})
    _expect(
        text,
        f"Red lines: {redline['overall']} ({redline['passed']}/{redline['total_checks']} passed",
        "redline_counts",
        findings,
    )
    _expect(
        text,
        f"Official context: fields={context['fields']}, operators={context['operators']}, datasets={context['datasets']}",
        "official_context_counts",
        findings,
    )
    _expect(
        text,
        f"Parameter audit: hash={str(parameter_audit.get('config_hash', ''))[:12]}",
        "parameter_audit_hash",
        findings,
    )
    _expect(text, f"Official refresh: status={refresh.get('status')}", "official_refresh_status", findings)
    _expect(
        text,
        (
            f"Context validation: blocking_ok={validation.get('blocking_ok')}, "
            f"p1_findings={validation.get('p1_count')}, "
            f"dataset_field_count_sum={(validation.get('lineage') or {}).get('dataset_field_count_sum', 0)}"
        ),
        "official_context_validation",
        findings,
    )
    _expect(
        text,
        f"Scoring probe: status={scoring['api_status']}, zero_deviation={scoring['zero_deviation']}, score={scoring['total_score']}",
        "scoring_probe",
        findings,
    )
    _expect(text, f"History replay: capability={history.get('capability')}", "history_replay_status", findings)

    for dimension in REQUIRED_DIMENSIONS:
        _expect(text, f"| {dimension} |", f"gap_dimension:{dimension}", findings)
    for area in REQUIRED_UPGRADE_AREAS:
        _expect(text, f"**{next(item['priority'] for item in snapshot['upgrade_plan'] if item['area'] == area)} {area}**", f"upgrade_area:{area}", findings)
    for item in snapshot.get("priority_items") or []:
        _expect(text, f"**{item['priority']} {item['area']}**", f"priority_item:{item['area']}", findings)

    return {
        "ok": not findings,
        "schema_version": "diagnostic_report_check.v1",
        "report": str(path),
        "config": str(config_path),
        "snapshot_ok": bool(snapshot.get("ok")),
        "findings": findings,
    }


def _expect(text: str, needle: str, code: str, findings: list[dict[str, str]]) -> None:
    if needle not in text:
        findings.append(_finding(code, needle, "expected current diagnostic fact not found in report"))


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check production diagnosis report consistency.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Markdown report path.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_diagnostic_report(config_path=args.config, report_path=args.report)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        if result["ok"]:
            print(f"diagnostic report check passed: {result['report']}")
        else:
            print(f"diagnostic report check failed: {result['report']}")
            for finding in result["findings"]:
                print(f"[{finding['code']}] {finding['message']}: {finding['expected']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

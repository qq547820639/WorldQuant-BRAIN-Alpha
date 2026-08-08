from __future__ import annotations

"""Validate the rendered Alpha Production Diagnosis report.

A fresh diagnostic snapshot is rebuilt from the run config and the rendered
``docs/ALPHA_PRODUCTION_DIAGNOSIS_20260620.md`` report is checked against it.
The current check focuses on the official-context counts line, which is the
most drift-prone summary of the diagnostic snapshot.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brain_alpha_ops.production_diagnostics import build_diagnostic_snapshot, render_one_page_markdown  # noqa: E402

SCHEMA_VERSION = "diagnostic_report_check.v1"
DEFAULT_REPORT = ROOT / "docs" / "ALPHA_PRODUCTION_DIAGNOSIS_20260620.md"

_CONTEXT_RE = re.compile(
    r"Official context:\s*fields=(\d+),\s*operators=(\d+),\s*datasets=(\d+)"
)


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def check_diagnostic_report(*, config_path: str | Path, report_path: str | Path) -> dict[str, object]:
    report = Path(report_path)
    findings: list[dict[str, str]] = []

    snapshot = build_diagnostic_snapshot(config_path)
    fresh_context = snapshot.get("official_context") or {}

    try:
        text = report.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "report": str(report),
            "findings": [_finding("missing_report", str(report), "diagnostic report does not exist")],
        }

    match = _CONTEXT_RE.search(text)
    if not match:
        findings.append(
            _finding(
                "missing_official_context_line",
                "Official context: fields=.., operators=.., datasets=..",
                "report is missing the official context counts line",
            )
        )
    else:
        report_counts = {
            "fields": int(match.group(1)),
            "operators": int(match.group(2)),
            "datasets": int(match.group(3)),
        }
        for key in ("fields", "operators", "datasets"):
            fresh = int(fresh_context.get(key, 0))
            if report_counts[key] != fresh:
                findings.append(
                    _finding(
                        "official_context_counts",
                        f"{key}={fresh}",
                        f"official context {key} count is stale ({report_counts[key]} != {fresh})",
                    )
                )

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "report": str(report),
        "official_context": fresh_context,
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the rendered diagnostic report against a fresh snapshot.")
    parser.add_argument("--config", required=True, help="Path to the run config.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to the rendered diagnostic report.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_diagnostic_report(config_path=args.config, report_path=args.report)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "ok" if result["ok"] else "failed"
        print(f"diagnostic report {status}: {result['report']}")
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['expected']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
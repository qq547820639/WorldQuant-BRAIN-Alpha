"""Validate the 2026-06-01 defect analysis tracking contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "DEFECT_ANALYSIS_REPORT_20260601.md"
SCHEMA_VERSION = "defect_analysis_report_check.v1"
VALID_STATUSES = {"CLOSED_CURRENT", "TRACKED_OPEN", "TRACKED_DEFERRED", "TRACKED_ENVIRONMENT"}
STALE_SNIPPETS = (
    "PARTIAL_CLOSED_CURRENT",
    "Remaining scan candidates",
)
DEFECT_HEADING_RE = re.compile(r"^### (DEFECT-\d{3}):\s*(.+)$", re.MULTILINE)
STATUS_ROW_RE = re.compile(r"^(DEFECT-\d{3}):\s*(.+)$")


def check_defect_analysis_report(report_path: str | Path = DEFAULT_REPORT) -> dict[str, Any]:
    path = Path(report_path)
    findings: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "report": str(path),
            "findings": [_finding("missing_report", str(path), "defect analysis report does not exist")],
        }

    detail_rows = _detail_rows(text)
    status_rows = _status_rows(text, findings)
    _check_duplicates(detail_rows, "detail", findings)
    _check_duplicates(status_rows, "status", findings)

    detail_ids = {row["id"] for row in detail_rows}
    status_ids = {row["id"] for row in status_rows}
    for defect_id in sorted(detail_ids - status_ids):
        findings.append(
            _finding("missing_status_row", defect_id, "detailed defect is missing from current status table")
        )
    for defect_id in sorted(status_ids - detail_ids):
        findings.append(
            _finding("missing_detail_section", defect_id, "status table references a defect without a detail section")
        )

    total = _overview_total(text)
    if total is not None and total != len(detail_ids):
        findings.append(
            _finding(
                "overview_total_mismatch",
                str(total),
                f"overview total does not match {len(detail_ids)} detailed defect sections",
            )
        )

    for row in status_rows:
        status = row["status"]
        if status not in VALID_STATUSES:
            findings.append(_finding("invalid_status", f"{row['id']}:{status}", "unknown defect status"))
        if status != "CLOSED_CURRENT" and not row["next_action"]:
            findings.append(
                _finding("missing_next_action", row["id"], "open or deferred defects need an explicit next action")
            )
        if row["id"] == "DEFECT-016" and status == "CLOSED_CURRENT" and sys.version_info < (3, 10):
            findings.append(
                _finding(
                    "python_runtime_too_old",
                    ".".join(str(part) for part in sys.version_info[:3]),
                    "DEFECT-016 is closed but current Python runtime is below the project requirement",
                )
            )

    for stale in STALE_SNIPPETS:
        if stale in text:
            findings.append(_finding("stale_report_fact", stale, "stale defect tracking fact is still present"))

    open_items = [row for row in status_rows if row["status"] != "CLOSED_CURRENT"]
    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "report": str(path),
        "detailed_count": len(detail_ids),
        "status_count": len(status_ids),
        "closed_count": sum(1 for row in status_rows if row["status"] == "CLOSED_CURRENT"),
        "open_count": len(open_items),
        "open_items": [{"id": row["id"], "status": row["status"], "title": row["title"]} for row in open_items],
        "python_runtime": ".".join(str(part) for part in sys.version_info[:3]),
        "python_runtime_ok": sys.version_info >= (3, 10),
        "findings": findings,
    }


def _detail_rows(text: str) -> list[dict[str, str]]:
    return [
        {"id": match.group(1), "title": match.group(2).strip()}
        for match in DEFECT_HEADING_RE.finditer(text)
    ]


def _status_rows(text: str, findings: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not line.startswith("| DEFECT-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            findings.append(_finding("malformed_status_row", line, "status table row has too few cells"))
            continue
        match = STATUS_ROW_RE.match(cells[0])
        if match is None:
            findings.append(_finding("malformed_status_id", cells[0], "status table first cell is not a defect id"))
            continue
        rows.append(
            {
                "id": match.group(1),
                "title": match.group(2).strip(),
                "status": cells[1],
                "evidence": cells[2],
                "next_action": "|".join(cells[3:]).strip(),
            }
        )
    return rows


def _check_duplicates(rows: list[dict[str, str]], section: str, findings: list[dict[str, str]]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        defect_id = row["id"]
        if defect_id in seen:
            duplicates.add(defect_id)
        seen.add(defect_id)
    for defect_id in sorted(duplicates):
        findings.append(_finding(f"duplicate_{section}_defect", defect_id, "defect id appears more than once"))


def _overview_total(text: str) -> int | None:
    match = re.search(r"\|\s*\*\*合计\*\*\s*\|\s*\*\*(\d+)\*\*", text)
    return int(match.group(1)) if match else None


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check defect analysis report consistency.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to DEFECT_ANALYSIS_REPORT_20260601.md")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    args = parser.parse_args()

    result = check_defect_analysis_report(args.report)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        state = "PASS" if result["ok"] else "FAIL"
        print(f"defect analysis report check {state}: {result['report']}")
        for finding in result["findings"]:
            print(f"- {finding['code']}: {finding['expected']} ({finding['message']})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

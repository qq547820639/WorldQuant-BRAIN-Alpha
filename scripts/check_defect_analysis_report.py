"""Validate the 2026-06-01 defect analysis tracking contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts._defect_analysis_helpers import (  # noqa: E402
    RESOLVED_STATUSES,
    SCHEMA_VERSION,
    STALE_SNIPPETS,
    VALID_STATUSES,
    _check_duplicates,
    _check_priority_counts,
    _check_required_open_items,
    _check_required_report_boundaries,
    _detail_rows,
    _finding,
    _overview_priority_counts,
    _overview_total,
    _priority_counts,
    _status_rows,
)

DEFAULT_REPORT = ROOT / "docs" / "DEFECT_ANALYSIS_REPORT_20260601.md"


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
    overview_priority_counts = _overview_priority_counts(text)
    detail_priority_counts = _priority_counts(detail_rows)
    status_priority_counts = _priority_counts(status_rows)
    if overview_priority_counts:
        _check_priority_counts("detail", overview_priority_counts, detail_priority_counts, findings)
        _check_priority_counts("status", overview_priority_counts, status_priority_counts, findings)

    detail_titles = {row["id"]: row["title"] for row in detail_rows}
    for row in status_rows:
        status = row["status"]
        if status not in VALID_STATUSES:
            findings.append(_finding("invalid_status", f"{row['id']}:{status}", "unknown defect status"))
        if status not in RESOLVED_STATUSES and not row["next_action"]:
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

    _check_required_report_boundaries(path, text, status_rows, findings)

    open_items = [row for row in status_rows if row["status"] not in RESOLVED_STATUSES]
    _check_required_open_items(path, open_items, findings)
    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "report": str(path),
        "detailed_count": len(detail_ids),
        "status_count": len(status_ids),
        "closed_count": sum(1 for row in status_rows if row["status"] in RESOLVED_STATUSES),
        "open_count": len(open_items),
        "priority_counts": {
            "overview": overview_priority_counts,
            "detail": detail_priority_counts,
            "status": status_priority_counts,
        },
        "open_items": [
            {
                "id": row["id"],
                "status": row["status"],
                "title": row["title"] or detail_titles.get(row["id"], ""),
            }
            for row in open_items
        ],
        "python_runtime": ".".join(str(part) for part in sys.version_info[:3]),
        "python_runtime_ok": sys.version_info >= (3, 10),
        "findings": findings,
    }


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

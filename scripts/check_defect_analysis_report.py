from __future__ import annotations

"""Validate the BRAIN Alpha Ops defect analysis reports.

Two report documents are supported:

* ``docs/DEFECT_ANALYSIS_REPORT_20260601.md`` — the default report with 16
  detailed defect sections and a 16-row current-status table.
* ``docs/STATIC_ANALYSIS_DEFECT_REPORT_20260603.md`` — the static-analysis
  report with 22 detailed defect sections, a 22-row status table, priority
  distribution, and tracked boundary evidence (P0-3 pagination, P2-6 bind
  smoke).

The check is intentionally strict: it locks the status-table row set, the
closed/open split, the priority distribution, the open items, and the
tracked boundary evidence so that tracking drift is caught in CI.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_REPORT = ROOT / "docs" / "DEFECT_ANALYSIS_REPORT_20260601.md"
SCHEMA_VERSION = "defect_analysis_report_check.v1"

# Statuses that count as an open / tracked-deferred item.
OPEN_STATUSES = frozenset({"TRACKED_DEFERRED", "TRACKED_OPEN", "OPEN"})

# Resolved statuses that are treated as closed for the current code line.
CLOSED_STATUSES = frozenset({"FIXED", "CLOSED_CURRENT", "TRACKED_LEGACY_COMPAT"})

# Expected open items for the static 20260603 report: (id, status).
STATIC_EXPECTED_OPEN_ITEMS = (("P0-3", "TRACKED_DEFERRED"),)

# Boundary status/evidence locked in the status table rows for the static
# 20260603 report. Each entry: (row_id, expected_status_or_snippet, code).
# Checks run against the status-table row only.
STATIC_ROW_BOUNDARY_CHECKS = (
    ("P0-3", "TRACKED_DEFERRED", "boundary_status_mismatch"),
    ("P2-6", "FIXED", "boundary_status_mismatch"),
    ('P2-6', '{"ok": true, "status": "web ready"', "boundary_evidence_mismatch"),
)

# Boundary evidence locked anywhere in the static report text (typically in the
# detailed section). Each entry: (row_id, expected_snippet). Code is always
# ``boundary_report_text_mismatch``.
STATIC_TEXT_BOUNDARY_CHECKS = (
    ("P0-3", "stalled_unique_pages"),
    (
        "P0-3",
        "tests/test_web_sync_job.py::test_run_sync_job_service_returns_false_to_cancel_alpha_scan",
    ),
    ("P2-6", "python -m brain_alpha_ops.web --smoke-test --port 0"),
    ("P2-6", "PermissionError: [Errno 1] Operation not permitted"),
    ('P2-6', '{"ok": true, "status": "web ready"'),
)

_DETAIL_RE = re.compile(r"^###\s+(DEFECT-\d+|P\d+-\d+)\b")
_PRIORITY_RE = re.compile(r"^P(\d+)-")
_OVERVIEW_PRIORITY_RE = re.compile(r"P(\d+)[×x](\d+)")


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(set(cell) <= {"-", ":"} for cell in cells)


def _tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = text.splitlines()
    tables: list[tuple[list[str], list[list[str]]]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|") and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            header = _cells(lines[i])
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            tables.append((header, rows))
            continue
        i += 1
    return tables


def _status_rows(text: str) -> list[dict[str, str]]:
    for header, rows in _tables(text):
        if "当前状态" not in header:
            continue
        if not any(cell in header for cell in ("ID", "缺陷")):
            continue
        status_col = header.index("当前状态")
        evidence_col = header.index("当前证据") if "当前证据" in header else None
        parsed = []
        for cells in rows:
            if len(cells) <= status_col:
                continue
            match = re.match(r"^(DEFECT-\d+|P\d+-\d+)\b", cells[0])
            if not match:
                continue
            row: dict[str, str] = {"id": match.group(1), "status": cells[status_col]}
            if evidence_col is not None and evidence_col < len(cells):
                row["evidence"] = cells[evidence_col]
            parsed.append(row)
        return parsed
    return []


def _detailed_sections(text: str) -> list[str]:
    ids: list[str] = []
    for line in text.splitlines():
        match = _DETAIL_RE.match(line)
        if match:
            ids.append(match.group(1))
    return ids


def _overview_priority_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        matches = list(_OVERVIEW_PRIORITY_RE.finditer(line))
        if matches:
            for match in matches:
                counts[f"P{match.group(1)}"] = int(match.group(2))
    return counts


def _priority_counts_by_id(ids: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for defect_id in ids:
        match = _PRIORITY_RE.match(defect_id)
        if match:
            counts[f"P{match.group(1)}"] = counts.get(f"P{match.group(1)}", 0) + 1
    return counts


def check_defect_analysis_report(report_path: str | Path = DEFAULT_REPORT) -> dict[str, object]:
    report = Path(report_path)
    findings: list[dict[str, str]] = []
    try:
        text = report.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "report": str(report),
            "findings": [_finding("missing_report", str(report), "defect analysis report does not exist")],
        }

    detailed_ids = _detailed_sections(text)
    status_rows = _status_rows(text)
    rows_by_id = {row["id"]: row for row in status_rows}
    expected_status_ids = set(detailed_ids)

    for defect_id in expected_status_ids:
        if defect_id not in rows_by_id:
            findings.append(_finding("missing_status_row", defect_id, "status table row is missing"))

    open_items = [row for row in status_rows if row["status"] in OPEN_STATUSES]
    open_count = len(open_items)
    status_count = len(status_rows)
    closed_count = status_count - open_count

    overview = _overview_priority_counts(text)
    detail_counts = _priority_counts_by_id(detailed_ids)
    status_counts = _priority_counts_by_id([row["id"] for row in status_rows])
    priority_counts = {"overview": overview, "detail": detail_counts, "status": status_counts}

    if overview:
        for scope, counts in (("detail", detail_counts), ("status", status_counts)):
            for priority in ("P0", "P1", "P2", "P3"):
                expected = overview.get(priority, 0)
                actual = counts.get(priority, 0)
                if actual != expected:
                    findings.append(
                        _finding("priority_count_mismatch", f"{scope}:{priority}={expected}", "priority distribution drifted")
                    )

    is_static = "STATIC_ANALYSIS_DEFECT_REPORT" in report.name
    if is_static:
        _check_static_boundaries(rows_by_id, text, findings)
        actual_open_ids = {item["id"] for item in open_items}
        expected_open_ids = {item[0] for item in STATIC_EXPECTED_OPEN_ITEMS}
        if actual_open_ids != expected_open_ids:
            findings.append(
                _finding(
                    "open_items_mismatch",
                    f"{report.name}:" + ",".join(sorted(expected_open_ids)),
                    "open item set drifted",
                )
            )

    runtime = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    runtime_ok = (sys.version_info.major, sys.version_info.minor) >= (3, 10)

    if "PARTIAL_CLOSED_CURRENT" in text:
        findings.append(_finding("stale_report_fact", "PARTIAL_CLOSED_CURRENT", "stale tracking fact present"))

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "report": str(report),
        "detailed_count": len(detailed_ids),
        "status_count": status_count,
        "closed_count": closed_count,
        "open_count": open_count,
        "priority_counts": priority_counts,
        "python_runtime": runtime,
        "python_runtime_ok": runtime_ok,
        "open_items": open_items,
        "findings": findings,
    }


def _check_static_boundaries(
    rows_by_id: dict[str, dict[str, str]],
    text: str,
    findings: list[dict[str, str]],
) -> None:
    for defect_id, expected, code in STATIC_ROW_BOUNDARY_CHECKS:
        row = rows_by_id.get(defect_id)
        if row is None:
            findings.append(_finding(code, f"{defect_id}:{expected}", "boundary row is missing"))
            continue
        if code == "boundary_status_mismatch":
            if row.get("status") != expected:
                findings.append(_finding(code, f"{defect_id}:{expected}", "boundary status changed"))
            continue
        row_text = " | ".join(row.values())
        if expected not in row_text:
            findings.append(_finding(code, f"{defect_id}:{expected}", "boundary success evidence changed"))
    for defect_id, expected in STATIC_TEXT_BOUNDARY_CHECKS:
        if expected not in text:
            findings.append(
                _finding("boundary_report_text_mismatch", f"{defect_id}:{expected}", "boundary report text changed")
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check defect analysis report consistency.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to the defect analysis report.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_defect_analysis_report(args.report)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "ok" if result["ok"] else "failed"
        print(f"defect analysis report {status}: {result['report']}")
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['expected']}: {finding['message']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
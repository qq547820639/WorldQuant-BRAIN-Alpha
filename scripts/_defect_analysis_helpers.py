"""Helpers for the defect analysis report validation contract.

Split from ``scripts/check_defect_analysis_report.py`` so the CLI entry
point stays within the project's 350-line module limit. Logger names are
not used here; the parent module retains its original identity.
"""

from __future__ import annotations

import re
from pathlib import Path


SCHEMA_VERSION = "defect_analysis_report_check.v1"
STATUS_VALUES = (
    "FIXED_LOCAL_VERIFIED",
    "TRACKED_LEGACY_COMPAT",
    "TRACKED_ENVIRONMENT",
    "TRACKED_DEFERRED",
    "TRACKED_OPEN",
    "CLOSED_CURRENT",
    "FIXED",
)
VALID_STATUSES = set(STATUS_VALUES)
RESOLVED_STATUSES = {"CLOSED_CURRENT", "FIXED", "TRACKED_LEGACY_COMPAT"}
STALE_SNIPPETS = (
    "PARTIAL_CLOSED_CURRENT",
    "Remaining scan candidates",
)
DEFECT_ID_PATTERN = r"(?:DEFECT-(?:\d{3}|A\d+[a-z]?(?:-[a-z])?)|P[0-3]-\d+)"
DEFECT_HEADING_RE = re.compile(rf"^### ({DEFECT_ID_PATTERN}):\s*(.+)$", re.MULTILINE)
STATUS_ROW_RE = re.compile(rf"({DEFECT_ID_PATTERN})(?::\s*(.+))?")
REQUIRED_REPORT_BOUNDARIES = {
    "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md": {
        "P0-3": {
            "status": "TRACKED_DEFERRED",
            "evidence": "no_new_unique_items",
            "next_action": "不添加固定分页截断",
            "report_text": (
                "stalled_unique_pages",
                "duplicate_unique_items",
                "tests/test_official_adapter.py::test_list_user_alphas_can_be_cancelled_by_progress_callback_without_page_cap",
                "tests/test_web_sync_job.py::test_run_sync_job_service_returns_false_to_cancel_alpha_scan",
                "tests/test_web_sync_job.py::test_run_sync_job_service_ignores_elapsed_limit_and_scans_all_pages",
                "tests/test_pipeline.py::test_pipeline_cloud_sync_cancel_does_not_merge_partial_rows",
                "tests/test_pipeline.py::test_pipeline_cloud_sync_ignores_elapsed_limit_and_merges_all_rows",
            ),
        },
        "P2-6": {
            "status": "FIXED",
            "evidence": '{"ok": true, "status": "web ready"',
            "report_text": (
                "python -m brain_alpha_ops.web --smoke-test --port 0",
                "PermissionError: [Errno 1] Operation not permitted",
                '{"ok": true, "status": "web ready"',
            ),
        },
    }
}
REQUIRED_REPORT_OPEN_ITEMS = {
    "STATIC_ANALYSIS_DEFECT_REPORT_20260603.md": {"P0-3"},
}


def _detail_rows(text: str) -> list[dict[str, str]]:
    return [
        {"id": match.group(1), "title": match.group(2).strip()}
        for match in DEFECT_HEADING_RE.finditer(text)
    ]


def _status_rows(text: str, findings: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_status_table = False
    for line in text.splitlines():
        if not line.startswith("|"):
            in_status_table = False
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if _is_status_header(cells):
            in_status_table = True
            continue
        if in_status_table and cells and set(cells[0]) <= {"-", ":"}:
            continue
        if not in_status_table:
            continue
        if len(cells) < 4:
            findings.append(_finding("malformed_status_row", line, "status table row has too few cells"))
            continue
        match = STATUS_ROW_RE.search(cells[0])
        if match is None:
            continue
        status = _normalize_status(cells[1])
        rows.append(
            {
                "id": match.group(1),
                "title": (match.group(2) or "").strip(),
                "status": status,
                "evidence": cells[2],
                "next_action": "|".join(cells[3:]).strip(),
            }
        )
    return rows


def _is_status_header(cells: list[str]) -> bool:
    if len(cells) < 4:
        return False
    return cells[0] in {"缺陷", "编号", "ID"} and cells[1] in {"当前状态", "状态"}


def _normalize_status(value: str) -> str:
    for status in STATUS_VALUES:
        if status in value:
            return status
    return value.strip()


def _check_required_report_boundaries(
    path: Path,
    text: str,
    status_rows: list[dict[str, str]],
    findings: list[dict[str, str]],
) -> None:
    requirements = REQUIRED_REPORT_BOUNDARIES.get(path.name)
    if not requirements:
        return
    rows_by_id = {row["id"]: row for row in status_rows}
    for defect_id, expected in requirements.items():
        row = rows_by_id.get(defect_id)
        if row is None:
            findings.append(_finding("missing_required_boundary", defect_id, "required tracked boundary is missing"))
            continue
        expected_status = expected.get("status")
        if expected_status and row["status"] != expected_status:
            findings.append(
                _finding(
                    "boundary_status_mismatch",
                    f"{defect_id}:{expected_status}",
                    "required tracked boundary has stale status",
                )
            )
        expected_evidence = expected.get("evidence")
        if expected_evidence and expected_evidence not in row["evidence"]:
            findings.append(
                _finding(
                    "boundary_evidence_mismatch",
                    f"{defect_id}:{expected_evidence}",
                    "required tracked boundary is missing current evidence",
                )
            )
        expected_next_action = expected.get("next_action")
        if expected_next_action and expected_next_action not in row["next_action"]:
            findings.append(
                _finding(
                    "boundary_next_action_mismatch",
                    f"{defect_id}:{expected_next_action}",
                    "required tracked boundary is missing current next action",
                )
            )
        expected_report_text = expected.get("report_text")
        if isinstance(expected_report_text, str):
            expected_report_snippets = (expected_report_text,)
        else:
            expected_report_snippets = tuple(expected_report_text or ())
        for snippet in expected_report_snippets:
            if snippet not in text:
                findings.append(
                    _finding(
                        "boundary_report_text_mismatch",
                        f"{defect_id}:{snippet}",
                        "required tracked boundary is missing report evidence text",
                    )
                )


def _check_required_open_items(
    path: Path,
    open_items: list[dict[str, str]],
    findings: list[dict[str, str]],
) -> None:
    expected_open_items = REQUIRED_REPORT_OPEN_ITEMS.get(path.name)
    if expected_open_items is None:
        return
    actual_open_items = {row["id"] for row in open_items}
    if actual_open_items != expected_open_items:
        expected = ",".join(sorted(expected_open_items))
        actual = ",".join(sorted(actual_open_items)) or "<none>"
        findings.append(
            _finding(
                "open_items_mismatch",
                f"{path.name}:{expected}",
                f"open items are {actual}",
            )
        )


def _priority_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        match = re.match(r"(P[0-3])-", row["id"])
        if not match:
            continue
        priority = match.group(1)
        counts[priority] = counts.get(priority, 0) + 1
    return counts


def _overview_priority_counts(text: str) -> dict[str, int]:
    match = re.search(r"发现缺陷总数\*\*:\s*\d+\s*项（(.+?)）", text)
    if not match:
        return {}
    counts: dict[str, int] = {}
    for priority, count in re.findall(r"(P[0-3])×(\d+)", match.group(1)):
        counts[priority] = int(count)
    return counts


def _check_priority_counts(
    section: str,
    expected_counts: dict[str, int],
    actual_counts: dict[str, int],
    findings: list[dict[str, str]],
) -> None:
    for priority, expected in sorted(expected_counts.items()):
        actual = actual_counts.get(priority, 0)
        if actual != expected:
            findings.append(
                _finding(
                    "priority_count_mismatch",
                    f"{section}:{priority}={expected}",
                    f"overview priority count does not match {actual} {section} rows",
                )
            )


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
    if match:
        return int(match.group(1))
    match = re.search(r"发现缺陷总数\*\*:\s*(\d+)\s*项", text)
    return int(match.group(1)) if match else None


def _finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}

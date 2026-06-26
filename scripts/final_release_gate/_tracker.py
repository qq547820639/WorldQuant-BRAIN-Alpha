"""Implementation-tracker (AF-006..AF-025) redline checks.

Split from the former ``scripts/final_release_gate.py`` monolith
(deep-optimization-phase12, Task A4). Parses the implementation tracker
markdown, validates AF-006 through AF-025 coverage, and builds the tracker
payload, readiness summary, gate matrix, and AF-006 non-submit verification
submatrix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.af006_quality_submatrix import (
    EXPECTED_AF_COMPLETION_IDS,
    build_final_release_af006_submatrix,
    tracker_non_done_statuses,
    tracker_readiness_summary,
)

from ._models import Finding, _add_finding


def _check_implementation_tracker_redline(tracker_path: Path, findings: list[Finding]) -> dict[str, Any]:
    expected_ids = list(EXPECTED_AF_COMPLETION_IDS)
    status_by_id: dict[str, str] = {}
    row_by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: list[str] = []
    parse_errors: list[str] = []
    try:
        lines = tracker_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        _add_finding(
            findings,
            "P0",
            "IMPLEMENTATION_TRACKER_MISSING",
            "Final release requires an implementation tracker covering AF-006 through AF-025.",
            str(tracker_path),
            expected=expected_ids,
        )
        return _tracker_payload(tracker_path, expected_ids, {}, {}, expected_ids, {}, [], [])

    in_tracked_items = False
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped == "tracked_items:":
            in_tracked_items = True
            continue
        if not in_tracked_items:
            continue
        if not stripped:
            break
        if not stripped.startswith("- AF-"):
            continue
        columns = [column.strip() for column in stripped[2:].split("|")]
        if len(columns) < 5 or any(not column for column in columns[:5]):
            parse_errors.append(f"line {line_number}: {stripped[:120]}")
            continue
        af_id = columns[0].strip()
        status = columns[3].strip().lower()
        if af_id in status_by_id:
            duplicate_ids.append(af_id)
        status_by_id[af_id] = status
        row_by_id[af_id] = {
            "id": af_id,
            "line": line_number,
            "module": columns[1],
            "title": columns[2],
            "status": status,
            "details": columns[4],
            "done": status == "done",
        }

    missing_ids = [af_id for af_id in expected_ids if af_id not in status_by_id]
    non_done_statuses = tracker_non_done_statuses(expected_ids, status_by_id)
    for condition, code, message, current, expected in (
        (
            parse_errors,
            "IMPLEMENTATION_TRACKER_PARSE_ERROR",
            "Implementation tracker AF rows must have pipe-delimited id/module/title/status/details columns.",
            parse_errors[:20],
            "rows like '- AF-006 | Module 6 | ... | done | ...'",
        ),
        (
            duplicate_ids,
            "IMPLEMENTATION_TRACKER_AF_DUPLICATE",
            "Final release requires exactly one tracker row for each AF module.",
            sorted(set(duplicate_ids)),
            expected_ids,
        ),
        (
            missing_ids,
            "IMPLEMENTATION_TRACKER_AF_MISSING",
            "Final release requires tracker rows for every AF-006 through AF-025 module.",
            missing_ids,
            expected_ids,
        ),
        (
            non_done_statuses,
            "IMPLEMENTATION_TRACKER_AF_NOT_DONE",
            "Final release requires every AF-006 through AF-025 module to be marked done.",
            non_done_statuses,
            "done",
        ),
    ):
        if condition:
            findings.append(Finding("P0", code, message, str(tracker_path), current=current, expected=expected))
    return _tracker_payload(
        tracker_path,
        expected_ids,
        status_by_id,
        row_by_id,
        missing_ids,
        non_done_statuses,
        duplicate_ids,
        parse_errors,
    )


def _tracker_payload(
    tracker_path: Path,
    expected_ids: list[str],
    status_by_id: dict[str, str],
    row_by_id: dict[str, dict[str, Any]],
    missing_ids: list[str],
    non_done_statuses: dict[str, str],
    duplicate_ids: list[str],
    parse_errors: list[str],
) -> dict[str, Any]:
    duplicate_ids = sorted(set(duplicate_ids))
    return {
        "path": str(tracker_path),
        "expected_ids": expected_ids,
        "status_by_id": {af_id: status_by_id[af_id] for af_id in expected_ids if af_id in status_by_id},
        "missing_ids": missing_ids,
        "non_done_statuses": non_done_statuses,
        "duplicate_ids": duplicate_ids,
        "parse_errors": parse_errors,
        "done_count": sum(1 for af_id in expected_ids if status_by_id.get(af_id) == "done"),
        "total_expected": len(expected_ids),
        "readiness_summary": tracker_readiness_summary(expected_ids, status_by_id),
        "gate_matrix": _tracker_gate_matrix(expected_ids, row_by_id, duplicate_ids=duplicate_ids),
        "af006_non_submit_verification_submatrix": build_final_release_af006_submatrix(
            status_by_id.get("AF-006")
        ),
        "completion_claimable": not (parse_errors or duplicate_ids or missing_ids or non_done_statuses),
    }


def _tracker_gate_matrix(
    expected_ids: list[str],
    row_by_id: dict[str, dict[str, Any]],
    *,
    duplicate_ids: list[str],
) -> list[dict[str, Any]]:
    duplicate_set = set(duplicate_ids)
    matrix: list[dict[str, Any]] = []
    for af_id in expected_ids:
        row = row_by_id.get(af_id)
        if row is None:
            matrix.append(
                {
                    "id": af_id,
                    "status": "missing",
                    "done": False,
                    "duplicate": False,
                    "release_blocking": True,
                    "reason": "missing_tracker_row",
                }
            )
            continue
        status = str(row.get("status") or "")
        duplicate = af_id in duplicate_set
        release_blocking = status != "done" or duplicate
        reason = "ready" if not release_blocking else ("duplicate_tracker_row" if duplicate else status)
        matrix.append({**row, "duplicate": duplicate, "release_blocking": release_blocking, "reason": reason})
    return matrix

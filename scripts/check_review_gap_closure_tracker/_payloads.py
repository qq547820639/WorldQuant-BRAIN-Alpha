"""Section payload extractors and tracker summary builder.

Split from the former ``scripts/check_review_gap_closure_tracker.py`` monolith
(Task A3). Each extractor parses a Markdown section into a list of row dicts
and records shape/detail findings, and the summary builder collapses the
collected payloads into the JSON-serialisable tracker summary.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_review_gap_closure_tracker_helpers import (  # noqa: E402
    finding as _finding,
    frontend_mirror_only_decision as _frontend_mirror_only_decision,
    has_fact as _has_fact,
)

from ._constants import BASELINE_CHECKS, STATUS_MATRIX_ITEMS, TRIAGE_ITEMS
from ._tables import _expect_required_status_rows, _table_payload


def _current_run_baseline_payload(section: str, findings: list[dict[str, str]]) -> list[dict[str, str]]:
    required_columns = ("check", "result")
    rows = _table_payload(
        section,
        columns=required_columns,
        header="| Check |",
        shape_code="baseline_row_shape",
        shape_message="current run baseline row must contain check and result",
        detail_code="baseline_row_detail",
        detail_message="current run baseline row is missing required tracking detail",
        findings=findings,
    )
    for expected_check, expected_result_values in BASELINE_CHECKS:
        matches = [row for row in rows if expected_check in row["check"]]
        if not matches:
            findings.append(_finding("baseline_check", expected_check, "expected current run baseline check row is missing"))
            continue
        if len(matches) > 1:
            findings.append(
                _finding("baseline_duplicate_check", expected_check, "current run baseline check must appear exactly once")
            )
        result = matches[0]["result"]
        for expected_result in expected_result_values:
            if not _has_fact(result, expected_result):
                findings.append(
                    _finding(
                        "baseline_row_fact",
                        f"{expected_check}:{expected_result}",
                        "current run baseline row does not contain the required result evidence",
                    )
                )
    return rows


def _delivery_review_triage_payload(section: str, findings: list[dict[str, str]]) -> list[dict[str, str]]:
    required_columns = ("review_item", "current_tracking_decision", "current_evidence", "next_action")
    rows = _table_payload(
        section,
        columns=required_columns,
        header="| Review item |",
        shape_code="review_triage_row_shape",
        shape_message=(
            "delivery review triage row must contain review item, current tracking decision, evidence, and next action"
        ),
        detail_code="review_triage_row_detail",
        detail_message="delivery review triage row is missing required tracking detail",
        detail_columns=required_columns[1:],
        findings=findings,
    )
    _expect_required_status_rows(
        rows,
        key_column="review_item",
        status_column="current_tracking_decision",
        required_items=TRIAGE_ITEMS,
        missing_code="review_triage_item",
        duplicate_code="review_triage_duplicate_item",
        mismatch_code="review_triage_item",
        missing_message="expected delivery review triage row is missing",
        duplicate_message="delivery review triage item must appear exactly once",
        mismatch_message="delivery review triage row does not match the required current decision",
        findings=findings,
    )
    return rows


def _status_matrix_payload(section: str, findings: list[dict[str, str]]) -> list[dict[str, str]]:
    required_columns = ("gap", "status", "current_evidence", "remaining_evidence_needed")
    rows = _table_payload(
        section,
        columns=required_columns,
        header="| Gap |",
        shape_code="status_matrix_row_shape",
        shape_message="status matrix row must contain gap, status, current evidence, and remaining evidence needed",
        detail_code="status_matrix_row_detail",
        detail_message="status matrix row is missing required tracking detail",
        detail_columns=required_columns[1:],
        findings=findings,
    )
    _expect_required_status_rows(
        rows,
        key_column="gap",
        status_column="status",
        required_items=STATUS_MATRIX_ITEMS,
        missing_code="status_matrix_fact",
        duplicate_code="status_matrix_duplicate_gap",
        mismatch_code="status_matrix_fact",
        missing_message="expected status matrix row is missing",
        duplicate_message="status matrix gap must appear exactly once",
        mismatch_message="status matrix row does not match the required current status",
        findings=findings,
    )
    return rows


def _active_queue_payload(
    section: str,
    findings: list[dict[str, str]],
    *,
    expected_items: tuple[str, ...],
) -> list[dict[str, str]]:
    required_columns = ("item", "current_state", "unblock_condition", "minimum_verification")
    rows = _table_payload(
        section,
        columns=required_columns,
        header="| Item |",
        shape_code="queue_row_shape",
        shape_message="active work queue row must contain item, current state, unblock condition, and minimum verification",
        detail_code="queue_row_detail",
        detail_message="active work queue row is missing required tracking detail",
        detail_columns=required_columns[1:],
        findings=findings,
    )
    item_counts: dict[str, int] = {}
    for row in rows:
        item = row["item"]
        item_counts[item] = item_counts.get(item, 0) + 1
        if item not in expected_items:
            findings.append(_finding("queue_unexpected_item", item, "active work queue row item is not part of the current tracked queue contract"))
    for expected in expected_items:
        count = item_counts.get(expected, 0)
        if count == 0:
            findings.append(_finding("queue_item", expected, "expected active work queue row is missing"))
        elif count > 1:
            findings.append(_finding("queue_duplicate_item", expected, "active work queue item must appear exactly once"))
    return rows


def _check_active_queue_summary(
    section: str,
    active_queue: list[dict[str, str]],
    findings: list[dict[str, str]],
) -> None:
    stale_empty_queue_text = "No active blocking queue items remain"
    if active_queue and stale_empty_queue_text in section:
        findings.append(
            _finding(
                "active_queue_summary_fact",
                stale_empty_queue_text,
                "active work queue summary claims no active blockers while queue items are present",
            )
        )


def _check_tracker_self_summary_baseline(
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    result = next(
        (row["result"] for row in rows if "scripts/check_review_gap_closure_tracker.py --json" in row["check"]),
        "",
    )
    expected_claimable = f"completion_claimable={str(bool(summary['completion_claimable'])).lower()}"
    if expected_claimable not in result:
        findings.append(_finding("tracker_self_summary_fact", expected_claimable, "tracker self-check baseline row does not match the current completion claim state"))
    for blocker in summary["completion_blockers"]:
        if blocker not in result:
            findings.append(_finding("tracker_self_summary_fact", blocker, "tracker self-check baseline row is missing a current completion blocker"))


def _check_live_submit_baseline_facts(
    rows: list[dict[str, str]],
    live_submit: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    if not live_submit.get("available"):
        return
    result = next(
        (row["result"] for row in rows if "scripts/check_live_submit_readiness.py --json" in row["check"]),
        "",
    )
    if not result:
        return
    expected_values = [
        f"ready_to_submit={str(bool(live_submit.get('ready_to_submit'))).lower()}",
        f"eligible_count={int(live_submit.get('eligible_count') or 0)}",
        f"jobs_checked={int(live_submit.get('jobs_checked') or 0)}",
        f"job_ledgers_checked={int(live_submit.get('job_ledgers_checked') or 0)}",
        f"ledger_candidate_count={int(live_submit.get('ledger_candidate_count') or 0)}",
        f"ledger_eligible_count={int(live_submit.get('ledger_eligible_count') or 0)}",
        f"job_family_candidate_count={int(live_submit.get('job_family_candidate_count') or 0)}",
        f"job_family_eligible_count={int(live_submit.get('job_family_eligible_count') or 0)}",
        f"submission_ready={int(live_submit.get('submission_ready') or 0)}",
    ]
    latest_job_id = str(live_submit.get("latest_job_id") or "")
    if latest_job_id:
        expected_values.append(f"latest_job={latest_job_id}")
    max_similarity = live_submit.get("max_similarity")
    if max_similarity is not None:
        expected_values.append(f"max_similarity={max_similarity}")

    for expected in expected_values:
        if not _has_fact(result, expected):
            findings.append(
                _finding(
                    "baseline_row_fact",
                    f"scripts/check_live_submit_readiness.py --json:{expected}",
                    "current run baseline row does not contain the required result evidence",
                )
            )


def _tracker_summary_payload(
    *,
    status_matrix: list[dict[str, str]],
    active_queue: list[dict[str, str]],
    official_context: dict[str, Any],
    react_surface: dict[str, Any],
    live_submit: dict[str, Any],
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    statuses = [row["status"] for row in status_matrix]
    closed_count = sum(1 for status in statuses if status.startswith("CLOSED"))
    partial_count = sum(1 for status in statuses if status.startswith("PARTIAL"))
    status_counts = {"total": len(statuses), "closed": closed_count, "partial": partial_count, "other": len(statuses) - closed_count - partial_count}
    active_queue_items = [row["item"] for row in active_queue]
    open_status_items = [row["gap"] for row in status_matrix if not row["status"].startswith("CLOSED")]
    blocking_count = int(official_context.get("blocking_count") or 0)
    p1_count = int(official_context.get("p1_count") or 0)
    official_context_fresh = bool(official_context.get("available")) and blocking_count == 0 and p1_count == 0
    production_surface = str(react_surface.get("production_surface") or "")
    react_surface_kind = str(react_surface.get("react_surface") or "")
    frontend_mirror_only_decision = _frontend_mirror_only_decision(status_matrix)
    completion_blockers = (["tracker_findings"] if findings else []) + [f"active_queue:{item}" for item in active_queue_items] + [f"status:{item}" for item in open_status_items] + ([] if official_context_fresh else ["official_context_freshness"])
    return {
        "tracker_contract_ok": not findings,
        "completion_claimable": not completion_blockers,
        "completion_blockers": completion_blockers,
        "finding_count": len(findings),
        "status_counts": status_counts,
        "active_queue_count": len(active_queue_items),
        "active_queue_items": active_queue_items,
        "open_status_items": open_status_items,
        "official_context_fresh": official_context_fresh,
        "official_context_blocking_count": blocking_count,
        "official_context_p1_count": p1_count,
        "react_ready": bool(react_surface.get("ready")),
        "react_preview_only": production_surface == "inline_html_js" and react_surface_kind == "mirror",
        "frontend_mirror_only_decision": frontend_mirror_only_decision,
        "production_surface": production_surface,
        "react_surface": react_surface_kind,
        "react_build_runner": str(react_surface.get("build_runner") or ""),
        "live_submit_ready": bool(live_submit.get("ready_to_submit")),
        "live_submit_eligible_count": int(live_submit.get("eligible_count") or 0),
        "live_submit_candidate_count": int(live_submit.get("candidate_count") or 0),
        "live_submit_job_ledgers_checked": int(live_submit.get("job_ledgers_checked") or 0),
        "live_submit_jobs_checked": int(live_submit.get("jobs_checked") or 0),
        "live_submit_ledger_candidate_count": int(live_submit.get("ledger_candidate_count") or 0),
        "live_submit_ledger_eligible_count": int(live_submit.get("ledger_eligible_count") or 0),
        "live_submit_job_family_candidate_count": int(live_submit.get("job_family_candidate_count") or 0),
        "live_submit_job_family_eligible_count": int(live_submit.get("job_family_eligible_count") or 0),
        "live_submit_max_similarity": live_submit.get("max_similarity"),
        "live_submit_latest_job_id": str(live_submit.get("latest_job_id") or ""),
    }

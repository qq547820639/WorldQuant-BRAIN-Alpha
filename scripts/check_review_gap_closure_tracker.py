"""Validate the defect/implementation tracking document contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_review_gap_closure_tracker_helpers import (  # noqa: E402
    OFFICIAL_CONTEXT_QUEUE_ITEM,
    finding as _finding,
    check_official_context_queue as _check_official_context_queue,
    check_official_context_baseline_facts as _check_official_context_baseline_facts,
    check_official_context_refresh_baseline as _check_official_context_refresh_baseline,
    check_official_context_refresh_queue as _check_official_context_refresh_queue,
    check_real_submit_queue as _check_real_submit_queue,
    ADDITIONAL_TRIAGE_ITEMS as _ADDITIONAL_TRIAGE_ITEMS,
    ADDITIONAL_TRIAGE_SNIPPETS as _ADDITIONAL_TRIAGE_SNIPPETS,
    expect_all as _expect_all,
    live_submit_readiness_status as _live_submit_readiness_status,
    frontend_mirror_only_decision as _frontend_mirror_only_decision,
    frontend_surface_requires_queue as _frontend_surface_requires_queue,
    has_fact as _has_fact,
    reject_any as _reject_any,
    official_context_refresh_status as _official_context_refresh_status,
    official_context_status as _official_context_status,
    section as _section,
    table_cells as _table_cells,
    table_row as _table_row,
)

DEFAULT_TRACKER = ROOT / "docs" / "REVIEW_GAP_CLOSURE_20260530.md"
DEFAULT_DELIVERY_AUDIT = ROOT / "docs" / "DELIVERY_COMPLETION_AUDIT_20260528.md"
DEFAULT_CONFIG = ROOT / "config" / "run_config.json"
DEFAULT_JOBS = ROOT / "data" / "jobs_production.json"
DEFAULT_REFRESH_STATUS = ROOT / "data" / "official_context_refresh_status.json"
DEFAULT_REACT_APP_DIR = ROOT / "brain_alpha_ops" / "web" / "react_app"
SCHEMA_VERSION = "review_gap_closure_tracker_check.v1"

REQUIRED_SECTIONS = (
    "Current Run Baseline",
    "2026-05-31 Delivery Review Triage",
    "Status Matrix",
    "Active Work Queue",
    "Not Yet Claimable",
)
BASELINE_SNIPPETS = (
    "quality_gate.py config validation",
    "scripts/check_frontend_surface_parity.py --json",
    "scripts/check_frontend_innerhtml.py --json",
    "document.writeln",
    "scripts/check_tracked_data_inventory.py --json",
    "scripts/check_react_build_env.py --json",
    "ready=true",
    "build_runner=local_node_modules",
    "scripts/check_live_submit_readiness.py --json",
    "scan_sensitive_artifacts.py --root . --json --fail-on-findings --include-all --include-git-history",
    "scripts/check_v5_defect_tracking.py --json",
)
BASELINE_CHECKS = (
    ("quality_gate.py config validation", ("PASS",)),
    ("scripts/check_frontend_surface_parity.py --json", ("PASS",)),
    ("scripts/check_frontend_innerhtml.py --json", ("PASS", "document.writeln", "trustedHtml", "createContextualFragment")),
    ("scripts/check_tracked_data_inventory.py --json", ("PASS",)),
    (
        "scripts/check_diagnostic_report.py --config config/run_config.json --report docs/ALPHA_PRODUCTION_DIAGNOSIS_20260522.md --json",
        ("PASS",),
    ),
    ("scripts/check_react_build_env.py --json", ("PASS", "ready=true", "build_runner=local_node_modules")),
    (
        "scripts/check_live_submit_readiness.py --json",
        ("PASS",),
    ),
    (
        "scripts/scan_sensitive_artifacts.py --root . --json --fail-on-findings --include-all --include-git-history",
        ("PASS", "findings=[]"),
    ),
    ("scripts/check_review_gap_closure_tracker.py --json", ("PASS", "tracker_contract_ok=true")),
    ("scripts/check_v5_defect_tracking.py --json", ("PASS", "required_validation_count=29", "findings=[]")),
)
TRIAGE_SNIPPETS = (
    "BRAIN_E2E_*",
    "data/e2e_screenshots/example.png",
    "--include-all --include-git-history",
    "output/` runtime smoke artifacts",
    "session-cookie-*",
    ".outerHTML",
    "trustedHtml",
    "createContextualFragment",
    "explicit allowlist",
    "BRAIN_PASSWORD",
    "OPENAI_API_KEY",
    "timeout=300",
    "exit_code=124",
    "launch_web.py --smoke-test --frontend react --port 0",
    "explicit `0`",
    "OS-assigned",
) + _ADDITIONAL_TRIAGE_SNIPPETS
TRIAGE_ITEMS = (
    ("Review P0 hardcoded E2E credentials", "CLOSED_CURRENT"),
    ("Review P0 E2E screenshot ignore policy", "CLOSED_CURRENT"),
    ("Review P0 CI secret scan coverage", "CLOSED_CURRENT"),
    ("Review P1 inline HTML injection risk", "CLOSED_CURRENT"),
    ("Review P1 quality-gate subprocess environment", "CLOSED_CURRENT"),
    ("Review P1 quality-gate subprocess timeout", "CLOSED_CURRENT"),
    ("Review P2 quality-gate preview smoke port race", "CLOSED_CURRENT"),
) + _ADDITIONAL_TRIAGE_ITEMS
STATUS_MATRIX_ITEMS = (
    ("P0-2 React strict build", "CLOSED_CURRENT"),
    ("P2-6 Frontend automated tests", "CLOSED_LOCAL_WITH_TOOLCHAIN"),
    ("P3-1 Dual frontend unification", "CLOSED_CURRENT"),
)
BASE_QUEUE_ITEMS: tuple[str, ...] = ()
FRONTEND_SURFACE_QUEUE_ITEM = "Frontend production-surface promotion"
NOT_YET_SNIPPETS = (
    "Real BRAIN submit success is not claimable",
    "non-blocking follow-up",
    "eligible_count=0",
    "ledger_eligible_count=0",
    "job_family_eligible_count=0",
)
DELIVERY_AUDIT_SNIPPETS = (
    "docs/REVIEW_GAP_CLOSURE_20260530.md",
    "ready=true",
    "build_runner=local_node_modules",
    "lockfile, `node_modules`, required packages, and the React artifact are present",
)
STALE_DELIVERY_AUDIT_SNIPPETS = (
    "ready=false",
    "missing `npm`, lockfile",
    "current default PATH still needs npm",
    "React strict-build reproducibility on the current default PATH is not claimable",
)
TRACKER_STALE_SNIPPETS = (
    "advisory only: `ready=false`",
    "missing `npm`",
    "npm is missing on the current PATH",
    "npm-enabled local toolchain path",
    "current default PATH still needs npm",
    "React strict-build reproducibility on the current default PATH is not claimable",
    "live BRAIN submit as the only active queue item",
    "Official context validation is fresh with `p1_findings=0`",
)


def check_review_gap_closure_tracker(
    tracker_path: str | Path = DEFAULT_TRACKER,
    delivery_audit_path: str | Path = DEFAULT_DELIVERY_AUDIT,
    *,
    config_path: str | Path = DEFAULT_CONFIG,
    jobs_path: str | Path = DEFAULT_JOBS,
    refresh_status_path: str | Path = DEFAULT_REFRESH_STATUS,
    official_context_validation: dict[str, Any] | None = None,
    official_context_refresh_status_validation: dict[str, Any] | None = None,
    react_build_env_validation: dict[str, Any] | None = None,
    live_submit_readiness_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(tracker_path)
    findings: list[dict[str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "ok": False,
            "schema_version": SCHEMA_VERSION,
            "tracker": str(path),
            "findings": [_finding("missing_tracker", str(path), "tracker file does not exist")],
        }
    delivery_path = Path(delivery_audit_path)
    try:
        delivery_text = delivery_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        delivery_text = ""
        findings.append(_finding("missing_delivery_audit", str(delivery_path), "delivery audit file does not exist"))

    for section in REQUIRED_SECTIONS:
        if f"## {section}" not in text:
            findings.append(_finding("missing_section", section, "required tracker section is missing"))

    baseline = _section(text, "Current Run Baseline")
    _expect_all(baseline, BASELINE_SNIPPETS, "baseline_fact", findings)
    current_run_baseline = _current_run_baseline_payload(baseline, findings)
    official_context_refresh = _official_context_refresh_status(
        refresh_status_path=refresh_status_path,
        validation=official_context_refresh_status_validation,
        findings=findings,
    )
    _check_official_context_refresh_baseline(current_run_baseline, official_context_refresh, findings)
    triage = _section(text, "2026-05-31 Delivery Review Triage")
    _expect_all(triage, TRIAGE_SNIPPETS, "review_triage_fact", findings)
    delivery_review_triage = _delivery_review_triage_payload(triage, findings)
    status = _section(text, "Status Matrix")
    status_matrix = _status_matrix_payload(status, findings)
    _reject_any(text, TRACKER_STALE_SNIPPETS, "stale_tracker_fact", findings)

    queue = _section(text, "Active Work Queue")
    if "| Item | Current state | Unblock condition | Minimum verification |" not in queue:
        findings.append(
            _finding("queue_header", "Active Work Queue table header", "active work queue table header is missing")
        )
    official_context = _official_context_status(
        config_path=config_path,
        validation=official_context_validation,
        findings=findings,
    )
    _check_official_context_baseline_facts(current_run_baseline, official_context, findings)
    react_surface = _react_surface_status(validation=react_build_env_validation, findings=findings)
    live_submit = _live_submit_readiness_status(
        jobs_path=jobs_path,
        validation=live_submit_readiness_validation,
        findings=findings,
    )
    _check_live_submit_baseline_facts(current_run_baseline, live_submit, findings)
    active_queue = _active_queue_payload(
        queue,
        findings,
        expected_items=_expected_queue_items(
            official_context,
            react_surface=react_surface,
            status_matrix=status_matrix,
            live_submit=live_submit,
        ),
    )
    _check_active_queue_summary(queue, active_queue, findings)

    not_yet = _section(text, "Not Yet Claimable")
    _expect_all(not_yet, NOT_YET_SNIPPETS, "not_yet_claimable", findings)
    _check_real_submit_queue(text, not_yet, findings, live_submit)
    _expect_all(delivery_text, DELIVERY_AUDIT_SNIPPETS, "delivery_audit_fact", findings)
    _reject_any(delivery_text, STALE_DELIVERY_AUDIT_SNIPPETS, "stale_delivery_audit_fact", findings)
    _check_official_context_queue(text, queue, not_yet, official_context, findings)
    _check_official_context_refresh_queue(queue, official_context_refresh, findings)
    _check_frontend_surface_queue(text, queue, not_yet, react_surface, status_matrix, findings)
    current_completion = _tracker_summary_payload(
        status_matrix=status_matrix,
        active_queue=active_queue,
        official_context=official_context,
        react_surface=react_surface,
        live_submit=live_submit,
        findings=[],
    )
    _check_tracker_self_summary_baseline(current_run_baseline, current_completion, findings)
    summary = _tracker_summary_payload(
        status_matrix=status_matrix,
        active_queue=active_queue,
        official_context=official_context,
        react_surface=react_surface,
        live_submit=live_submit,
        findings=findings,
    )

    return {
        "ok": not findings,
        "schema_version": SCHEMA_VERSION,
        "tracker": str(path),
        "delivery_audit": str(delivery_path),
        "config": str(config_path),
        "current_run_baseline": current_run_baseline,
        "delivery_review_triage": delivery_review_triage,
        "status_matrix": status_matrix,
        "active_queue": active_queue,
        "official_context": official_context,
        "official_context_refresh": official_context_refresh,
        "react_surface": react_surface,
        "live_submit": live_submit,
        "summary": summary,
        "findings": findings,
    }


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


def _expected_queue_items(
    official_context: dict[str, Any],
    *,
    react_surface: dict[str, Any],
    status_matrix: list[dict[str, str]],
    live_submit: dict[str, Any],
) -> tuple[str, ...]:
    blocking_count = int(official_context.get("blocking_count") or 0)
    p1_count = int(official_context.get("p1_count") or 0)
    items = list(BASE_QUEUE_ITEMS)
    if _frontend_surface_requires_queue(react_surface, status_matrix):
        items.append(FRONTEND_SURFACE_QUEUE_ITEM)
    if not official_context.get("available") or blocking_count or p1_count:
        items.append(OFFICIAL_CONTEXT_QUEUE_ITEM)
    return tuple(items)


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


def _table_payload(
    section: str,
    *,
    columns: tuple[str, ...],
    header: str,
    shape_code: str,
    shape_message: str,
    detail_code: str,
    detail_message: str,
    findings: list[dict[str, str]],
    detail_columns: tuple[str, ...] | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    required_detail_columns = detail_columns or columns
    for line in section.splitlines():
        if not line.startswith("| ") or line.startswith("|---") or line.startswith(header):
            continue
        cells = _table_cells(line)
        if len(cells) != len(columns):
            findings.append(_finding(shape_code, line, shape_message))
            continue
        row = dict(zip(columns, cells))
        rows.append(row)
        row_name = row[columns[0]]
        for column in required_detail_columns:
            if not row[column].strip():
                findings.append(_finding(detail_code, f"{row_name}:{column}", detail_message))
    return rows


def _expect_required_status_rows(
    rows: list[dict[str, str]],
    *,
    key_column: str,
    status_column: str,
    required_items: tuple[tuple[str, str], ...],
    missing_code: str,
    duplicate_code: str,
    mismatch_code: str,
    missing_message: str,
    duplicate_message: str,
    mismatch_message: str,
    findings: list[dict[str, str]],
) -> None:
    status_by_item: dict[str, str] = {}
    counts: dict[str, int] = {}
    for row in rows:
        key = row[key_column]
        status_by_item[key] = row[status_column]
        counts[key] = counts.get(key, 0) + 1
    for item, expected_status in required_items:
        count = counts.get(item, 0)
        if count == 0:
            findings.append(_finding(missing_code, item, missing_message))
            continue
        if count > 1:
            findings.append(_finding(duplicate_code, item, duplicate_message))
        if status_by_item.get(item, "") != expected_status:
            findings.append(_finding(mismatch_code, f"{item}:{expected_status}", mismatch_message))


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


def _react_surface_status(
    *,
    validation: dict[str, Any] | None,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        payload = validation if validation is not None else _load_react_build_env_validation()
        return {
            "available": True,
            "ready": bool(payload.get("ready")),
            "production_surface": str(payload.get("production_surface") or ""),
            "react_surface": str(payload.get("react_surface") or ""),
            "build_runner": str((payload.get("tooling") or {}).get("build_runner") or ""),
        }
    except Exception as exc:
        findings.append(
            _finding(
                "react_surface_validation_error",
                str(DEFAULT_REACT_APP_DIR),
                f"could not validate current React surface status: {exc}",
            )
        )
        return {
            "available": False,
            "ready": False,
            "production_surface": "",
            "react_surface": "",
            "build_runner": "",
        }


def _load_react_build_env_validation() -> dict[str, Any]:
    from scripts.check_react_build_env import check_react_build_env

    return check_react_build_env(DEFAULT_REACT_APP_DIR)


def _check_frontend_surface_queue(
    text: str,
    queue: str,
    not_yet: str,
    react_surface: dict[str, Any],
    status_matrix: list[dict[str, str]],
    findings: list[dict[str, str]],
) -> None:
    if not react_surface.get("available"):
        return

    ready = bool(react_surface.get("ready"))
    production_surface = str(react_surface.get("production_surface") or "")
    react_surface_kind = str(react_surface.get("react_surface") or "")
    build_runner = str(react_surface.get("build_runner") or "")
    frontend_row = _table_row(queue, FRONTEND_SURFACE_QUEUE_ITEM)

    if ready:
        for expected in ("ready=true", "build_runner=local_node_modules"):
            if expected not in text:
                findings.append(
                    _finding(
                        "react_surface_fact",
                        expected,
                        "tracker does not reflect current React build readiness",
                    )
                )
    else:
        if "ready=true" in text:
            findings.append(
                _finding(
                    "stale_react_surface_fact",
                    "ready=true",
                    "tracker reports React ready=true while current validation is not ready",
                )
            )
        if "build_runner=local_node_modules" in text and build_runner != "local_node_modules":
            findings.append(
                _finding(
                    "stale_react_surface_fact",
                    "build_runner=local_node_modules",
                    "tracker reports React build readiness that current validation does not support",
                )
            )

    current_preview_split = production_surface == "inline_html_js" and react_surface_kind == "mirror"
    preview_phrases = (
        "inline HTML/JS console remains production",
        "inline HTML/JS console remains the production surface",
        "React remains explicit preview",
        "React mirror-only",
        "React preview path",
        "keep React mirror-only",
    )
    if current_preview_split:
        if _frontend_mirror_only_decision(status_matrix):
            if frontend_row:
                findings.append(
                    _finding(
                        "stale_frontend_surface_queue_fact",
                        FRONTEND_SURFACE_QUEUE_ITEM,
                        "tracker still reports frontend promotion work after the current release decision keeps React mirror-only",
                    )
                )
            _reject_any(
                not_yet,
                ("Frontend unification is not claimable",),
                "stale_frontend_surface_fact",
                findings,
                "not-yet-claimable section still reports frontend promotion work after the mirror-only decision",
            )
            return
        if not frontend_row:
            findings.append(
                _finding(
                    "frontend_surface_queue_fact",
                    FRONTEND_SURFACE_QUEUE_ITEM,
                    "current frontend split still needs an active promotion decision queue item",
                )
            )
        _expect_all(
            frontend_row,
            preview_phrases,
            "frontend_surface_queue_fact",
            findings,
            "frontend queue item does not reflect the current inline/React surface split",
        )
        if "Frontend unification is not claimable" not in not_yet:
            findings.append(
                _finding(
                    "frontend_surface_not_yet_fact",
                    "Frontend unification is not claimable",
                    "not-yet-claimable section does not reflect the current frontend split",
                )
            )
        return

    _reject_any(
        text,
        (*preview_phrases, "Frontend unification is not claimable"),
        "stale_frontend_surface_fact",
        findings,
        "tracker still reports preview-only frontend status after current validation changed",
    )


def _print_human_result(result: dict[str, Any]) -> None:
    state = "passed" if result["ok"] else "failed"
    print(f"review gap closure tracker check {state}: {result['tracker']}")
    summary = result.get("summary") or {}
    if summary:
        counts = summary["status_counts"]
        queue_items = ", ".join(summary["active_queue_items"]) or "none"
        claimable = "yes" if summary["completion_claimable"] else "no"
        print(f"summary: closed={counts['closed']}, partial={counts['partial']}, active_queue={summary['active_queue_count']}")
        print(f"active queue items: {queue_items}")
        print(f"official context: fresh={summary['official_context_fresh']}, blocking={summary['official_context_blocking_count']}, p1={summary['official_context_p1_count']}")
        print(f"frontend surface: production={summary['production_surface']}, react={summary['react_surface']}, ready={summary['react_ready']}, runner={summary['react_build_runner']}")
        print(f"completion claimable: {claimable}")
        if summary.get("completion_blockers"):
            print(f"completion blockers: {', '.join(summary['completion_blockers'])}")
    if not result["ok"]:
        for finding in result["findings"]:
            print(f"[{finding['code']}] {finding['message']}: {finding['expected']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check review gap closure tracker consistency.")
    parser.add_argument("--tracker", default=str(DEFAULT_TRACKER), help="Tracker Markdown path.")
    parser.add_argument("--delivery-audit", default=str(DEFAULT_DELIVERY_AUDIT), help="Delivery audit Markdown path.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Run config path for current official-context validation.")
    parser.add_argument("--jobs", default=str(DEFAULT_JOBS), help="Production jobs ledger path for live-submit readiness.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    result = check_review_gap_closure_tracker(args.tracker, args.delivery_audit, config_path=args.config, jobs_path=args.jobs)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human_result(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

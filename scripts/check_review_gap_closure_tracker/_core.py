"""Top-level review gap closure tracker check orchestrator.

Split from the former ``scripts/check_review_gap_closure_tracker.py`` monolith
(Task A3). Reads the tracker Markdown, drives the section payload extractors,
runs the official-context / refresh / live-submit / frontend surface checks,
and assembles the final tracker contract result dict.
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
    check_official_context_queue as _check_official_context_queue,
    check_official_context_baseline_facts as _check_official_context_baseline_facts,
    check_official_context_refresh_baseline as _check_official_context_refresh_baseline,
    check_official_context_refresh_queue as _check_official_context_refresh_queue,
    check_real_submit_queue as _check_real_submit_queue,
    expect_all as _expect_all,
    live_submit_readiness_status as _live_submit_readiness_status,
    official_context_refresh_status as _official_context_refresh_status,
    official_context_status as _official_context_status,
    reject_any as _reject_any,
    section as _section,
)

from ._constants import (
    BASELINE_SNIPPETS,
    DEFAULT_CONFIG,
    DEFAULT_DELIVERY_AUDIT,
    DEFAULT_JOBS,
    DEFAULT_REFRESH_STATUS,
    DEFAULT_TRACKER,
    DELIVERY_AUDIT_SNIPPETS,
    NOT_YET_SNIPPETS,
    REQUIRED_SECTIONS,
    SCHEMA_VERSION,
    STALE_DELIVERY_AUDIT_SNIPPETS,
    TRACKER_STALE_SNIPPETS,
    TRIAGE_SNIPPETS,
)
from ._payloads import (
    _active_queue_payload,
    _check_active_queue_summary,
    _check_live_submit_baseline_facts,
    _check_tracker_self_summary_baseline,
    _current_run_baseline_payload,
    _delivery_review_triage_payload,
    _status_matrix_payload,
    _tracker_summary_payload,
)
from ._surface_checks import _check_frontend_surface_queue, _react_surface_status
from ._tables import _expected_queue_items


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

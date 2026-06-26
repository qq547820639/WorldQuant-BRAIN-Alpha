"""Queue and baseline checkers for the review gap closure tracker."""

from __future__ import annotations

from typing import Any

from ._constants import OFFICIAL_CONTEXT_QUEUE_ITEM
from ._text_helpers import (
    _check_baseline_row_values,
    expect_all,
    finding,
    has_fact,
    reject_any,
    table_row,
)


def check_real_submit_queue(
    tracker_text: str,
    not_yet: str,
    findings: list[dict[str, str]],
    live_submit: dict[str, Any] | None = None,
) -> None:
    rows = [line for line in tracker_text.splitlines() if line.startswith("| Real BRAIN submit E2E |")]
    row = rows[0] if rows else ""
    if not row:
        findings.append(
            finding(
                "real_submit_boundary_fact",
                "Real BRAIN submit E2E",
                "non-blocking live-submit safety evidence row is missing",
            )
        )
    elif len(rows) > 1:
        findings.append(
            finding(
                "real_submit_duplicate_item",
                "Real BRAIN submit E2E",
                "non-blocking live-submit safety evidence row must appear exactly once",
            )
        )
    expected_boundary_facts = (
        "confirmed on 2026-06-02",
        "non-blocking",
        "last production path correctly failed closed on high similarity risk",
        "low-risk candidate with complete official metrics",
        "confirm no safety gate was bypassed",
    )
    expect_all(
        row,
        expected_boundary_facts,
        "real_submit_boundary_fact",
        findings,
        "real BRAIN submit E2E safety evidence is missing required non-blocking confirmation or future-submit safety gates",
    )
    if live_submit and live_submit.get("available") and not live_submit.get("ready_to_submit"):
        expected_live_facts = [
            "ready_to_submit=false",
            f"eligible_count={int(live_submit.get('eligible_count') or 0)}",
            f"jobs_checked={int(live_submit.get('jobs_checked') or 0)}",
            f"job_ledgers_checked={int(live_submit.get('job_ledgers_checked') or 0)}",
            f"ledger_eligible_count={int(live_submit.get('ledger_eligible_count') or 0)}",
            f"job_family_candidate_count={int(live_submit.get('job_family_candidate_count') or 0)}",
            f"job_family_eligible_count={int(live_submit.get('job_family_eligible_count') or 0)}",
            f"submission_ready={int(live_submit.get('submission_ready') or 0)}",
        ]
        max_similarity = live_submit.get("max_similarity")
        if max_similarity is not None:
            expected_live_facts.append(f"max_similarity={max_similarity}")
        expect_all(
            row,
            tuple(expected_live_facts),
            "real_submit_readiness_fact",
            findings,
            "real BRAIN submit E2E queue item does not reflect current live-submit readiness evidence",
        )
    if "confirmed on 2026-06-02" not in not_yet or "non-blocking" not in not_yet:
        findings.append(
            finding(
                "real_submit_not_yet_fact",
                "confirmed on 2026-06-02",
                "not-yet-claimable section does not preserve the operator-confirmed non-blocking live-submit boundary",
            )
        )


def check_official_context_refresh_baseline(
    rows: list[dict[str, str]],
    refresh_status: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    matches = [
        row
        for row in rows
        if "fetch_official_context.py --config config/run_config.json" in row["check"]
        and "--json" in row["check"]
    ]
    if not matches or not refresh_status.get("available"):
        return
    result = matches[0]["result"]
    expected_values = [
        "PASS" if refresh_status.get("ok") else "FAILED",
        f"status={refresh_status.get('status')}",
        f"write_enabled={str(bool(refresh_status.get('write_enabled'))).lower()}",
        f"manifest_stale={str(bool(refresh_status.get('manifest_stale'))).lower()}",
    ]
    if refresh_status.get("error_code"):
        expected_values.append(f"error_code={refresh_status.get('error_code')}")
    if refresh_status.get("error_category"):
        expected_values.append(f"error_category={refresh_status.get('error_category')}")

    for expected in expected_values:
        if not has_fact(result, expected):
            findings.append(
                finding(
                    "official_context_refresh_baseline_fact",
                    expected,
                    "official context refresh baseline row does not match the latest refresh status",
                )
            )


def check_official_context_baseline_facts(
    rows: list[dict[str, str]],
    official_context: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    if not official_context.get("available"):
        return
    fetch_rows = [
        row
        for row in rows
        if "fetch_official_context.py --config config/run_config.json" in row["check"]
        and "--json" in row["check"]
    ]
    check_rows = [
        row
        for row in rows
        if "scripts/check_official_context.py --config config/run_config.json" in row["check"]
        and "--json" in row["check"]
    ]
    _check_baseline_row_values(
        fetch_rows,
        "official_context_refresh_baseline_fact",
        [
            ("fields", official_context.get("fields")),
            ("operators", official_context.get("operators")),
            ("datasets", official_context.get("datasets")),
        ],
        findings,
        "official context refresh baseline row does not match current official context counts",
    )
    _check_baseline_row_values(
        check_rows,
        "official_context_baseline_fact",
        [
            ("validation_ok", str(bool(official_context.get("validation_ok"))).lower()),
            ("blocking_ok", str(bool(official_context.get("blocking_ok"))).lower()),
            ("blocking_count", official_context.get("blocking_count")),
            ("p1_count", official_context.get("p1_count")),
            ("dataset_field_count_sum", official_context.get("dataset_field_count_sum")),
        ],
        findings,
        "official context baseline row does not match current official context validation",
    )


def check_official_context_refresh_queue(
    queue: str,
    refresh_status: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    if not refresh_status.get("available"):
        return
    row = table_row(queue, OFFICIAL_CONTEXT_QUEUE_ITEM)
    if not row:
        return
    expected_values = [
        f"status={refresh_status.get('status')}",
        f"write_enabled={str(bool(refresh_status.get('write_enabled'))).lower()}",
        f"manifest_stale={str(bool(refresh_status.get('manifest_stale'))).lower()}",
    ]
    if refresh_status.get("error_code"):
        expected_values.append(f"error_code={refresh_status.get('error_code')}")
    if refresh_status.get("error_category"):
        expected_values.append(f"error_category={refresh_status.get('error_category')}")

    for expected in expected_values:
        if not has_fact(row, expected):
            findings.append(
                finding(
                    "official_context_refresh_queue_fact",
                    expected,
                    "official context queue row does not match the latest refresh status",
                )
            )


def check_official_context_queue(
    _text: str,
    queue: str,
    not_yet: str,
    official_context: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    if not official_context.get("available"):
        return

    blocking_count = int(official_context.get("blocking_count") or 0)
    p1_count = int(official_context.get("p1_count") or 0)
    row = table_row(queue, OFFICIAL_CONTEXT_QUEUE_ITEM)
    has_refresh_item = bool(row)

    if blocking_count:
        if not has_refresh_item:
            findings.append(finding("official_context_queue_fact", OFFICIAL_CONTEXT_QUEUE_ITEM, "official context has blocking findings but the active queue is missing the refresh item"))
        if f"blocking_count={blocking_count}" not in row:
            findings.append(finding("official_context_queue_fact", f"blocking_count={blocking_count}", "official context queue item does not reflect current blocking findings"))
        return

    if p1_count:
        if not has_refresh_item:
            findings.append(finding("official_context_queue_fact", OFFICIAL_CONTEXT_QUEUE_ITEM, "official context has P1 freshness findings but the active queue is missing the refresh item"))
        if f"p1_findings={p1_count}" not in row:
            findings.append(finding("official_context_queue_fact", f"p1_findings={p1_count}", "official context queue item does not match the current P1 finding count"))
        if "expired official metadata" not in row:
            findings.append(finding("official_context_queue_fact", "expired official metadata", "official context queue item does not name the current freshness reason"))
        if "Official context freshness is not claimable" not in not_yet:
            findings.append(finding("official_context_not_yet_fact", "Official context freshness is not claimable", "not-yet-claimable section does not reflect stale official context"))
        return

    if has_refresh_item:
        findings.append(finding("stale_official_context_queue_fact", OFFICIAL_CONTEXT_QUEUE_ITEM, "tracker still reports official-context refresh work after current validation is fresh"))
    reject_any(
        not_yet,
        ("Official context freshness is not claimable", "expired official metadata", "p1_findings="),
        "stale_official_context_queue_fact",
        findings,
        "tracker still reports official-context freshness work after current validation has no findings",
    )
    if row:
        reject_any(
            row,
            ("p1_findings=", "expired official metadata"),
            "stale_official_context_queue_fact",
            findings,
            "tracker still reports official-context freshness work after current validation has no findings",
        )

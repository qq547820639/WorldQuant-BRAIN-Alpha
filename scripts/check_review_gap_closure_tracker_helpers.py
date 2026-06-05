from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


OFFICIAL_CONTEXT_QUEUE_ITEM = "Official context refresh"


def section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start == -1:
        return ""
    next_start = text.find("\n## ", start + len(marker))
    return text[start:] if next_start == -1 else text[start:next_start]


def expect_all(
    text: str,
    expected_values: tuple[str, ...],
    code: str,
    findings: list[dict[str, str]],
    message: str = "expected tracker fact is missing",
) -> None:
    for expected in expected_values:
        if expected not in text:
            findings.append(finding(code, expected, message))


def has_fact(text: str, expected: str) -> bool:
    if "=" not in expected:
        return expected in text
    return re.search(r"(?<![A-Za-z0-9_])" + re.escape(expected) + r"(?![A-Za-z0-9_])", text) is not None


def reject_any(
    text: str,
    rejected_values: tuple[str, ...],
    code: str,
    findings: list[dict[str, str]],
    message: str = "stale tracker fact is still present",
) -> None:
    for rejected in rejected_values:
        if rejected in text:
            findings.append(finding(code, rejected, message))


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


def live_submit_readiness_status(
    *,
    jobs_path: str | Path,
    validation: dict[str, Any] | None,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        if validation is None:
            from scripts.check_live_submit_readiness import check_live_submit_readiness

            payload = check_live_submit_readiness(jobs_path)
        else:
            payload = validation
        summary = payload.get("summary_counts") or {}
        return {
            "available": True,
            "ok": bool(payload.get("ok")),
            "ready_to_submit": bool(payload.get("ready_to_submit")),
            "eligible_count": int(payload.get("eligible_count") or 0),
            "candidate_count": int(payload.get("candidate_count") or 0),
            "job_ledgers_checked": int(payload.get("job_ledgers_checked") or 0),
            "jobs_checked": int(payload.get("jobs_checked") or 0),
            "ledger_candidate_count": int(payload.get("ledger_candidate_count") or 0),
            "ledger_eligible_count": int(payload.get("ledger_eligible_count") or 0),
            "job_family_candidate_count": int(payload.get("job_family_candidate_count") or 0),
            "job_family_eligible_count": int(payload.get("job_family_eligible_count") or 0),
            "job_family_ready_to_submit": bool(payload.get("job_family_ready_to_submit")),
            "latest_job_id": str(payload.get("latest_job_id") or ""),
            "max_similarity": payload.get("max_similarity"),
            "submission_ready": int(summary.get("submission_ready") or 0),
        }
    except Exception as exc:
        findings.append(
            finding(
                "live_submit_readiness_error",
                str(jobs_path),
                f"could not validate current live-submit readiness: {exc}",
            )
        )
        return {"available": False, "ok": False, "ready_to_submit": False}


def official_context_refresh_status(
    *,
    refresh_status_path: str | Path,
    validation: dict[str, Any] | None,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    if validation is None:
        path = Path(refresh_status_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"available": False, "path": str(path)}
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(finding("official_context_refresh_status", str(path), f"could not read refresh status: {exc}"))
            return {"available": False, "path": str(path)}
    else:
        payload = validation
        path = Path(str(payload.get("status_path") or refresh_status_path))

    before = payload.get("before") if isinstance(payload.get("before"), dict) else {}
    after = payload.get("after") if isinstance(payload.get("after"), dict) else {}
    manifest_stale = bool(after.get("manifest_stale") if "manifest_stale" in after else before.get("manifest_stale"))
    return {
        "available": True,
        "path": str(path),
        "ok": bool(payload.get("ok")),
        "status": str(payload.get("status") or ""),
        "error_code": str(payload.get("error_code") or ""),
        "error_category": str(payload.get("error_category") or ""),
        "retryable": bool(payload.get("retryable")),
        "write_enabled": bool(payload.get("write_enabled")),
        "manifest_stale": manifest_stale,
    }


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


def official_context_status(
    *,
    config_path: str | Path,
    validation: dict[str, Any] | None,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        payload = validation if validation is not None else _load_official_context_validation(config_path)
        return {
            "available": True,
            "blocking_ok": bool(payload.get("blocking_ok")),
            "blocking_count": int(payload.get("blocking_count") or 0),
            "p1_count": int(payload.get("p1_count") or 0),
        }
    except Exception as exc:
        findings.append(
            finding(
                "official_context_validation_error",
                str(config_path),
                f"could not validate current official context: {exc}",
            )
        )
        return {"available": False, "blocking_ok": False, "blocking_count": 0, "p1_count": 0}


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
        ("Official context freshness is not claimable", "expired official metadata"),
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


def _load_official_context_validation(config_path: str | Path) -> dict[str, Any]:
    from brain_alpha_ops.data.official_context_validation import validate_official_context

    return validate_official_context(config_path=config_path)


def frontend_mirror_only_decision(status_matrix: list[dict[str, str]]) -> bool:
    row = next((item for item in status_matrix if item.get("gap") == "P3-1 Dual frontend unification"), {})
    evidence = f"{row.get('current_evidence', '')} {row.get('remaining_evidence_needed', '')}"
    return (
        row.get("status") == "CLOSED_CURRENT"
        and "mirror-only" in evidence
        and "current release" in evidence
        and "frontend_surface_parity" in evidence
    )


def frontend_surface_requires_queue(react_surface: dict[str, Any], status_matrix: list[dict[str, str]]) -> bool:
    if not react_surface.get("available"):
        return True
    production_surface = str(react_surface.get("production_surface") or "")
    react_surface_kind = str(react_surface.get("react_surface") or "")
    current_preview_split = production_surface == "inline_html_js" and react_surface_kind == "mirror"
    return current_preview_split and not frontend_mirror_only_decision(status_matrix)


def table_row(section: str, first_cell: str) -> str:
    prefix = f"| {first_cell} |"
    for line in section.splitlines():
        if line.startswith(prefix):
            return line
    return ""


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def finding(code: str, expected: str, message: str) -> dict[str, str]:
    return {"code": code, "expected": expected, "message": message}


ADDITIONAL_TRIAGE_SNIPPETS = (
    "Review 2026-06-01 P0 baseUrl SSRF risk",
    "Review 2026-06-01 P0 request body size limit",
    "Review 2026-06-01 P1 traceback leakage",
    "Review 2026-06-01 P1 production budget numeric limits",
    "Review 2026-06-01 P1 silent exception swallowing",
)

ADDITIONAL_TRIAGE_ITEMS = (
    ("Review 2026-06-01 P0 baseUrl SSRF risk", "CLOSED_CURRENT"),
    ("Review 2026-06-01 P0 request body size limit", "CLOSED_CURRENT"),
    ("Review 2026-06-01 P1 traceback leakage", "CLOSED_CURRENT"),
    ("Review 2026-06-01 P1 production budget numeric limits", "CLOSED_CURRENT"),
    ("Review 2026-06-01 P1 silent exception swallowing", "CLOSED_CURRENT"),
)

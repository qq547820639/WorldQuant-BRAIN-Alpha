from __future__ import annotations

from pathlib import Path
import re
from typing import Any


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
    queue: str,
    not_yet: str,
    findings: list[dict[str, str]],
    live_submit: dict[str, Any] | None = None,
) -> None:
    row = table_row(queue, "Real BRAIN submit E2E")
    expected_queue_facts = (
        "last production path correctly failed closed on high similarity risk",
        "low-risk candidate with complete official metrics",
        "operator explicitly confirms a live submit attempt",
        "confirm no safety gate was bypassed",
    )
    expect_all(
        row,
        expected_queue_facts,
        "real_submit_queue_fact",
        findings,
        "real BRAIN submit E2E queue item is missing required safety evidence or unblock criteria",
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
    if "without a low-risk candidate and explicit human confirmation" not in not_yet:
        findings.append(
            finding(
                "real_submit_not_yet_fact",
                "without a low-risk candidate and explicit human confirmation",
                "not-yet-claimable section does not preserve the live-submit safety gate",
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

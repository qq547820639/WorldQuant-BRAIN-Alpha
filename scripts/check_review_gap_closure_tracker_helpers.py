from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


"""Helper utilities for the review gap closure tracker validator.

Re-export shim. The implementation has been split into the
``scripts.check_review_gap_closure_tracker_helpers`` subpackage (Task A9 of
deep-optimization-phase12). The public API is re-exported here so
``from scripts.check_review_gap_closure_tracker_helpers import ...`` continues
to resolve to the package directory (Python prefers the package ``__init__.py``
over the sibling ``scripts/check_review_gap_closure_tracker_helpers.py`` shim
when both exist). The thin ``scripts/check_review_gap_closure_tracker_helpers.py``
shim remains only to preserve ``python scripts/check_review_gap_closure_tracker_helpers.py``
direct execution, including the ``sys.path`` bootstrap for ``brain_alpha_ops``.
"""



__all__ = [
    "OFFICIAL_CONTEXT_QUEUE_ITEM",
    "ADDITIONAL_TRIAGE_SNIPPETS",
    "ADDITIONAL_TRIAGE_ITEMS",
    "section",
    "expect_all",
    "has_fact",
    "reject_any",
    "check_real_submit_queue",
    "live_submit_readiness_status",
    "official_context_refresh_status",
    "check_official_context_refresh_baseline",
    "check_official_context_baseline_facts",
    "check_official_context_refresh_queue",
    "official_context_status",
    "check_official_context_queue",
    "frontend_mirror_only_decision",
    "frontend_surface_requires_queue",
    "table_row",
    "table_cells",
    "finding",
    "_check_baseline_row_values",
    "_record_count",
    "_optional_int",
    "_load_official_context_validation",
]


"""Constants for the review gap closure tracker helpers subpackage."""



OFFICIAL_CONTEXT_QUEUE_ITEM = "Official context refresh"


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


"""Frontend surface decisions for the review gap closure tracker."""


from typing import Any


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


"""Queue and baseline checkers for the review gap closure tracker."""


from typing import Any



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


"""Official context / refresh / live-submit status loaders for the tracker.

Each function accepts an optional pre-computed validation dict (used by tests
and by callers that already have the validation result). When ``validation``
is ``None``, the function loads the validation from the canonical source
(script or JSON file). The returned dict is the normalised tracker payload
shape consumed by ``check_review_gap_closure_tracker`` and the queue/baseline
checkers.
"""


import json
from pathlib import Path
from typing import Any



def _optional_int(value: Any) -> int | None:
    """Coerce ``value`` to ``int`` or return ``None`` on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_count(files: dict[str, Any], filename: str) -> int:
    """Extract the ``record_count`` for a context file, defaulting to ``0``."""
    entry = files.get(filename) or {}
    return int(entry.get("record_count") or 0)


def _load_official_context_validation(config_path: str | Path) -> dict[str, Any]:
    """Load official context validation via the canonical checker.

    ``validate_official_context`` returns ``ok`` but the tracker contract uses
    ``validation_ok`` as the field name; mirror it so downstream extraction
    works uniformly for both the loader path and the test-fixture path.
    """
    from brain_alpha_ops.data.official_context_validation import validate_official_context

    payload = validate_official_context(config_path=config_path)
    if "validation_ok" not in payload:
        payload["validation_ok"] = bool(payload.get("ok"))
    return payload


def official_context_status(
    *,
    config_path: str | Path,
    validation: dict[str, Any] | None,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    """Normalise official context validation into the tracker payload shape."""
    try:
        payload = (
            validation
            if validation is not None
            else _load_official_context_validation(config_path)
        )
        files = payload.get("files") or {}
        lineage = payload.get("lineage") or {}
        return {
            "available": True,
            "validation_ok": bool(payload.get("validation_ok", payload.get("ok"))),
            "blocking_ok": bool(payload.get("blocking_ok")),
            "blocking_count": int(payload.get("blocking_count") or 0),
            "p1_count": int(payload.get("p1_count") or 0),
            "fields": _record_count(files, "official_fields.json"),
            "operators": _record_count(files, "official_operators.json"),
            "datasets": _record_count(files, "official_datasets.json"),
            "dataset_field_count_sum": int(lineage.get("dataset_field_count_sum") or 0),
        }
    except Exception as exc:
        findings.append(
            finding(
                "official_context_validation_error",
                str(config_path),
                f"could not validate current official context status: {exc}",
            )
        )
        return {
            "available": False,
            "validation_ok": False,
            "blocking_ok": False,
            "blocking_count": 0,
            "p1_count": 0,
            "fields": 0,
            "operators": 0,
            "datasets": 0,
            "dataset_field_count_sum": 0,
        }


def official_context_refresh_status(
    *,
    refresh_status_path: str | Path,
    validation: dict[str, Any] | None,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    """Normalise official context refresh status into the tracker payload shape."""
    try:
        if validation is not None:
            payload = validation
        else:
            path = Path(refresh_status_path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        before = payload.get("before") or {}
        after = payload.get("after") or {}
        manifest_stale = before.get("manifest_stale")
        if manifest_stale is None:
            manifest_stale = after.get("manifest_stale")
        return {
            "available": True,
            "ok": bool(payload.get("ok")),
            "status": str(payload.get("status") or ""),
            "error_code": str(payload.get("error_code") or ""),
            "error_category": str(payload.get("error_category") or ""),
            "write_enabled": bool(payload.get("write_enabled")),
            "manifest_stale": bool(manifest_stale),
        }
    except Exception as exc:
        findings.append(
            finding(
                "official_context_refresh_validation_error",
                str(refresh_status_path),
                f"could not validate current official context refresh status: {exc}",
            )
        )
        return {
            "available": False,
            "ok": False,
            "status": "",
            "error_code": "",
            "error_category": "",
            "write_enabled": False,
            "manifest_stale": False,
        }


def live_submit_readiness_status(
    *,
    jobs_path: str | Path,
    validation: dict[str, Any] | None,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    """Normalise live submit readiness validation into the tracker payload shape."""
    try:
        if validation is not None:
            payload = validation
        else:
            from scripts.check_live_submit_readiness import check_live_submit_readiness

            payload = check_live_submit_readiness(jobs_path)
        summary_counts = payload.get("summary_counts") or {}
        return {
            "available": True,
            "ready_to_submit": bool(payload.get("ready_to_submit")),
            "eligible_count": int(payload.get("eligible_count") or 0),
            "candidate_count": int(payload.get("candidate_count") or 0),
            "jobs_checked": int(payload.get("jobs_checked") or 0),
            "job_ledgers_checked": int(payload.get("job_ledgers_checked") or 0),
            "ledger_candidate_count": int(payload.get("ledger_candidate_count") or 0),
            "ledger_eligible_count": int(payload.get("ledger_eligible_count") or 0),
            "job_family_candidate_count": int(payload.get("job_family_candidate_count") or 0),
            "job_family_eligible_count": int(payload.get("job_family_eligible_count") or 0),
            "latest_job_id": str(payload.get("latest_job_id") or ""),
            "max_similarity": payload.get("max_similarity"),
            "submission_ready": int(summary_counts.get("submission_ready") or 0),
        }
    except Exception as exc:
        findings.append(
            finding(
                "live_submit_readiness_validation_error",
                str(jobs_path),
                f"could not validate current live submit readiness: {exc}",
            )
        )
        return {
            "available": False,
            "ready_to_submit": False,
            "eligible_count": 0,
            "candidate_count": 0,
            "jobs_checked": 0,
            "job_ledgers_checked": 0,
            "ledger_candidate_count": 0,
            "ledger_eligible_count": 0,
            "job_family_candidate_count": 0,
            "job_family_eligible_count": 0,
            "latest_job_id": "",
            "max_similarity": None,
            "submission_ready": 0,
        }


"""Text/table primitives and finding builders for tracker validation."""


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


def _check_baseline_row_values(
    rows: list[dict[str, str]],
    code: str,
    expected_values: list[tuple[str, Any]],
    findings: list[dict[str, str]],
    message: str,
) -> None:
    if not rows:
        return
    result = rows[0]["result"]
    for key, value in expected_values:
        if value is None:
            continue
        expected = f"{key}={value}"
        if not has_fact(result, expected):
            findings.append(finding(code, expected, message))


if __name__ == "__main__":
    raise SystemExit(main())
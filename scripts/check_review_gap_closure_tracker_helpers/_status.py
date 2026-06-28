"""Official context / refresh / live-submit status loaders for the tracker.

Each function accepts an optional pre-computed validation dict (used by tests
and by callers that already have the validation result). When ``validation``
is ``None``, the function loads the validation from the canonical source
(script or JSON file). The returned dict is the normalised tracker payload
shape consumed by ``check_review_gap_closure_tracker`` and the queue/baseline
checkers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._text_helpers import finding


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

"""Persist candidate-level evidence produced by Web check flows."""

from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.web_candidates.audit import append_scientific_audit_event
from brain_alpha_ops.web_candidates.simulation_state import save_candidate_update

logger = logging.getLogger(__name__)

SaveCandidateUpdate = Callable[[str, dict[str, Any], list[str]], None]

CHECK_EVIDENCE_FIELDS = [
    "cloud_correlation_risk",
    "cloud_status",
    "context_health",
    "observability_preflight",
    "latest_check",
    "last_check_status",
    "last_check_passed",
    "last_check_submittable",
    "last_check_at",
    "scientific_audit",
]


def persist_candidate_check_evidence(
    storage_dir: str,
    candidate: dict[str, Any],
    result: dict[str, Any],
    *,
    save_update: SaveCandidateUpdate = save_candidate_update,
) -> None:
    """Merge safe check evidence back into ``candidates.jsonl``.

    The full check row remains in ``checks.jsonl``. Submit-readiness audits use
    candidate rows as the source of truth, so the small subset needed for
    gating is mirrored there without ever marking a candidate submission-ready.
    """

    update = candidate_check_evidence_update(candidate, result)
    if not update:
        return
    try:
        save_update(storage_dir, update, CHECK_EVIDENCE_FIELDS)
    except Exception as exc:
        logger.warning(
            "failed to persist candidate check evidence for alpha_id=%s: %s",
            redact_text(update.get("alpha_id", "?"), max_length=64),
            redact_error_message(exc),
        )


def candidate_check_evidence_update(candidate: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Return a minimal candidate update row derived from a check result."""

    if not isinstance(candidate, dict) or not isinstance(result, dict):
        return {}
    update: dict[str, Any] = {}
    for key in ("alpha_id", "official_alpha_id", "expression", "dataset_id"):
        value = candidate.get(key) or result.get(key)
        if value not in (None, ""):
            update[key] = value

    for key in ("cloud_correlation_risk", "cloud_status", "context_health", "observability_preflight"):
        value = result.get(key)
        if isinstance(value, dict):
            update[key] = value

    checked_at = str(result.get("checked_at") or utc_now())
    latest_check = {
        "status": str(result.get("status") or ""),
        "passed": bool(result.get("passed")) if "passed" in result else False,
        "submittable": bool(result.get("submittable")) if "submittable" in result else False,
        "checked_at": checked_at,
        "failed_reasons": [str(item) for item in result.get("failed_reasons") or [] if str(item)][:12],
    }
    update["latest_check"] = latest_check
    update["last_check_status"] = latest_check["status"]
    update["last_check_passed"] = latest_check["passed"]
    update["last_check_submittable"] = latest_check["submittable"]
    update["last_check_at"] = checked_at
    audited = append_scientific_audit_event(
        {**candidate, **update},
        operation="pre_submit_availability_check",
        source="web_check_availability",
        feedback_sources=["pre_submit_availability_check", "cloud_similarity", "context_health"],
        official_api_called=_official_pre_submit_check_was_called(result),
        details={
            "status": latest_check["status"],
            "passed": latest_check["passed"],
            "submittable": latest_check["submittable"],
            "official_check_called": _official_pre_submit_check_was_called(result),
        },
    )
    update["scientific_audit"] = audited["scientific_audit"]
    return update


def _official_pre_submit_check_was_called(result: dict[str, Any]) -> bool:
    for check in result.get("checks") or []:
        if not isinstance(check, dict) or check.get("name") != "official_pre_submit_check":
            continue
        detail = str(check.get("detail") or "")
        return not detail.startswith("Skipped")
    return False

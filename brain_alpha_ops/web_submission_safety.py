"""Submission safety preflight services for the local web console."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.safety import SubmissionLedger, mock_source_reasons
from brain_alpha_ops.web_candidate_selection import official_alpha_id


LedgerFactory = Callable[[str], SubmissionLedger]
CloudAlphaSnapshot = Callable[..., dict[str, Any]]
CloudStatusFor = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]]
ObservabilityBuilder = Callable[..., dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]


def submit_preflight_block(error_code: str, error: str, *, category: str = "validation", action: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error_code": error_code, "error_category": category, "error": error}
    if action:
        payload["action"] = action
    return payload


def submission_preflight_advisory(
    candidate: dict[str, Any],
    run_config: RunConfig,
    *,
    ledger_factory: LedgerFactory = SubmissionLedger,
    cloud_alpha_snapshot: CloudAlphaSnapshot,
    cloud_status_for: CloudStatusFor,
) -> dict[str, Any]:
    official_id = official_alpha_id(candidate)
    if not official_id:
        return submit_preflight_block(
            "MISSING_OFFICIAL_ID",
            "Missing official Alpha ID; run an official simulation before production submit.",
            action="Run an official simulation before submitting.",
        )
    if str(run_config.environment).lower() == "production":
        mock_reasons = mock_source_reasons(candidate)
        if mock_reasons:
            return submit_preflight_block(
                "SUBMIT_NON_PRODUCTION_CANDIDATE",
                "Production submit blocked non-production mock/demo/test candidate: " + "; ".join(mock_reasons),
                action="Use only production-origin candidates for production submission.",
            )
    gate = candidate.get("gate") or {}
    if not (gate.get("submission_ready") or candidate.get("lifecycle_status") == "submission_ready"):
        return submit_preflight_block(
            "SUBMIT_NOT_READY",
            "Alpha is not submission-ready; complete the passed/submittable check flow first.",
            action="Complete the passed/submittable check flow before submitting.",
        )
    status_text = f"{candidate.get('lifecycle_status', '')} {gate.get('status', '')}".lower()
    if any(word in status_text for word in ("failed", "rejected", "not_passed")):
        return submit_preflight_block(
            "SUBMIT_FAILED_CANDIDATE",
            "Alpha is already marked failed or rejected and cannot be submitted.",
            action="Review or regenerate the failed alpha before submitting.",
        )

    records = ledger_factory(run_config.ops.storage_dir).records()
    candidate_expr_key = expression_key(str(candidate.get("expression", "")))
    duplicate_id = any(str(row.get("official_alpha_id") or "") == official_id for row in records)
    duplicate_expr = bool(candidate_expr_key) and any(expression_key(str(row.get("expression", ""))) == candidate_expr_key for row in records)
    if duplicate_id:
        return submit_preflight_block(
            "SUBMIT_DUPLICATE_OFFICIAL_ID",
            "Local submission history already contains this official Alpha ID.",
            category="conflict",
            action="Select a different official alpha or clear intentional duplicates manually.",
        )
    if duplicate_expr:
        return submit_preflight_block(
            "SUBMIT_DUPLICATE_EXPRESSION",
            "Local submission history already contains the same expression.",
            category="conflict",
            action="Generate or select a materially different expression before submitting.",
        )

    cloud_snapshot = cloud_alpha_snapshot(limit=2000)
    cloud_rows = cloud_snapshot.get("alphas") or []
    cloud_summary = cloud_snapshot.get("summary") or {}
    if run_config.ops.budget.require_cloud_sync:
        if not cloud_rows:
            return submit_preflight_block(
                "SUBMIT_CLOUD_SYNC_REQUIRED",
                "Cloud data must be synced before submission.",
                category="conflict",
                action="Run cloud sync before submitting.",
            )
        if cloud_summary.get("is_stale"):
            return submit_preflight_block(
                "SUBMIT_CLOUD_SYNC_STALE",
                "Cloud data is stale; refresh cloud sync before submission.",
                category="conflict",
                action="Refresh cloud sync before submitting.",
            )

    cloud_status = cloud_status_for(candidate, cloud_rows)
    if str(cloud_status.get("status", "")).upper() in {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}:
        return submit_preflight_block(
            "SUBMIT_CLOUD_ALREADY_SUBMITTED",
            "Cloud cache shows this Alpha is already submitted.",
            category="conflict",
            action="Do not resubmit an alpha already submitted in cloud state.",
        )
    return {"ok": True}


def observability_submission_preflight(
    storage_dir: str,
    *,
    limit: int = 5000,
    top_n: int = 5,
    observability_builder: ObservabilityBuilder = build_research_observability_snapshot,
    safe_error_message: SafeErrorMessage = str,
) -> dict[str, Any]:
    try:
        snapshot = observability_builder(
            storage_dir,
            limit=limit,
            top_n=top_n,
            include_cloud=True,
        )
    except Exception as exc:
        return {
            "ok": False,
            "schema_version": "submission_observability_preflight.v1",
            "risk_level": "unknown",
            "health_flags": ["observability_preflight_unavailable"],
            "blocking_flags": ["observability_preflight_unavailable"],
            "warning_flags": ["observability_preflight_unavailable"],
            "actions": ["Review local observability errors before submission or confirm the risk explicitly."],
            "requires_confirmation": True,
            "error": safe_error_message(exc),
        }
    health = snapshot.get("health") if isinstance(snapshot.get("health"), dict) else {}
    official_call_guard = snapshot.get("official_call_guard") if isinstance(snapshot.get("official_call_guard"), dict) else {}
    blocking_flags = [str(item) for item in health.get("blocking_flags") or [] if str(item)]
    warning_flags = [str(item) for item in health.get("warning_flags") or [] if str(item)]
    health_flags = [str(item) for item in health.get("health_flags") or [] if str(item)]
    actions = [str(item) for item in health.get("actions") or [] if str(item)]
    risk_level = str(health.get("risk_level") or "unknown")
    return {
        "ok": True,
        "schema_version": "submission_observability_preflight.v1",
        "risk_level": risk_level,
        "health_flags": health_flags,
        "blocking_flags": blocking_flags,
        "warning_flags": warning_flags,
        "actions": actions,
        "requires_confirmation": bool(blocking_flags),
        "official_call_guard": official_call_guard,
        "source_schema_version": snapshot.get("schema_version", ""),
        "generated_at": snapshot.get("generated_at", ""),
    }

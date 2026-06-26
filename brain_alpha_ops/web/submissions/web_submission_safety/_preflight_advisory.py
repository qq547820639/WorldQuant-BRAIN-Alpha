"""Comprehensive submission preflight advisory (dict-valued).

Extracted from the former ``web_submission_safety.py`` monolith
(deep-optimization-phase13). Bundles the advisory builder together with
its private helpers that look up the latest check result and assemble
the cloud self-correlation blocking payload.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from brain_alpha_ops.brain_api.official_helpers import looks_non_production_alpha_id
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.safety import SubmissionLedger
from brain_alpha_ops.scoring.release_score_gate import evaluate_release_score
from brain_alpha_ops.submission_readiness import missing_official_metric_fields
from brain_alpha_ops.web_candidates.selection import (
    candidate_official_metrics,
    official_alpha_id,
)
from brain_alpha_ops.web_check_availability import (
    build_cloud_self_correlation_explanation,
)

from ._blocks import (
    CloudAlphaSnapshot,
    CloudStatusFor,
    LedgerFactory,
    submit_preflight_block,
)


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
    metrics = candidate_official_metrics(candidate)
    metrics_official_id = str(metrics.get("official_alpha_id") or "").strip()
    if looks_non_production_alpha_id(official_id) or looks_non_production_alpha_id(metrics_official_id):
        return submit_preflight_block(
            "NON_PRODUCTION_ALPHA_ID",
            "Official Alpha ID looks like a mock, stub, or test identifier.",
            action="Run a real official simulation and select its official Alpha ID before submitting.",
            reasons=["official_alpha_id_non_production"],
        )
    if not metrics:
        return submit_preflight_block(
            "MISSING_OFFICIAL_METRICS",
            "Official metrics are required before production submit.",
            action="Run official simulation/check and refresh submit readiness before submitting.",
        )
    if str(metrics.get("pass_fail") or "").upper() != "PASS":
        return submit_preflight_block(
            "OFFICIAL_ALPHA_CHECK_NOT_PASS",
            "Official alpha check did not return PASS.",
            action="Fix the Alpha and rerun official checks before submitting.",
        )
    missing_fields = missing_official_metric_fields(metrics)
    if missing_fields:
        return submit_preflight_block(
            "MISSING_OFFICIAL_METRIC_FIELDS",
            "Official metrics are incomplete for production submit.",
            action="Run official simulation/check and refresh submit readiness before submitting.",
            missing_fields=missing_fields,
        )
    release_gate = evaluate_release_score(metrics, run_config.ops.thresholds, settings=run_config.ops.settings).to_dict()
    if release_gate.get("status") == "FAIL":
        failed_attributions = [
            row
            for row in release_gate.get("attributions") or []
            if isinstance(row, dict) and row.get("passed") is False and row.get("severity") == "ERROR"
        ]
        return submit_preflight_block(
            "OFFICIAL_RELEASE_GATE_FAILED",
            "Official release gate failed for production submit.",
            action="Fix the Alpha and rerun official checks before submitting.",
            release_gate=release_gate,
            reasons=[str(row.get("name") or "official_release_gate_failed") for row in failed_attributions],
        )
    scorecard = candidate.get("scorecard") if isinstance(candidate.get("scorecard"), dict) else {}
    if str(scorecard.get("decision_band") or "") != "submit_candidate":
        return submit_preflight_block(
            "SUBMIT_DECISION_BAND_NOT_READY",
            "Scorecard decision band is not submit_candidate.",
            action="Improve the Alpha until the scoring gate reaches submit_candidate.",
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

    latest_check = _latest_check_result_for_candidate(run_config.ops.storage_dir, candidate)
    cloud_self_block = _cloud_self_correlation_submit_block(candidate, latest_check)
    if cloud_self_block:
        return cloud_self_block

    cloud_snapshot = cloud_alpha_snapshot()
    cloud_rows = cloud_snapshot.get("alphas") or []
    cloud_summary = cloud_snapshot.get("summary") or {}
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


def _latest_check_result_for_candidate(storage_dir: str, candidate: dict[str, Any], *, limit: int = 5000) -> dict[str, Any]:
    alpha_id = str(candidate.get("alpha_id") or "")
    official_id = official_alpha_id(candidate)
    candidate_expr_key = expression_key(str(candidate.get("expression", "")))
    latest: dict[str, Any] = {}
    for row in read_jsonl_tail(Path(storage_dir) / "checks.jsonl", limit=limit):
        if not isinstance(row, dict):
            continue
        row_alpha_id = str(row.get("alpha_id") or "")
        row_official_id = str(row.get("official_alpha_id") or "")
        row_expr_key = expression_key(str(row.get("expression", "")))
        matches = (
            bool(alpha_id and row_alpha_id == alpha_id)
            or bool(official_id and row_official_id == official_id)
            or bool(candidate_expr_key and row_expr_key == candidate_expr_key)
        )
        if matches:
            latest = row
    return latest


def _cloud_self_correlation_submit_block(candidate: dict[str, Any], check_result: dict[str, Any]) -> dict[str, Any] | None:
    if not check_result:
        return None
    cloud_check_failed = any(
        isinstance(row, dict)
        and str(row.get("name") or "") == "cloud_self_correlation"
        and row.get("passed") is False
        for row in check_result.get("checks") or []
    )
    cloud_risk = check_result.get("cloud_correlation_risk") if isinstance(check_result.get("cloud_correlation_risk"), dict) else {}
    if not cloud_check_failed and str(cloud_risk.get("level") or "").lower() != "high":
        return None
    explanation = build_cloud_self_correlation_explanation(
        {**candidate, "official_alpha_id": official_alpha_id(candidate)},
        cloud_risk,
        check_context={
            "checked_at": check_result.get("checked_at", ""),
            "check_status": check_result.get("status", ""),
            "is_stale": check_result.get("is_stale"),
        },
    )
    return submit_preflight_block(
        "SUBMIT_CLOUD_SELF_CORRELATION_BLOCKED",
        explanation["summary"],
        category="risk",
        action="Refresh cloud data, diversify the expression, then rerun official checks before submitting.",
        risk_explanation=explanation,
        risk_explanations=[explanation],
        state_navigation=explanation.get("navigation"),
        check_result={
            "alpha_id": check_result.get("alpha_id", ""),
            "official_alpha_id": check_result.get("official_alpha_id", ""),
            "checked_at": check_result.get("checked_at", ""),
            "status": check_result.get("status", ""),
            "is_stale": check_result.get("is_stale"),
        },
    )

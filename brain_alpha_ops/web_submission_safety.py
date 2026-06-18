"""Submission safety preflight services for the local web console."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.brain_api.official_helpers import looks_non_production_alpha_id
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger
from brain_alpha_ops.scoring.release_score_gate import evaluate_release_score
from brain_alpha_ops.submission_readiness import missing_official_metric_fields
from brain_alpha_ops.web_candidates.selection import (
    candidate_official_metrics,
    official_alpha_id,
)
from brain_alpha_ops.web_check_availability import (
    build_cloud_self_correlation_explanation,
    build_context_health_explanation,
)
from brain_alpha_ops.web_cloud_snapshot import (
    dedupe_cloud_alpha_rows,
    extract_alpha_rows,
)
from brain_alpha_ops.web_post_handlers import save_assistant_guidance_post_payload

LedgerFactory = Callable[[str], SubmissionLedger]
CloudAlphaSnapshot = Callable[..., dict[str, Any]]
CloudStatusFor = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]]
ObservabilityBuilder = Callable[..., dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]
RepositoryFactory = Callable[[str], ResearchRepository]

logger = logging.getLogger(__name__)


def submit_preflight_block(
    error_code: str,
    error: str,
    *,
    category: str = "validation",
    action: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error_code": error_code, "error_category": category, "error": error}
    if action:
        payload["action"] = action
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


submission_preflight_block = submit_preflight_block


def submission_preflight_error_message(
    candidate: dict[str, Any],
    run_config: RunConfig,
    *,
    ledger_factory: LedgerFactory = SubmissionLedger,
    cloud_alpha_snapshot: CloudAlphaSnapshot,
    cloud_status_for: CloudStatusFor,
) -> str:
    official_id = official_alpha_id(candidate)
    if not official_id:
        return "缺少官方 Alpha ID，请先完成官方回测。"
    gate = candidate.get("gate") or {}
    if not (gate.get("submission_ready") or candidate.get("lifecycle_status") == "submission_ready"):
        return "该 Alpha 尚未达到可提交状态，请先在达标列表完成检查。"
    status_text = f"{candidate.get('lifecycle_status', '')} {gate.get('status', '')}".lower()
    if any(word in status_text for word in ("failed", "rejected", "不达标")):
        return "该 Alpha 已标记为失败或不达标，不能提交。"

    records = ledger_factory(run_config.ops.storage_dir).records()
    candidate_expr_key = expression_key(str(candidate.get("expression", "")))
    duplicate_id = any(str(row.get("official_alpha_id") or "") == official_id for row in records)
    duplicate_expr = bool(candidate_expr_key) and any(expression_key(str(row.get("expression", ""))) == candidate_expr_key for row in records)
    if duplicate_id:
        return "本地提交记录中已存在该官方 Alpha ID。"
    if duplicate_expr:
        return "本地提交记录中已存在相同表达式。"

    cloud_snapshot = cloud_alpha_snapshot()
    cloud_rows = cloud_snapshot.get("alphas") or []
    cloud_summary = cloud_snapshot.get("summary") or {}
    if not cloud_rows:
        return "提交前请先同步云端数据。"
    if cloud_summary.get("is_stale"):
        return "云端数据已超过 24 小时未刷新，请先同步云端数据。"

    cloud_status = cloud_status_for(candidate, cloud_rows)
    if str(cloud_status.get("status", "")).upper() in {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}:
        return "云端缓存显示该 Alpha 已提交。"
    return ""


# P3-1: removed the legacy alias ``submission_preflight_error`` (now only
# the canonical ``submission_preflight_error_message`` is exported).  All
# in-tree callers were updated to the canonical name.


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


def observability_submission_preflight(
    storage_dir: str,
    *,
    limit: int = 5000,
    top_n: int = 5,
    observability_builder: ObservabilityBuilder = build_research_observability_snapshot,
    safe_error_message: SafeErrorMessage = str,
) -> dict[str, Any]:
    try:
        snapshot = observability_builder(storage_dir, limit=limit, top_n=top_n, include_cloud=True)
    except Exception as exc:
        fallback_explanation = build_context_health_explanation({
            "risk_level": "unknown",
            "health_flags": ["observability_preflight_unavailable"],
            "blocking_flags": ["observability_preflight_unavailable"],
            "warning_flags": ["observability_preflight_unavailable"],
            "actions": ["Review local observability errors before submission or confirm the risk explicitly."],
        })
        return {
            "ok": False,
            "schema_version": "submission_observability_preflight.v1",
            "risk_level": "unknown",
            "health_flags": ["observability_preflight_unavailable"],
            "blocking_flags": ["observability_preflight_unavailable"],
            "warning_flags": ["observability_preflight_unavailable"],
            "actions": ["Review local observability errors before submission or confirm the risk explicitly."],
            "risk_explanation": fallback_explanation,
            "state_navigation": fallback_explanation.get("navigation"),
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
    flag_details = health.get("flag_details") if isinstance(health.get("flag_details"), dict) else {}
    context_explanation = build_context_health_explanation({
        "risk_level": risk_level,
        "health_flags": health_flags,
        "blocking_flags": blocking_flags,
        "warning_flags": warning_flags,
        "actions": actions,
        "flag_details": flag_details,
        "source_schema_version": snapshot.get("schema_version", ""),
        "generated_at": snapshot.get("generated_at", ""),
    })
    return {
        "ok": True,
        "schema_version": "submission_observability_preflight.v1",
        "risk_level": risk_level,
        "health_flags": health_flags,
        "blocking_flags": blocking_flags,
        "warning_flags": warning_flags,
        "actions": actions,
        "flag_details": flag_details,
        "risk_explanation": context_explanation if blocking_flags or warning_flags else {},
        "state_navigation": context_explanation.get("navigation") if blocking_flags else {},
        "requires_confirmation": bool(blocking_flags),
        "official_call_guard": official_call_guard,
        "source_schema_version": snapshot.get("schema_version", ""),
        "generated_at": snapshot.get("generated_at", ""),
    }


def record_submit_blocked_event(
    payload: dict[str, Any],
    candidate: dict[str, Any],
    run_config: RunConfig,
    failure_reason: str,
    *,
    repository_factory: RepositoryFactory = ResearchRepository,
    log: logging.Logger = logger,
) -> None:
    try:
        repository_factory(run_config.ops.storage_dir).save_lifecycle_record(
            str(payload.get("job_id", "")) or "manual_submit",
            {
                "timestamp": utc_now(),
                "alpha_id": candidate.get("alpha_id", ""),
                "official_alpha_id": official_alpha_id(candidate),
                "simulation_id": candidate.get("simulation_id", ""),
                "stage": "submission_blocked",
                "status": "BLOCKED",
                "family": candidate.get("family", ""),
                "score": (candidate.get("scorecard") or {}).get("total_score", 0.0),
                "expression": candidate.get("expression", ""),
                "submit_trigger": str(payload.get("submit_mode", "manual")),
                "environment": str(run_config.environment),
                "failure_reason": failure_reason,
                "note": failure_reason,
            },
        )
    except OSError as exc:
        log.error(
            "I/O error recording submission blocked for alpha_id=%s reason=%s: %s",
            redact_text(candidate.get("alpha_id", "?"), max_length=64),
            redact_text(failure_reason, max_length=160),
            redact_error_message(exc),
        )
    except Exception as exc:
        log.warning(
            "failed to record submission blocked for alpha_id=%s reason=%s: %s",
            redact_text(candidate.get("alpha_id", "?"), max_length=64),
            redact_text(failure_reason, max_length=160),
            redact_error_message(exc),
        )

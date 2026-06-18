"""Candidate-level readiness assessment helpers for live submit checks.

This module is intentionally local-evidence only. It does not call BRAIN APIs
or infer submit eligibility beyond the official metrics and audit payloads that
are already persisted in the local ledgers.
"""
from __future__ import annotations

from typing import Any

from brain_alpha_ops.brain_api.official_helpers import looks_non_production_alpha_id
from brain_alpha_ops.config import QualityThresholds
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
)
from brain_alpha_ops.scoring.release_score_gate import evaluate_release_score
from brain_alpha_ops.submission_readiness import missing_official_metric_fields
from brain_alpha_ops.web_candidates.audit import (
    SCIENTIFIC_AUDIT_SCHEMA_VERSION,
    scientific_audit_policy_reasons,
)
from brain_alpha_ops.web_candidates.lifecycle_risk import (
    lifecycle_history_requires_rework,
    lifecycle_history_should_archive,
)

FORBIDDEN_SCIENTIFIC_AUDIT_FEEDBACK_SOURCE_TOKENS = (
    "pytest",
    "fixture",
    "fixtures",
    "unit_test",
    "unit-test",
    "test_result",
    "browser_smoke",
    "browser-smoke",
    "vitest",
)

def assess_candidate(
    candidate: dict[str, Any],
    *,
    thresholds: QualityThresholds,
    similarity_threshold: float,
) -> dict[str, Any]:
    metrics = candidate.get("official_metrics") if isinstance(candidate.get("official_metrics"), dict) else {}
    if not metrics and isinstance(candidate.get("metrics"), dict):
        metrics = candidate["metrics"]
    risk = candidate.get("cloud_correlation_risk") if isinstance(candidate.get("cloud_correlation_risk"), dict) else {}
    submission = candidate.get("submission") if isinstance(candidate.get("submission"), dict) else {}
    local_backtest = (
        submission.get("local_backtest")
        if isinstance(submission.get("local_backtest"), dict)
        else {}
    )
    local_backtest_passed = local_backtest.get("pass_local") if local_backtest else None
    max_similarity = float_or_none(risk.get("max_similarity"))
    official_id = str(candidate.get("official_alpha_id") or metrics.get("official_alpha_id") or "")
    pass_fail = str(metrics.get("pass_fail") or "").strip().upper()
    pending_check_names = _string_list(metrics.get("brain_pending_names") or [])
    decision_band = str(
        (candidate.get("scorecard") or {}).get("decision_band")
        or candidate.get("decision_band")
        or ""
    )
    expression = str(candidate.get("expression") or "")
    submission_ready = bool((candidate.get("gate") or {}).get("submission_ready")) or candidate.get(
        "lifecycle_status"
    ) == "submission_ready"
    generation_risks = high_turnover_generation_risk_reasons(expression)
    local_backtest_summary = _local_backtest_summary(local_backtest)
    reasons: list[str] = []
    if not submission_ready:
        reasons.append("not_submission_ready")
    if generation_risks:
        reasons.append("high_turnover_generation_risk")
    if decision_band != "submit_candidate":
        reasons.append("decision_band_not_submit_candidate")
    if local_backtest_passed is False and local_backtest.get("advisory") is not True:
        reasons.append("local_backtest_failed")
    for unsupported_reason in _unsupported_local_backtest_reasons(local_backtest_summary):
        reasons.append(unsupported_reason)
    if not official_id:
        reasons.append("missing_official_alpha_id")
    elif looks_non_production_alpha_id(official_id):
        reasons.append("non_production_official_alpha_id")
    if not metrics or not pass_fail:
        reasons.append("missing_official_metrics")
    elif pass_fail != "PASS":
        reasons.append("official_pass_fail_not_pass")
    missing_metric_fields = missing_official_metric_fields(metrics) if metrics else []
    if metrics and missing_metric_fields:
        reasons.append("missing_official_metric_fields")
    if any(name.upper() == "SELF_CORRELATION" for name in pending_check_names):
        reasons.append("official_self_correlation_pending")
    elif pending_check_names:
        reasons.append("official_checks_pending")
    release_gate = evaluate_release_score(metrics, thresholds, settings=_candidate_settings(candidate)).to_dict() if metrics else {}
    for reason in _release_gate_blocking_reasons(release_gate):
        if reason not in reasons:
            reasons.append(reason)
    lifecycle_reasons = lifecycle_readiness_blocking_reasons(candidate)
    for reason in lifecycle_reasons:
        if reason not in reasons:
            reasons.append(reason)
    if max_similarity is None:
        reasons.append("missing_cloud_similarity")
    elif max_similarity >= similarity_threshold or str(risk.get("level") or "").lower() == "high":
        reasons.append("high_cloud_similarity")
    scientific_reasons = scientific_audit_readiness_blocking_reasons(candidate, require_presence=not reasons)
    for reason in scientific_reasons:
        if reason not in reasons:
            reasons.append(reason)
    eligible = not reasons
    return {
        "alpha_id": str(candidate.get("alpha_id") or ""),
        "official_alpha_id": official_id,
        "expression": expression,
        "generation_risk_reasons": generation_risks,
        "lifecycle_status": str(candidate.get("lifecycle_status") or ""),
        "pass_fail": pass_fail,
        "score": float_or_none((candidate.get("scorecard") or {}).get("total_score") or candidate.get("score")),
        "decision_band": decision_band,
        "local_backtest_passed": local_backtest_passed if isinstance(local_backtest_passed, bool) else None,
        "local_backtest": local_backtest_summary,
        "max_similarity": max_similarity,
        "risk_level": str(risk.get("level") or ""),
        "missing_official_metric_fields": missing_metric_fields,
        "pending_official_checks": pending_check_names,
        "lifecycle_readiness_reasons": lifecycle_reasons,
        "scientific_readiness_reasons": scientific_reasons,
        "official_release_gate": release_gate,
        "eligible": eligible,
        "blocking_reasons": reasons,
    }

def lifecycle_readiness_blocking_reasons(candidate: dict[str, Any]) -> list[str]:
    """Return local lifecycle-history blockers for the final submit stop rule."""

    reasons: list[str] = []
    if lifecycle_history_should_archive(candidate):
        reasons.append("lifecycle_history_blocked")
    if lifecycle_history_requires_rework(candidate):
        reasons.append("lifecycle_history_failed")
    decision = candidate.get("production_decision") if isinstance(candidate.get("production_decision"), dict) else {}
    if decision:
        action = str(decision.get("action") or "").strip()
        blocking = decision.get("blocking") is True
        reason_codes = {
            str(reason or "").strip()
            for reason in decision.get("reason_codes") or []
            if str(reason or "").strip()
        }
        if action == "archive" or blocking:
            if reason_codes & {"lifecycle_history_blocked", "lifecycle_history_failed"}:
                reasons.append("production_decision_lifecycle_blocked")
            elif blocking:
                reasons.append("production_decision_blocked")
    return sorted(set(reasons))

def scientific_audit_readiness_blocking_reasons(
    candidate: dict[str, Any],
    *,
    require_presence: bool,
) -> list[str]:
    """Return scientific-audit blockers for the final submit stop rule.

    Missing, invalid, or incomplete audit evidence blocks only otherwise-ready
    candidates to keep early-stage diagnostics readable. Unsafe evidence is
    always reported because it is a hard anti-overfitting/non-submit boundary.
    """

    audits = _scientific_audits(candidate)
    if not audits:
        return ["missing_scientific_audit"] if require_presence else []

    reasons: list[str] = []
    for audit in audits:
        schema_ok = audit.get("schema_version") == SCIENTIFIC_AUDIT_SCHEMA_VERSION
        if not schema_ok and require_presence:
            reasons = _append_unique(reasons, "invalid_scientific_audit_schema")

        anti = audit.get("anti_overfit") if isinstance(audit.get("anti_overfit"), dict) else {}
        evidence = audit.get("evidence") if isinstance(audit.get("evidence"), dict) else {}
        boundary = audit.get("safety_boundary") if isinstance(audit.get("safety_boundary"), dict) else {}
        # Treat every persisted audit payload as submission-stop evidence. A
        # safe top-level copy must not hide an unsafe nested copy from an older
        # merge or writeback path.
        if schema_ok and require_presence and not (anti and evidence and boundary):
            reasons = _append_unique(reasons, "incomplete_scientific_audit")

        if anti.get("test_script_outcomes_used") is True or anti.get("test_feedback_allowed") is True:
            reasons = _append_unique(reasons, "scientific_audit_test_feedback_used")
        for source in evidence.get("feedback_sources") or []:
            normalized = str(source or "").strip().lower()
            if any(token in normalized for token in FORBIDDEN_SCIENTIFIC_AUDIT_FEEDBACK_SOURCE_TOKENS):
                reasons = _append_unique(reasons, "scientific_audit_test_feedback_used")
        for reason in scientific_audit_policy_reasons({"scientific_audit": audit}):
            reasons = _append_unique(reasons, reason)

        explainability = audit.get("explainability") if isinstance(audit.get("explainability"), dict) else {}
        optimization = (
            explainability.get("optimization_explanation")
            if isinstance(explainability.get("optimization_explanation"), dict)
            else {}
        )
        official_context = optimization.get("official_context") if isinstance(optimization.get("official_context"), dict) else {}
        official_proof = (
            explainability.get("official_context_proof")
            if isinstance(explainability.get("official_context_proof"), dict)
            else {}
        )
        if official_context.get("passed") is False or official_proof.get("passed") is False:
            reasons = _append_unique(reasons, "official_context_proof_failed")
    return reasons

def best_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {}
    return sorted(candidates, key=_best_candidate_rank, reverse=True)[0]

def has_unsupported_local_backtest(candidate: dict[str, Any]) -> bool:
    reasons = {str(reason) for reason in candidate.get("blocking_reasons") or [] if str(reason)}
    return bool(reasons & {"unsupported_local_backtest_fields", "unsupported_local_backtest_operators"})

def has_hard_local_backtest_block(candidate: dict[str, Any]) -> bool:
    reasons = {str(reason) for reason in candidate.get("blocking_reasons") or [] if str(reason)}
    return "local_backtest_failed" in reasons

def scientific_audit_gap_messages() -> dict[str, str]:
    return {
        "missing_scientific_audit": "lacks scientific audit evidence",
        "invalid_scientific_audit_schema": "has an invalid scientific audit schema",
        "incomplete_scientific_audit": "has incomplete scientific audit evidence",
        "scientific_audit_test_feedback_used": "scientific audit includes test feedback",
        "scientific_audit_submit_boundary_breached": "scientific audit breached the non-submit boundary",
        "official_context_proof_failed": "scientific audit official-context proof failed",
    }

def _scientific_audits(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    direct = candidate.get("scientific_audit")
    if isinstance(direct, dict):
        audits.append(direct)
    extra_fields = candidate.get("extra_fields") if isinstance(candidate.get("extra_fields"), dict) else {}
    nested = extra_fields.get("scientific_audit")
    if isinstance(nested, dict):
        audits.append(nested)
    return audits

def _candidate_settings(candidate: dict[str, Any]) -> dict[str, Any]:
    settings = candidate.get("settings") if isinstance(candidate.get("settings"), dict) else {}
    submission = candidate.get("submission") if isinstance(candidate.get("submission"), dict) else {}
    submission_settings = submission.get("settings") if isinstance(submission.get("settings"), dict) else {}
    metrics = candidate.get("official_metrics") if isinstance(candidate.get("official_metrics"), dict) else {}
    if settings:
        return settings
    if submission_settings:
        return submission_settings
    if "delay" in metrics:
        return {"delay": metrics.get("delay")}
    return {}

def _local_backtest_summary(local_backtest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(local_backtest, dict) or not local_backtest:
        return {}

    reasons = _string_list(local_backtest.get("pass_reasons") or local_backtest.get("reasons"))
    failing_reasons = [
        reason for reason in reasons
        if "FAIL" in reason.upper() or "ERROR" in reason.upper() or "REJECT" in reason.upper()
    ]
    return {
        "pass_local": local_backtest.get("pass_local") if isinstance(local_backtest.get("pass_local"), bool) else None,
        "advisory": local_backtest.get("advisory") if isinstance(local_backtest.get("advisory"), bool) else None,
        "sharpe": float_or_none(local_backtest.get("sharpe")),
        "fitness": float_or_none(local_backtest.get("fitness")),
        "turnover": float_or_none(local_backtest.get("turnover")),
        "weight_concentration": float_or_none(local_backtest.get("weight_concentration")),
        "failing_reasons": failing_reasons[:8],
        "reasons": reasons[:8],
    }

def _unsupported_local_backtest_reasons(local_backtest: dict[str, Any]) -> list[str]:
    reasons = _string_list(local_backtest.get("reasons"))
    reasons.extend(_string_list(local_backtest.get("failing_reasons")))
    blockers: list[str] = []
    if any("unsupported_fields=" in reason for reason in reasons):
        blockers.append("unsupported_local_backtest_fields")
    if any("unsupported_operators=" in reason for reason in reasons):
        blockers.append("unsupported_local_backtest_operators")
    return blockers

def _release_gate_blocking_reasons(release_gate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for item in release_gate.get("attributions") or []:
        if not isinstance(item, dict):
            continue
        if item.get("passed") or item.get("severity") != "ERROR":
            continue
        reason = _release_gate_reason(str(item.get("name") or ""))
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons

def _release_gate_reason(name: str) -> str:
    return {
        "sharpe": "official_sharpe_below_threshold",
        "fitness": "official_fitness_below_threshold",
        "turnover_cap": "official_turnover_above_threshold",
        "self_correlation_cap": "official_self_correlation_above_threshold",
        "prod_correlation_cap": "official_prod_correlation_above_threshold",
        "weight_concentration_cap": "official_weight_concentration_above_threshold",
        "sub_universe_sharpe": "official_sub_universe_sharpe_below_threshold",
    }.get(name, "")

def _best_candidate_rank(candidate: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, float]:
    reasons = {str(reason) for reason in candidate.get("blocking_reasons") or [] if str(reason)}
    score = float_or_none(candidate.get("score")) or 0.0
    return (
        1 if candidate.get("eligible") is True else 0,
        1 if candidate.get("decision_band") == "submit_candidate" else 0,
        0 if has_unsupported_local_backtest(candidate) else 1,
        0 if has_hard_local_backtest_block(candidate) else 1,
        0 if "high_turnover_generation_risk" in reasons else 1,
        0 if "high_cloud_similarity" in reasons else 1,
        -len(reasons),
        score,
    )

def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result

def _append_unique(items: list[str], value: str) -> list[str]:
    text = str(value).strip()
    if text and text not in items:
        items.append(text)
    return items

def float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

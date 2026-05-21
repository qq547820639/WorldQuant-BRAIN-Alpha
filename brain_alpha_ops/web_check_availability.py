"""Candidate availability checks for pre-submit web flows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.safety import similarity
from brain_alpha_ops.web_candidate_selection import is_passed_candidate_for_check, official_alpha_id
from brain_alpha_ops.web_risk_guidance import (
    build_cloud_self_correlation_explanation,
    build_context_health_explanation,
    build_state_navigation,
)


SafeErrorMessage = Callable[[Exception], str]
ObservabilityPreflight = Callable[[str], dict[str, Any]]


CHECK_LABELS: dict[str, tuple[str, str]] = {
    "production_gate": ("Production gate", "Confirm the alpha passed all quality gates."),
    "official_alpha_id": ("Official Alpha ID", "Run an official simulation to obtain an official alpha ID."),
    "not_failed_locally": ("Local lifecycle", "Use candidates not marked failed or rejected."),
    "cloud_sync_available": ("Cloud sync", "Run cloud sync before submitting."),
    "not_submitted_before": ("Local duplicate", "Check local submission history."),
    "cloud_status_not_already_submitted": ("Cloud status", "Do not resubmit active or submitted cloud alphas."),
    "cloud_self_correlation": ("Cloud self-correlation", "Reduce similarity to existing cloud alphas."),
    "context_health_preflight": ("Context health", "Resolve blocking context-health flags before official checks."),
    "official_pre_submit_check": ("Official pre-submit check", "Run the official pre-submit check."),
}


def check_candidate_availability(
    candidate: dict[str, Any],
    mode: str,
    api: Any,
    ledger: Any,
    cloud_alphas: list[dict[str, Any]],
    cloud_error: str = "",
    observability_preflight: dict[str, Any] | None = None,
    *,
    safe_error_message: SafeErrorMessage,
    observability_submission_preflight: ObservabilityPreflight,
) -> dict[str, Any]:
    official_id = official_alpha_id(candidate)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str, **extra: Any) -> None:
        label, suggestion = CHECK_LABELS.get(name, (name, "Review this check before submitting."))
        row = {
            "name": name,
            "label_cn": label,
            "passed": bool(passed),
            "detail": detail,
            "suggestion": suggestion if not passed else "",
        }
        row.update({key: value for key, value in extra.items() if value is not None})
        checks.append(row)

    gate = candidate.get("gate") or {}
    status_text = f"{candidate.get('lifecycle_status', '')} {gate.get('status', '')}".lower()
    add("production_gate", is_passed_candidate_for_check(candidate), gate.get("status", ""))
    add("official_alpha_id", bool(official_id), official_id or "missing official alpha id")
    add("not_failed_locally", not any(word in status_text for word in ("failed", "rejected", "not_passed")), candidate.get("lifecycle_status", ""))
    add("cloud_sync_available", not cloud_error, cloud_error or f"{len(cloud_alphas)} cloud alphas loaded")

    records = ledger.records()
    duplicate_id = official_id and any(row.get("official_alpha_id") == official_id for row in records)
    candidate_expr_key = expression_key(str(candidate.get("expression", "")))
    duplicate_expr = bool(candidate_expr_key) and any(expression_key(str(row.get("expression", ""))) == candidate_expr_key for row in records)
    add("not_submitted_before", not duplicate_id and not duplicate_expr, "duplicate local submission record" if (duplicate_id or duplicate_expr) else "new local submission")

    cloud_status = cloud_status_for(candidate, cloud_alphas)
    already_submitted_status = str(cloud_status.get("status", "")).upper() in {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}
    add("cloud_status_not_already_submitted", not already_submitted_status, cloud_status.get("status", "not found"))

    cloud_risk = cloud_similarity_risk(candidate, cloud_alphas)
    observability_preflight = observability_preflight or observability_submission_preflight(str(Path(ledger.path).parent))
    cloud_check_context = _cloud_self_correlation_check_context(observability_preflight)
    cloud_explanation = build_cloud_self_correlation_explanation(candidate, cloud_risk, check_context=cloud_check_context)
    add(
        "cloud_self_correlation",
        cloud_risk["level"] != "high",
        f"{cloud_risk['level']} {cloud_risk['max_similarity']:.4f}",
        risk_explanation=cloud_explanation if cloud_risk["level"] in {"high", "medium"} else None,
        state_navigation=cloud_explanation.get("navigation") if cloud_risk["level"] == "high" else None,
        severity=cloud_explanation.get("severity"),
    )

    context_explanation = build_context_health_explanation(observability_preflight)
    context_blocked = bool(context_explanation.get("blocking_flags"))
    add(
        "context_health_preflight",
        not context_blocked,
        context_explanation.get("summary", ""),
        risk_explanation=context_explanation if context_blocked else None,
        state_navigation=context_explanation.get("navigation") if context_blocked else None,
        severity=context_explanation.get("severity"),
    )

    official_check_passed = False
    local_preflight_passed = all(row["passed"] for row in checks)
    if official_id and local_preflight_passed:
        try:
            official_check = api.check_alpha(official_id)
        except Exception as exc:
            add("official_pre_submit_check", False, safe_error_message(exc))
        else:
            official_check_passed = official_check.get("status") == "PASSED"
            add("official_pre_submit_check", official_check_passed, official_check.get("status", ""))
    elif official_id:
        add(
            "official_pre_submit_check",
            False,
            "Skipped because local/context preflight blocked before an official call.",
            state_navigation=build_state_navigation(
                "LOCAL_PREFLIGHT_BLOCKED",
                title="先处理本地前置阻断",
                summary="本地检查或上下文健康已阻断，暂不调用官方预提交检查。",
                target_view="passed",
                primary_action="解决阻断项后重新检查。",
            ),
        )

    passed = all(row["passed"] for row in checks)
    submittable = passed and official_check_passed
    score = float((candidate.get("scorecard") or {}).get("total_score", 0.0) or 0.0)
    if cloud_risk["level"] == "high":
        score -= 40
    elif cloud_risk["level"] == "medium":
        score -= 12
    failed_reasons = [row["detail"] or row["name"] for row in checks if not row["passed"]]
    risk_explanations = [row["risk_explanation"] for row in checks if not row["passed"] and isinstance(row.get("risk_explanation"), dict)]
    state_navigation = next((row.get("state_navigation") for row in checks if not row["passed"] and isinstance(row.get("state_navigation"), dict)), {})
    return {
        "ok": True,
        "alpha_id": candidate.get("alpha_id", ""),
        "official_alpha_id": official_id,
        "mode": mode,
        "passed": passed,
        "submittable": submittable,
        "local_preflight_passed": local_preflight_passed,
        "requires_official_check": local_preflight_passed and not submittable,
        "status": "SUBMITTABLE" if submittable else "CHECK_PASSED_NEEDS_OFFICIAL" if local_preflight_passed else "BLOCKED",
        "score": round(score, 2),
        "checked_at": utc_now(),
        "is_stale": False,
        "checks": checks,
        "failed_reasons": failed_reasons,
        "risk_explanations": risk_explanations,
        "state_navigation": state_navigation,
        "cloud_correlation_risk": cloud_risk,
        "cloud_status": cloud_status,
        "context_health": context_explanation,
        "observability_preflight": observability_preflight,
    }


def _cloud_self_correlation_check_context(observability_preflight: dict[str, Any]) -> dict[str, Any]:
    details = observability_preflight.get("flag_details") if isinstance(observability_preflight.get("flag_details"), dict) else {}
    saturation = details.get("cloud_self_correlation_saturation") if isinstance(details.get("cloud_self_correlation_saturation"), dict) else {}
    evidence = saturation.get("evidence") if isinstance(saturation.get("evidence"), dict) else {}
    if not evidence:
        return {}
    return {
        "recent_check_count": evidence.get("check_total", 0),
        "blocked_count": evidence.get("blocked_count", 0),
        "cloud_self_correlation_failed_count": evidence.get("cloud_self_correlation_failed_count", 0),
        "cloud_self_correlation_block_rate": evidence.get("cloud_self_correlation_block_rate", 0.0),
    }


def cloud_status_for(candidate: dict[str, Any], cloud_alphas: list[dict[str, Any]]) -> dict[str, str]:
    official_id = official_alpha_id(candidate)
    candidate_expr_key = expression_key(str(candidate.get("expression", "")))
    for row in cloud_alphas:
        row_id = str(row.get("id") or row.get("alpha_id") or "")
        if official_id and row_id == official_id:
            return {"id": row_id, "status": str(row.get("status", "")), "match": "official_id"}
    for row in cloud_alphas:
        if candidate_expr_key and expression_key(cloud_row_expression(row)) == candidate_expr_key:
            return {"id": str(row.get("id") or row.get("alpha_id") or ""), "status": str(row.get("status", "")), "match": "expression"}
    return {"id": "", "status": "", "match": "none"}


def cloud_similarity_risk(candidate: dict[str, Any], cloud_alphas: list[dict[str, Any]]) -> dict[str, Any]:
    official_id = official_alpha_id(candidate)
    best = {"score": 0.0, "id": "", "status": ""}
    for row in cloud_alphas:
        row_id = str(row.get("id") or row.get("alpha_id") or "")
        if official_id and row_id == official_id:
            continue
        expr = cloud_row_expression(row)
        score = similarity(str(candidate.get("expression", "")), expr)
        if score > best["score"]:
            best = {"score": score, "id": row_id, "status": str(row.get("status", ""))}
    level = "high" if best["score"] >= 0.90 else "medium" if best["score"] >= 0.75 else "low"
    return {"level": level, "max_similarity": best["score"], "matched_alpha_id": best["id"], "matched_status": best["status"]}


def cloud_row_expression(row: dict[str, Any]) -> str:
    expression = row.get("expression", "")
    if isinstance(expression, dict):
        code = expression.get("code") or expression.get("regular")
        if code:
            return str(code)
    regular = row.get("regular")
    if isinstance(regular, dict) and regular.get("code"):
        return str(regular.get("code"))
    raw = row.get("raw")
    if isinstance(raw, dict):
        raw_regular = raw.get("regular")
        if isinstance(raw_regular, dict) and raw_regular.get("code"):
            return str(raw_regular.get("code"))
    return str(expression or "")

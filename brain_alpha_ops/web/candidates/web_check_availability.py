"""Alpha availability checks, batch job results, and risk guidance."""

from __future__ import annotations

from typing import Any

CLOUD_SELF_CORRELATION_THRESHOLD = 0.90
CLOUD_SELF_CORRELATION_WARNING_THRESHOLD = 0.75


def build_state_navigation(
    reason_code: str,
    *,
    title: str = "",
    summary: str = "",
    target_view: str = "passed",
    primary_action: str = "",
    steps: list[dict[str, Any]] | None = None,
    state: str = "blocked",
) -> dict[str, Any]:
    """Return a UI-friendly abnormal-state navigation payload."""

    return {
        "schema_version": "abnormal_state_navigation.v1",
        "state": state,
        "reason_code": reason_code,
        "title": title or "Submission is blocked",
        "summary": summary,
        "target_view": target_view,
        "primary_action": primary_action or "Review the blocking checks before retrying.",
        "steps": steps or _default_resolution_steps(reason_code),
    }


def build_cloud_self_correlation_explanation(
    candidate: dict[str, Any] | None,
    cloud_risk: dict[str, Any] | None,
    *,
    check_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explain why cloud_self_correlation blocks submission."""

    candidate = candidate or {}
    cloud_risk = cloud_risk or {}
    value = _float(cloud_risk.get("max_similarity"))
    level = str(cloud_risk.get("level") or _risk_level(value))
    severity = "blocking" if level == "high" or value >= CLOUD_SELF_CORRELATION_THRESHOLD else "warning" if level == "medium" else "info"
    matched_alpha_id = str(cloud_risk.get("matched_alpha_id") or "")
    matched_status = str(cloud_risk.get("matched_status") or "")
    percent = round(value * 100, 2)
    evidence: dict[str, Any] = {
        "alpha_id": candidate.get("alpha_id", ""),
        "official_alpha_id": candidate.get("official_alpha_id", ""),
        "max_similarity": value,
        "threshold": CLOUD_SELF_CORRELATION_THRESHOLD,
        "matched_alpha_id": matched_alpha_id,
        "matched_status": matched_status,
    }
    if check_context:
        evidence["check_context"] = check_context

    title = "云端自相关风险过高" if severity == "blocking" else "云端自相关风险提示"
    summary = (
        f"当前 Alpha 与云端已有 Alpha 的最高相似度为 {percent:.2f}%，"
        f"已达到 {CLOUD_SELF_CORRELATION_THRESHOLD * 100:.0f}% 的提交阻断阈值。"
        if severity == "blocking"
        else f"当前 Alpha 与云端已有 Alpha 的最高相似度为 {percent:.2f}%，接近提交风险区间。"
    )
    reasons = [
        "cloud_self_correlation 是官方提交前检查的硬风险项，命中后本地达标不能直接等价为可提交。",
        "该规则通常说明表达式结构、字段组合或收益形态与云端历史 Alpha 过于接近。",
        "继续提交大概率会被官方检查拦截，并消耗一次提交/检查路径的注意力成本。",
    ]
    if matched_alpha_id:
        reasons.insert(1, f"最相似的云端 Alpha 为 {matched_alpha_id}，状态为 {matched_status or 'unknown'}。")
    if check_context and _int(check_context.get("cloud_self_correlation_failed_count")):
        failed = _int(check_context.get("cloud_self_correlation_failed_count"))
        total = _int(check_context.get("recent_check_count"))
        if total:
            reasons.append(f"最近 {total} 条检查中有 {failed} 条被该规则阻断，说明当前上下文存在系统性相似度风险。")

    actions = [
        "先刷新云端 Alpha 缓存，确认相似对象和状态仍然有效。",
        "调整核心表达式而不是只改常数：更换字段、窗口、分组或 neutralization 组合。",
        "重新运行快速/全部检查，只有 cloud_self_correlation 解除后再进入提交队列。",
    ]
    return {
        "schema_version": "submit_risk_explanation.v1",
        "rule": "cloud_self_correlation",
        "severity": severity,
        "level": level,
        "title": title,
        "summary": summary,
        "reasons": reasons,
        "recommended_actions": actions,
        "evidence": evidence,
        "visual": {
            "kind": "similarity_meter",
            "value": value,
            "threshold": CLOUD_SELF_CORRELATION_THRESHOLD,
            "warning_threshold": CLOUD_SELF_CORRELATION_WARNING_THRESHOLD,
            "unit": "ratio",
            "label": "Cloud similarity",
        },
        "navigation": build_state_navigation(
            "CLOUD_SELF_CORRELATION_BLOCKED",
            title="先解除云端自相关阻断",
            summary="按云端缓存、表达式差异化、重新检查的顺序处理，避免在提交入口反复失败。",
            target_view="passed",
            primary_action="刷新云端数据并重新检查该 Alpha。",
            steps=[
                {"id": "inspect_rule", "label": "查看阻断原因", "status": "active", "view": "passed"},
                {"id": "refresh_cloud", "label": "刷新云端数据", "status": "pending", "view": "cloud"},
                {"id": "diversify_expression", "label": "调整表达式差异", "status": "pending", "view": "candidates"},
                {"id": "rerun_check", "label": "重新执行检查", "status": "pending", "view": "passed"},
            ],
        ),
    }


def build_context_health_explanation(preflight: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize observability/context health into a check-stage risk payload."""

    preflight = preflight or {}
    blocking_flags = [str(item) for item in preflight.get("blocking_flags") or [] if str(item)]
    warning_flags = [str(item) for item in preflight.get("warning_flags") or [] if str(item)]
    health_flags = [str(item) for item in preflight.get("health_flags") or [] if str(item)]
    flag_details = preflight.get("flag_details") if isinstance(preflight.get("flag_details"), dict) else {}
    primary_flags = blocking_flags or warning_flags or health_flags
    severity = "blocking" if blocking_flags else "warning" if warning_flags else "info"
    summary = (
        "上下文健康检查发现阻断项：" + ", ".join(blocking_flags[:3])
        if blocking_flags
        else "上下文健康检查发现风险项：" + ", ".join(warning_flags[:3])
        if warning_flags
        else "上下文健康检查未发现阻断项。"
    )
    actions = [str(item) for item in preflight.get("actions") or [] if str(item)]
    if not actions:
        actions = ["继续保持云端缓存和本地检查记录可用。"] if not blocking_flags else ["先处理上下文阻断项，再重试检查/提交。"]
    return {
        "schema_version": "context_health_preflight.v1",
        "rule": "context_health_preflight",
        "severity": severity,
        "title": "上下文健康前置检查",
        "summary": summary,
        "flags": primary_flags,
        "blocking_flags": blocking_flags,
        "warning_flags": warning_flags,
        "recommended_actions": actions,
        "flag_details": flag_details,
        "evidence": {
            "risk_level": preflight.get("risk_level", "unknown"),
            "generated_at": preflight.get("generated_at", ""),
            "source_schema_version": preflight.get("source_schema_version", ""),
        },
        "navigation": build_state_navigation(
            "CONTEXT_HEALTH_BLOCKED" if blocking_flags else "CONTEXT_HEALTH_REVIEW",
            title="先处理上下文健康阻断" if blocking_flags else "检查上下文健康提示",
            summary="把系统性风险前移到检查阶段，避免到提交阶段才发现不可提交。",
            target_view="research_observability",
            primary_action="打开 Observability 查看阻断旗标。" if blocking_flags else "查看 Observability 风险提示。",
            steps=[
                {"id": "open_observability", "label": "查看 Observability", "status": "active", "view": "research_observability"},
                {"id": "fix_context", "label": "处理阻断旗标", "status": "pending", "view": "research_observability"},
                {"id": "rerun_check", "label": "重新执行检查", "status": "pending", "view": "passed"},
            ],
            state="blocked" if blocking_flags else "review",
        ),
    }


def _default_resolution_steps(reason_code: str) -> list[dict[str, Any]]:
    if "CLOUD" in reason_code:
        return [
            {"id": "sync_cloud", "label": "刷新云端数据", "status": "active", "view": "cloud"},
            {"id": "rerun_check", "label": "重新检查", "status": "pending", "view": "passed"},
            {"id": "retry_submit", "label": "再提交", "status": "pending", "view": "submittable"},
        ]
    return [
        {"id": "inspect", "label": "查看原因", "status": "active", "view": "passed"},
        {"id": "fix", "label": "修正问题", "status": "pending", "view": "candidates"},
        {"id": "retry", "label": "重新检查/提交", "status": "pending", "view": "passed"},
    ]


def _risk_level(value: float) -> str:
    if value >= CLOUD_SELF_CORRELATION_THRESHOLD:
        return "high"
    if value >= CLOUD_SELF_CORRELATION_WARNING_THRESHOLD:
        return "medium"
    return "low"


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

"""Candidate availability checks for pre-submit web flows."""

import logging
from pathlib import Path
from typing import Callable

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.safety import similarity
from brain_alpha_ops.submission_readiness import missing_official_metric_fields
from brain_alpha_ops.web_candidates.selection import (
    is_passed_candidate_for_check,
    official_alpha_id,
)
# Phase 3.3: removed redundant self-import of build_* functions
# (already defined above in this module).

SafeErrorMessage = Callable[[Exception], str]
ObservabilityPreflight = Callable[[str], dict[str, Any]]

logger = logging.getLogger(__name__)


CHECK_LABELS: dict[str, tuple[str, str]] = {
    "production_gate": ("Production gate", "Confirm the alpha passed all quality gates."),
    "official_alpha_id": ("Official Alpha ID", "Run an official simulation to obtain an official alpha ID."),
    "official_pass_fail": ("Official Alpha Check", "Run official Alpha Check until pass_fail=PASS."),
    "official_metric_fields_complete": ("Official metrics", "Refresh official simulation metrics before submit."),
    "decision_band_submit_candidate": ("Scoring band", "Optimize the alpha until decision_band=submit_candidate."),
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
    metrics = candidate.get("official_metrics")
    if not isinstance(metrics, dict) or not metrics:
        raw_metrics = candidate.get("metrics")
        metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
    pass_fail = str(metrics.get("pass_fail") or "").strip().upper()
    missing_metric_fields = missing_official_metric_fields(metrics) if metrics else []
    decision_band = _submission_decision_band(candidate)
    add("production_gate", is_passed_candidate_for_check(candidate), gate.get("status", ""))
    add("official_alpha_id", bool(official_id), official_id or "missing official alpha id")
    add("official_pass_fail", pass_fail == "PASS", pass_fail or "missing official pass/fail")
    add(
        "official_metric_fields_complete",
        not missing_metric_fields,
        ", ".join(missing_metric_fields) if missing_metric_fields else "complete official metrics",
        missing_fields=missing_metric_fields or None,
    )
    add(
        "decision_band_submit_candidate",
        decision_band == "submit_candidate",
        decision_band or "missing decision_band",
    )
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
            message = safe_error_message(exc)
            logger.warning(
                "official pre-submit check failed for alpha_id=%s official_alpha_id=%s: %s",
                redact_text(candidate.get("alpha_id", ""), max_length=64),
                redact_text(official_id, max_length=64),
                message,
            )
            add("official_pre_submit_check", False, message)
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
    state_navigation: dict[str, Any] = {}
    for row in checks:
        if row["passed"]:
            continue
        raw_navigation = row.get("state_navigation")
        if isinstance(raw_navigation, dict):
            state_navigation = raw_navigation
            break
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
    raw_details = observability_preflight.get("flag_details")
    details = raw_details if isinstance(raw_details, dict) else {}
    raw_saturation = details.get("cloud_self_correlation_saturation")
    saturation = raw_saturation if isinstance(raw_saturation, dict) else {}
    raw_evidence = saturation.get("evidence")
    evidence = raw_evidence if isinstance(raw_evidence, dict) else {}
    if not evidence:
        return {}
    return {
        "recent_check_count": evidence.get("check_total", 0),
        "blocked_count": evidence.get("blocked_count", 0),
        "cloud_self_correlation_failed_count": evidence.get("cloud_self_correlation_failed_count", 0),
        "cloud_self_correlation_block_rate": evidence.get("cloud_self_correlation_block_rate", 0.0),
    }


def _submission_decision_band(candidate: dict[str, Any]) -> str:
    scorecard = candidate.get("scorecard")
    if isinstance(scorecard, dict) and scorecard.get("decision_band"):
        return str(scorecard.get("decision_band") or "")
    return str(candidate.get("decision_band") or "")


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
    best: dict[str, Any] = {"score": 0.0, "id": "", "status": ""}
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

"""Batch check background job service for the local web console."""

import logging
import time
from collections import Counter
from typing import Any, Callable, Protocol

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger
from brain_alpha_ops.web_candidates.check_evidence import (
    persist_candidate_check_evidence,
)

logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


PassedCandidates = Callable[[dict[str, Any]], list[dict[str, Any]]]
RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ApiFromRunConfig = Callable[[RunConfig], Any]
RepositoryFactory = Callable[[str], ResearchRepository]
LedgerFactory = Callable[[str], SubmissionLedger]
PayloadTruthy = Callable[[object], bool]
RefreshCloudContext = Callable[..., tuple[list[dict[str, Any]], str]]
CheckAvailability = Callable[..., dict[str, Any]]
ObservabilityPreflight = Callable[[str], dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]
ErrorPayload = Callable[..., dict[str, Any]]


def _timing_payload(started_at: float, *, done: int = 0, total: int = 0) -> dict[str, Any]:
    current = time.time()
    elapsed = max(0.0, current - float(started_at or current))
    payload: dict[str, Any] = {
        "started_at_ms": int(float(started_at or current) * 1000),
        "updated_at_ms": int(current * 1000),
        "elapsed_seconds": round(elapsed, 1),
    }
    done = max(0, int(done or 0))
    total = max(0, int(total or 0))
    if done > 0 and total > done and elapsed > 0:
        rate = done / elapsed
        eta_seconds = max(1, int(round((total - done) / rate))) if rate > 0 else 0
        payload["eta_seconds"] = eta_seconds
        payload["eta_deadline_at_ms"] = int((current + eta_seconds) * 1000)
    elif total and done >= total:
        payload["eta_seconds"] = 0
    return payload


def _store_is_cancelled(store: JobStoreLike, job_id: str) -> bool:
    checker = getattr(store, "is_cancelled", None)
    if not callable(checker):
        return False
    try:
        return bool(checker(job_id))
    except Exception:
        return False


def _update_check_batch_cancelled(
    store: JobStoreLike,
    job_id: str,
    *,
    mode: str,
    sync_range: str,
    total: int,
    checked: int,
    submittable: int,
    blocked: int,
    failed: int,
    started_at: float,
    results: list[dict[str, Any]],
) -> None:
    store.update(
        job_id,
        status="stopped",
        progress={
            "task_id": job_id,
            "job_id": job_id,
            "operation": "check_batch",
            "phase": "stopped",
            "status_code": "CHECK_STOPPED",
            "mode": mode,
            "range": sync_range,
            "total": total,
            "percent": 100,
            "percent_complete": 100,
            "checked": checked,
            "submittable": submittable,
            "blocked": blocked,
            "failed": failed,
            "status_message": "批量质量检查已停止，未继续调用官方上下文或候选检查。",
            "message": "批量质量检查已停止，未继续调用官方上下文或候选检查。",
            **_timing_payload(started_at, done=checked, total=total),
            "items": results,
        },
    )


def run_check_batch_job_service(
    job_id: str,
    payload: dict[str, Any],
    *,
    store: JobStoreLike,
    passed_candidates_from_payload: PassedCandidates,
    run_config_from_payload: RunConfigFromPayload,
    api_from_run_config: ApiFromRunConfig,
    repository_factory: RepositoryFactory,
    ledger_factory: LedgerFactory,
    refresh_cloud_context_for_check: RefreshCloudContext,
    payload_truthy: PayloadTruthy,
    check_candidate_availability: CheckAvailability,
    observability_submission_preflight: ObservabilityPreflight,
    safe_error_message: SafeErrorMessage,
    error_payload: ErrorPayload,
) -> None:
    mode = str(payload.get("mode", "quick"))
    sync_range = str(payload.get("syncRange", "all"))
    candidates = passed_candidates_from_payload(payload)
    total = len(candidates)
    checked = 0
    submittable = 0
    blocked = 0
    failed = 0
    blocker_counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    cloud_alphas: list[dict[str, Any]] = []
    cloud_error = ""
    started_at = time.time()
    try:
        store.update(
            job_id,
            status="running",
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "check_batch",
                "phase": "cloud_sync",
                "status_code": "CHECK_CLOUD_SYNC",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "percent": 0 if total else 100,
                "percent_complete": 0 if total else 100,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "status_message": f"Preparing real-time checks for {total} passed alpha(s).",
                "message": f"Preparing real-time checks for {total} passed alpha(s).",
                **_timing_payload(started_at, done=0, total=total),
                "items": [],
            },
        )
        if _store_is_cancelled(store, job_id):
            _update_check_batch_cancelled(
                store,
                job_id,
                mode=mode,
                sync_range=sync_range,
                total=total,
                checked=checked,
                submittable=submittable,
                blocked=blocked,
                failed=failed,
                started_at=started_at,
                results=results,
            )
            return
        run_config = run_config_from_payload(payload)
        if _store_is_cancelled(store, job_id):
            _update_check_batch_cancelled(
                store,
                job_id,
                mode=mode,
                sync_range=sync_range,
                total=total,
                checked=checked,
                submittable=submittable,
                blocked=blocked,
                failed=failed,
                started_at=started_at,
                results=results,
            )
            return
        api = api_from_run_config(run_config)
        repo = repository_factory(run_config.ops.storage_dir)
        api.authenticate()
        if _store_is_cancelled(store, job_id):
            _update_check_batch_cancelled(
                store,
                job_id,
                mode=mode,
                sync_range=sync_range,
                total=total,
                checked=checked,
                submittable=submittable,
                blocked=blocked,
                failed=failed,
                started_at=started_at,
                results=results,
            )
            return
        cloud_alphas, cloud_error = refresh_cloud_context_for_check(
            api,
            repo,
            sync_range,
            job_id,
            total,
            mode,
            run_config.ops.settings.region,
            refresh_remote=payload_truthy(payload.get("refreshCloudForCheck")),
        )
        ledger = ledger_factory(run_config.ops.storage_dir)
        observability_preflight = observability_submission_preflight(run_config.ops.storage_dir)

        for index, candidate in enumerate(candidates, start=1):
            if _store_is_cancelled(store, job_id):
                _update_check_batch_cancelled(
                    store,
                    job_id,
                    mode=mode,
                    sync_range=sync_range,
                    total=total,
                    checked=checked,
                    submittable=submittable,
                    blocked=blocked,
                    failed=failed,
                    started_at=started_at,
                    results=results,
                )
                return
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "check_batch",
                    "phase": "checking",
                    "status_code": "CHECK_RUNNING",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "percent": (checked / total * 100) if total else 100,
                    "percent_complete": (checked / total * 100) if total else 100,
                    "checked": checked,
                    "submittable": submittable,
                    "blocked": blocked,
                    "failed": failed,
                    "current_alpha_id": candidate.get("alpha_id", ""),
                    "status_message": f"Checking {index}/{total}: {candidate.get('alpha_id', '')}",
                    "message": f"Checking {index}/{total}: {candidate.get('alpha_id', '')}",
                    **_timing_payload(started_at, done=checked, total=total),
                    "items": results,
                },
            )
            if _store_is_cancelled(store, job_id):
                _update_check_batch_cancelled(
                    store,
                    job_id,
                    mode=mode,
                    sync_range=sync_range,
                    total=total,
                    checked=checked,
                    submittable=submittable,
                    blocked=blocked,
                    failed=failed,
                    started_at=started_at,
                    results=results,
                )
                return
            result = check_candidate_availability(
                candidate,
                mode,
                api,
                ledger,
                cloud_alphas,
                cloud_error,
                observability_preflight=observability_preflight,
            )
            results.append(result)
            checked += 1
            if result.get("submittable", result.get("passed")):
                submittable += 1
            elif result.get("error"):
                failed += 1
            else:
                blocked += 1
                for check in result.get("checks") or []:
                    if isinstance(check, dict) and check.get("passed") is False:
                        blocker_counts[str(check.get("name") or "unknown")] += 1
            repo.save_check_record({"job_id": str(payload.get("job_id", "")), **result})
            persist_candidate_check_evidence(run_config.ops.storage_dir, candidate, result)
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "check_batch",
                    "phase": "checking",
                    "status_code": "CHECK_RUNNING",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "percent": (checked / total * 100) if total else 100,
                    "percent_complete": (checked / total * 100) if total else 100,
                    "checked": checked,
                    "submittable": submittable,
                    "blocked": blocked,
                    "failed": failed,
                    "blockers": dict(blocker_counts.most_common(5)),
                    "current_alpha_id": candidate.get("alpha_id", ""),
                    "status_message": f"Checked {checked}/{total}; submittable {submittable}, blocked {blocked}, failed {failed}.",
                    "message": f"Checked {checked}/{total}; submittable {submittable}, blocked {blocked}, failed {failed}.",
                    **_timing_payload(started_at, done=checked, total=total),
                    "items": results,
                },
            )

        if _store_is_cancelled(store, job_id):
            _update_check_batch_cancelled(
                store,
                job_id,
                mode=mode,
                sync_range=sync_range,
                total=total,
                checked=checked,
                submittable=submittable,
                blocked=blocked,
                failed=failed,
                started_at=started_at,
                results=results,
            )
            return

        summary = {
            "mode": mode,
            "range": sync_range,
            "total": total,
            "checked": checked,
            "submittable": submittable,
            "blocked": blocked,
            "failed": failed,
            "cloud_count": len(cloud_alphas),
            "cloud_error": cloud_error,
            "blockers": dict(blocker_counts.most_common(5)),
        }
        store.update(
            job_id,
            status="completed",
            result={"ok": True, "summary": summary, "items": results},
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "check_batch",
                "phase": "completed",
                "status_code": "CHECK_COMPLETED",
                "percent": 100,
                "percent_complete": 100,
                "status_message": "Batch check completed.",
                "message": "Batch check completed.",
                **_timing_payload(started_at, done=checked, total=total),
                "items": results,
                **summary,
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="CHECK_BATCH_JOB_FAILED", job_id=job_id, phase="check_batch_job")
        logger.error("check batch job failed: %s", error_context, exc_info=True)
        store.update(
            job_id,
            status="failed",
            error=message,
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "check_batch",
                "phase": "failed",
                "status_code": "CHECK_FAILED",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "percent": 100,
                "percent_complete": 100,
                "checked": checked,
                "submittable": submittable,
                "blocked": blocked,
                "failed": failed + 1,
                "status_message": message,
                "message": message,
                **_timing_payload(started_at, done=checked, total=total),
                "items": results,
                "error_context": error_context,
            },
        )

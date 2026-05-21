"""Structured risk explanations and navigation hints for web submit flows."""

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

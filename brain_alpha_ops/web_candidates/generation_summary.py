"""Status summaries for Web candidate generation jobs."""

from __future__ import annotations

from typing import Any

_REASON_LABELS = {
    "expression_high_turnover_generation_risk": "高换手生成风险",
    "gate_not_submission_ready": "提交门禁未就绪",
    "local_backtest_failed": "本地回测未通过",
    "local_backtest_unsupported": "本地回测不支持",
    "local_candidate_invalid": "本地候选未通过",
    "local_quality_failed": "本地质量未通过",
    "missing_official_alpha_id": "缺少官方 Alpha ID",
    "missing_official_metrics": "缺少官方仿真指标",
    "non_signal_generation_fields": "非信号字段",
}


def candidate_generation_status_message(result: dict[str, Any]) -> str:
    """Return a user-facing completion message for candidate generation."""

    if not result.get("ok"):
        return str(result.get("error") or "候选生成失败。")
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    quality = summary.get("quality_summary") if isinstance(summary.get("quality_summary"), dict) else {}
    persistence = summary.get("persistence") if isinstance(summary.get("persistence"), dict) else {}
    generated = _positive_int(
        summary.get("generated_count"),
        result.get("generated_count"),
        result.get("count"),
    )
    returned = _positive_int(
        summary.get("returned_count"),
        result.get("count"),
        len(result.get("candidates") or []),
    )
    rejected = _positive_int(
        summary.get("rejected_count"),
        quality.get("invalid_count"),
    )
    qualified = _positive_int(quality.get("qualified_count"))
    local_valid = _positive_int(quality.get("local_valid_count"))
    persisted = _positive_int(persistence.get("persisted_count")) if persistence else None
    target_pool_size = _nonnegative_int(summary.get("target_pool_size"))
    existing_pool_size = _nonnegative_int(summary.get("existing_pool_size"))
    pool_deficit = _nonnegative_int(summary.get("pool_deficit"))
    reason_counts = (
        summary.get("rejected_reasons")
        if isinstance(summary.get("rejected_reasons"), dict)
        else persistence.get("skipped_invalid_reasons")
        if isinstance(persistence.get("skipped_invalid_reasons"), dict)
        else quality.get("reason_counts")
        if isinstance(quality.get("reason_counts"), dict)
        else {}
    )
    reason_detail = _reason_detail(reason_counts)
    saved_part = f"已保存 {persisted} 个可推进候选" if persisted is not None else f"{returned} 个进入主候选列表"
    pool_part = (
        f"目标池 {target_pool_size}；当前可推进 {existing_pool_size}；补位缺口 {pool_deficit}。"
        if target_pool_size is not None
        else ""
    )
    if generated > 0 and returned <= 0:
        return (
            f"{pool_part}生成 {generated} 个本地候选；0 个通过本地门禁，{rejected} 个已阻断"
            f"{reason_detail}；{saved_part}。"
        )
    return (
        f"{pool_part}生成 {generated} 个本地候选；{returned} 个通过本地门禁，"
        f"{local_valid} 个本地有效，{qualified} 个达到提交证据带，"
        f"{rejected} 个已阻断{reason_detail}；{saved_part}。"
    )


def _reason_detail(reason_counts: Any) -> str:
    if not isinstance(reason_counts, dict) or not reason_counts:
        return ""
    rows = []
    for reason, count in sorted(reason_counts.items(), key=lambda item: (-_positive_int(item[1]), str(item[0])))[:3]:
        label = _REASON_LABELS.get(str(reason), str(reason))
        rows.append(f"{label} {count}")
    return "（" + "，".join(rows) + "）" if rows else ""


def _positive_int(*values: Any) -> int:
    for value in values:
        try:
            parsed = int(float(value or 0))
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0


def _nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return max(0, parsed)

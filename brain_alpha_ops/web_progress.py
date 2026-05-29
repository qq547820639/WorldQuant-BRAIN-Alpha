"""Progress presentation helpers for the local web console."""

from __future__ import annotations

from typing import Any


PHASE_LABELS: dict[str, str] = {
    "queued": "排队",
    "auth": "认证",
    "scan": "扫描",
    "merge": "合并",
    "startup": "启动",
    "cloud_sync": "云端数据同步",
    "context": "加载上下文",
    "production_loop": "循环生产",
    "candidate_generation": "候选生成",
    "local_scoring": "本地评分排序",
    "scoring": "评分",
    "candidate_pool": "候选池维护",
    "official_validation": "回测前预检",
    "official_simulation": "官方模拟回测",
    "official_deferred": "官方延迟",
    "checking": "批量检查",
    "submitting": "提交",
    "config_load": "配置加载",
    "completed": "已完成",
    "stopped": "已停止",
    "failed": "失败",
    "stopping": "正在停止",
    "context_fields": "更新字段缓存",
    "context_operators": "更新算子缓存",
    "page_load": "页面加载",
    "dashboard_load": "仪表盘加载",
    "cloud_cache": "云端缓存",
}


def _bounded_percent(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return max(0.0, min(100.0, parsed))


def _ratio_percent(progress: dict[str, Any]) -> float | None:
    total = progress.get("total")
    for done_key in ("done", "scanned", "checked", "submitted", "current"):
        if done_key not in progress:
            continue
        if done_key == "current" and "total_steps" in progress:
            total = progress.get("total_steps")
        try:
            done_value = float(progress.get(done_key) or 0)
            total_value = float(total or 0)
        except (TypeError, ValueError):
            continue
        if total_value > 0:
            return _bounded_percent(done_value / total_value * 100.0)
    return None


def progress_percent(progress: dict[str, Any]) -> float | None:
    """Return a normalized 0-100 progress value when it can be derived."""
    explicit = _bounded_percent(progress.get("percent_complete"))
    if explicit is not None:
        return explicit
    explicit = _bounded_percent(progress.get("percent"))
    if explicit is not None:
        return explicit
    return _ratio_percent(progress)


def normalize_progress(progress: dict[str, Any], *, task_id: str = "", status: str = "") -> dict[str, Any]:
    """Add the unified progress fields expected by API and React consumers."""
    normalized = dict(progress or {})
    if task_id:
        normalized.setdefault("task_id", task_id)
        normalized.setdefault("job_id", task_id)
    if status:
        normalized.setdefault("status", status)
    if "phase" in normalized and "phase_label" not in normalized:
        normalized["phase_label"] = PHASE_LABELS.get(str(normalized["phase"]), str(normalized["phase"]))
    percent = progress_percent(normalized)
    if percent is not None:
        normalized["percent_complete"] = round(percent, 1)
        normalized.setdefault("percent", round(percent, 1))
    message = normalized.get("status_message") or normalized.get("message") or normalized.get("phase_label") or normalized.get("phase") or status
    if message:
        normalized["status_message"] = str(message)
        normalized.setdefault("message", str(message))
    try:
        eta_seconds = int(float(normalized.get("eta_seconds") or 0))
    except (TypeError, ValueError):
        eta_seconds = 0
    normalized["eta_seconds"] = max(0, eta_seconds)
    return normalized


def enrich_progress(progress: dict) -> dict:
    progress = normalize_progress(progress)
    if "phase" in progress and "phase_label" not in progress:
        progress["phase_label"] = PHASE_LABELS.get(str(progress["phase"]), str(progress["phase"]))
    return progress

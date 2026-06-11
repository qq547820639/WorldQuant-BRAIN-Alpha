"""Progress presentation helpers for the local web console."""

from __future__ import annotations

from typing import Any, TypedDict


class ProgressPayload(TypedDict, total=False):
    """Public progress contract shared by polling, SSE, and UI rendering."""

    task_id: str
    job_id: str
    status: str
    phase: str
    phase_label: str
    percent: float
    percent_complete: float
    status_message: str
    message: str
    eta_seconds: int
    total: int | float
    done: int | float
    scanned: int | float
    checked: int | float
    submitted: int | float
    current: int | float
    total_steps: int | float
    indeterminate: bool
    open_ended: bool


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
    if _is_context_stage_progress(progress):
        return _context_stage_percent(progress)
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
    explicit = _bounded_percent(progress.get("percent_complete"))
    if explicit is not None:
        return explicit
    explicit = _bounded_percent(progress.get("percent"))
    if explicit is not None:
        return explicit
    return _ratio_percent(progress)


def _is_cloud_scan_progress(progress: dict[str, Any]) -> bool:
    phase = str(progress.get("phase") or "").lower()
    status_code = str(progress.get("status_code") or "").upper()
    operation = str(progress.get("operation") or "").lower()
    if phase != "scan":
        return False
    if status_code and status_code != "SCAN":
        return False
    return operation in ("", "sync_alphas", "cloud_sync")


_CONTEXT_STAGE_COUNTERS: dict[str, tuple[str, str]] = {
    "CONTEXT_FIELDS": ("fields_count", "fields_total"),
    "CONTEXT_OPERATORS": ("operators_count", "operators_total"),
    "CONTEXT_DATASETS": ("datasets_count", "datasets_total"),
}


def _is_context_stage_progress(progress: dict[str, Any]) -> bool:
    status_code = str(progress.get("status_code") or "").upper()
    return status_code in _CONTEXT_STAGE_COUNTERS


def _context_stage_counts(progress: dict[str, Any]) -> tuple[float, float]:
    status_code = str(progress.get("status_code") or "").upper()
    keys = _CONTEXT_STAGE_COUNTERS.get(status_code)
    if not keys:
        return 0.0, 0.0
    current_key, total_key = keys
    try:
        current = float(progress.get(current_key) or 0)
        total = float(progress.get(total_key) or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0
    return max(0.0, current), max(0.0, total)


def _context_stage_percent(progress: dict[str, Any]) -> float | None:
    current, total = _context_stage_counts(progress)
    if total <= 0:
        return None
    return _bounded_percent(current / total * 100.0)


def _format_count(value: Any) -> str:
    try:
        numeric = int(float(value or 0))
    except (TypeError, ValueError):
        numeric = 0
    return f"{max(0, numeric):,}"


def _open_ended_scan_message(progress: dict[str, Any]) -> str:
    try:
        scanned = int(float(progress.get("scanned") or 0))
    except (TypeError, ValueError):
        scanned = 0
    try:
        reported_total = int(float(
            progress.get("api_reported_total")
            or progress.get("filter_window_count")
            or 0
        ))
    except (TypeError, ValueError):
        reported_total = 0
    if scanned <= 0:
        return "正在扫描云端 Alpha；等待官方接口返回第一页和接口分页参考数。"
    if reported_total > 0:
        page_detail = _scan_page_detail(progress)
        current_page_detail = _scan_current_page_detail(progress)
        return (
            f"已拉取 {_format_count(scanned)} 条云端 Alpha；"
            f"接口分页参考数 {_format_count(reported_total)} 条，不是云端 Alpha 总量，会继续按分页自动确认边界"
            f"{page_detail}{current_page_detail}。"
        )
    return f"已拉取 {_format_count(scanned)} 条云端 Alpha；接口分页参考数仍在确认，会按分页返回继续读取。"


def _scan_has_filter_window_count(progress: dict[str, Any]) -> bool:
    try:
        return int(float(progress.get("api_reported_total") or progress.get("filter_window_count") or 0)) > 0
    except (TypeError, ValueError):
        return False


def _scan_page_detail(progress: dict[str, Any]) -> str:
    page = _positive_int(progress.get("pages_fetched") or progress.get("page_number"))
    if page:
        return f"；当前第 {_format_count(page)} 页"
    return ""


def _scan_current_page_detail(progress: dict[str, Any]) -> str:
    page_size = _positive_int(progress.get("page_size"))
    page_limit = _positive_int(progress.get("page_limit"))
    next_offset = _positive_int(progress.get("next_offset"))
    filter_window_count = _positive_int(progress.get("api_reported_total") or progress.get("filter_window_count"))
    parts: list[str] = []
    if page_size:
        parts.append(f"本页 {_format_count(page_size)} 条")
    if page_limit:
        parts.append(f"分页参数 {_format_count(page_limit)} 条/页")
    if next_offset:
        if filter_window_count and next_offset >= filter_window_count:
            parts.append("下一请求确认分页边界")
        else:
            parts.append("下一轮继续拉取")
    if progress.get("confirming_total_boundary"):
        parts.append("本页已满，继续确认下一页")
    if progress.get("cursor_before"):
        if str(progress.get("warning") or "") == "transient_page_retry_narrowed_by_date":
            parts.append("网关超时后自动缩小时间范围")
        else:
            parts.append("已自动缩小时间范围")
    return "；" + "，".join(parts) if parts else ""


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def normalize_progress(progress: dict[str, Any], *, task_id: str = "", status: str = "") -> dict[str, Any]:
    normalized = dict(progress or {})
    if task_id:
        normalized.setdefault("task_id", task_id)
        normalized.setdefault("job_id", task_id)
    if status:
        normalized.setdefault("status", status)
    if "phase" in normalized and "phase_label" not in normalized:
        normalized["phase_label"] = PHASE_LABELS.get(str(normalized["phase"]), str(normalized["phase"]))
    open_ended_scan = _is_cloud_scan_progress(normalized)
    if open_ended_scan:
        normalized.pop("eta_deadline_at_ms", None)
        normalized.pop("eta_seconds", None)
        normalized.pop("percent_complete", None)
        normalized.pop("percent", None)
        normalized["indeterminate"] = True
        normalized["open_ended"] = True
        message = _open_ended_scan_message(normalized)
        normalized["status_message"] = message
        normalized["message"] = message
    elif _is_context_stage_progress(normalized):
        normalized.pop("percent_complete", None)
        normalized.pop("percent", None)
        percent = _context_stage_percent(normalized)
        if percent is not None:
            normalized["percent_complete"] = round(percent, 1)
            normalized.setdefault("percent", round(percent, 1))
        else:
            normalized.pop("eta_deadline_at_ms", None)
            normalized.pop("eta_seconds", None)
    else:
        percent = progress_percent(normalized)
        if percent is not None:
            normalized["percent_complete"] = round(percent, 1)
            normalized.setdefault("percent", round(percent, 1))
    message = (
        normalized.get("status_message")
        or normalized.get("message")
        or normalized.get("phase_label")
        or normalized.get("phase")
        or status
    )
    if message:
        normalized["status_message"] = str(message)
        normalized.setdefault("message", str(message))
    try:
        eta_seconds = 0 if open_ended_scan else int(float(normalized.get("eta_seconds") or 0))
    except (TypeError, ValueError):
        eta_seconds = 0
    normalized["eta_seconds"] = max(0, eta_seconds)
    return normalized


def enrich_progress(progress: dict) -> dict:
    return normalize_progress(progress)

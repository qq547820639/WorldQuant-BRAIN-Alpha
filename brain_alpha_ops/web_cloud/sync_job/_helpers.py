"""Helper functions and observability constants for cloud sync jobs."""

from __future__ import annotations

import time
from typing import Any


def _timing_payload(started_at: float, *, done: int = 0, total: int = 0, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    start = float(started_at or current)
    elapsed = max(0.0, current - start)
    payload: dict[str, Any] = {
        "started_at_ms": int(start * 1000),
        "updated_at_ms": int(current * 1000),
        "elapsed_seconds": round(elapsed, 1),
    }
    done = max(0, int(done or 0))
    total = max(0, int(total or 0))
    rate = done / elapsed if done > 0 and elapsed > 0 else 0.0
    if rate > 0:
        payload["rate_per_second"] = round(rate, 3)
    if done > 0 and total > done and elapsed > 0:
        eta_seconds = max(1, int(round((total - done) / rate))) if rate > 0 else 0
        payload.update({
            "eta_seconds": eta_seconds,
            "eta_deadline_at_ms": int((current + eta_seconds) * 1000),
        })
    elif total and done >= total:
        payload["eta_seconds"] = 0
    return payload


_SCAN_OBSERVABILITY_INT_KEYS = frozenset({
    "api_reported_total",
    "filter_window_count",
    "page_number",
    "pages_fetched",
    "expected_pages",
    "remaining_items",
    "page_limit",
    "next_offset",
    "new_unique_items",
    "duplicate_unique_items",
    "unique_items",
    "stalled_unique_pages",
    "retry_attempt",
    "error_status",
})
_SCAN_OBSERVABILITY_FLOAT_KEYS = frozenset({"retry_after_seconds"})
_SCAN_OBSERVABILITY_TEXT_KEYS = frozenset({"warning", "cursor_before", "pagination_target", "stop_reason"})
_SCAN_OBSERVABILITY_BOOL_KEYS = frozenset({"confirming_total_boundary", "has_more", "pagination_complete", "retry_exhausted"})
_SCAN_OBSERVABILITY_KEYS = (
    _SCAN_OBSERVABILITY_INT_KEYS
    | _SCAN_OBSERVABILITY_FLOAT_KEYS
    | _SCAN_OBSERVABILITY_TEXT_KEYS
    | _SCAN_OBSERVABILITY_BOOL_KEYS
)


def _scan_observability(progress: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in _SCAN_OBSERVABILITY_INT_KEYS:
        if key not in progress:
            continue
        try:
            payload[key] = int(progress.get(key, 0) or 0)
        except (TypeError, ValueError):
            continue
    for key in _SCAN_OBSERVABILITY_FLOAT_KEYS:
        if key not in progress:
            continue
        try:
            payload[key] = float(progress.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
    for key in _SCAN_OBSERVABILITY_TEXT_KEYS:
        value = str(progress.get(key) or "").strip()
        if value:
            payload[key] = value
    for key in _SCAN_OBSERVABILITY_BOOL_KEYS:
        if key in progress:
            payload[key] = bool(progress.get(key))
    return payload


def _cloud_scan_status_message(stats: dict[str, Any]) -> str:
    scanned = max(0, int(stats.get("scanned", 0) or 0))
    filter_window_count = max(0, int(stats.get("api_reported_total") or stats.get("filter_window_count") or 0))
    page = max(0, int(stats.get("pages_fetched") or stats.get("page_number") or 0))
    page_limit = max(0, int(stats.get("page_limit") or 0))
    page_size = max(0, int(stats.get("page_size") or 0))
    next_offset = max(0, int(stats.get("next_offset") or 0))
    if scanned <= 0:
        return "正在扫描云端 Alpha，等待官方接口返回第一页和接口分页参考数；首次全量同步可能需要 3-5 分钟，近 3/7 天范围通常更快。"
    page_detail = f"当前第 {page:,} 页" if page else ""
    limit_detail = f"分页参数 {page_limit:,} 条/页" if page_limit else ""
    current_page_detail = f"本页 {page_size:,} 条" if page_size else ""
    if next_offset and filter_window_count and next_offset >= filter_window_count:
        next_detail = "下一请求确认分页边界"
    else:
        next_detail = "下一轮继续拉取" if next_offset else ""
    cursor_detail = "已自动缩小时间范围" if stats.get("cursor_before") else ""
    details = "；".join(part for part in (page_detail, limit_detail, current_page_detail, next_detail, cursor_detail) if part)
    if filter_window_count > 0:
        return (
            f"正在扫描云端 Alpha；已拉取 {scanned:,} 条；接口分页参考数 {filter_window_count:,} 条"
            f"{'；' + details if details else ''}。"
        )
    return (
        f"正在扫描云端 Alpha；已拉取 {scanned:,} 条"
        f"{'；' + details if details else ''}；会继续直到官方接口返回空页或短页。"
    )


def _sync_range_label(sync_range: str) -> str:
    return {
        "3d": "近 3 天",
        "7d": "近 7 天",
        "recent": "近期 30 天",
        "6months": "近 6 个月",
        "all": "全部",
    }.get(sync_range, sync_range or "全部")


def _final_sync_status_message(stats: dict[str, Any], *, context_error: str, context_warnings: list[str]) -> str:
    if context_error:
        return f"云端同步完成，但官方上下文刷新有警告：{context_error}"
    if context_warnings:
        return f"云端同步完成，但官方上下文刷新有警告：{'; '.join(context_warnings)}"
    if int(stats.get("added", 0) or 0) == 0 and int(stats.get("updated", 0) or 0) == 0:
        return (
            f"云端同步完成：已扫描 {stats['scanned']:,} 条，云端数据无变化，"
            f"本地缓存已是最新；跳过 {stats['skipped']:,} 条，失败 {stats['failed']:,} 条。"
        )
    return (
        f"云端同步完成：已扫描 {stats['scanned']:,} 条，新增 {stats['added']:,} 条，"
        f"更新 {stats.get('updated', 0):,} 条，跳过 {stats['skipped']:,} 条，失败 {stats['failed']:,} 条。"
    )

"""Pagination, deduplication, and cursor-recovery helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Any

_logger = logging.getLogger("brain_alpha_ops.brain_api.official_helpers")


def looks_partial_context_cache(kind: str, items: list[dict], total: int, page_limit: int) -> bool:
    limit = _positive_int(page_limit)
    full_page_boundary = (
        kind in {"fields", "datasets", "operators"}
        and limit > 0
        and len(items) > 0
        and len(items) % limit == 0
    )
    if total and len(items) >= total:
        return full_page_boundary
    if total and len(items) < total:
        return True
    return full_page_boundary


def items(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "items", "fields", "datasets", "dataSets", "data_sets", "operators", "checks"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def total_count(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if not isinstance(data, dict):
        return 0
    for key in ("count", "total", "totalCount", "total_count", "recordsTotal", "records_total"):
        value = data.get(key)
        if isinstance(value, bool):
            continue
        try:
            count = int(value)
        except (TypeError, ValueError):
            continue
        if count >= 0:
            return count
    return 0


def page_signature(items: list[dict], *, keys: tuple[str, ...]) -> str:
    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = {key: item.get(key, "") for key in keys}
        if not any(str(value or "") for value in row.values()):
            row = item
        rows.append(row)
    raw = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_user_alpha_offset_limit(exc: Exception) -> bool:
    text = str(exc).lower()
    return getattr(exc, "status_code", None) == 400 and "invalid offset" in text and "filter" in text


def oldest_alpha_created_at(rows: list[dict[str, Any]]) -> str:
    for row in reversed(rows):
        created = str(row.get("created_at") or "").strip()
        if created:
            return created
    return ""


def dedupe_alpha_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        alpha_id = str(row.get("id") or "").strip()
        if alpha_id:
            if alpha_id in seen:
                continue
            seen.add(alpha_id)
        deduped.append(row)
    return deduped


def user_alpha_offset_recovery(
    exc: Exception,
    rows: list[dict[str, Any]],
    page_params: dict[str, Any],
    *,
    sync_range: str,
    total: int,
) -> dict[str, Any] | None:
    if not is_user_alpha_offset_limit(exc):
        return None
    return user_alpha_cursor_recovery(
        rows,
        page_params,
        sync_range=sync_range,
        total=total,
        warning="offset_limit_narrowed_by_date",
    )


def user_alpha_cursor_recovery(
    rows: list[dict[str, Any]],
    page_params: dict[str, Any],
    *,
    sync_range: str,
    total: int,
    warning: str,
    **progress_extra: Any,
) -> dict[str, Any] | None:
    cursor = oldest_alpha_created_at(rows)
    if not cursor or page_params.get("dateCreated<") == cursor:
        return None
    next_params = dict(page_params)
    next_params["dateCreated<"] = cursor
    next_params["offset"] = 0
    return {
        "page_params": next_params,
        "progress": user_alpha_progress(
            sync_range,
            rows,
            max(total, len(rows)),
            page_size=0,
            offset=0,
            cursor_before=cursor,
            warning=warning,
            **progress_extra,
        ),
    }


def user_alpha_progress(sync_range: str, rows: list, total: int, **extra: Any) -> dict[str, Any]:
    page_size = _positive_int(extra.get("page_size"))
    page_limit = _positive_int(extra.get("page_limit")) or page_size
    offset = _positive_int(extra.get("offset"))
    expected_pages = int(math.ceil(total / page_limit)) if total > 0 and page_limit > 0 else 0
    payload: dict[str, Any] = {
        "range": sync_range,
        "scanned": len(rows),
        "total": total,
        "pagination_target": "api_filter_window" if total > 0 else "page_exhaustion",
    }
    if page_size > 0:
        payload["page_size"] = page_size
    if page_limit > 0:
        payload["page_limit"] = page_limit
        payload["next_offset"] = offset + page_limit
        payload["pages_fetched"] = int(offset / page_limit) + 1
    if expected_pages > 0:
        payload["expected_pages"] = expected_pages
    payload.update(extra)
    return payload


def _positive_int(value: Any) -> int:
    try:
        numeric = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, numeric)

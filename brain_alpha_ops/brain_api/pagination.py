"""Pagination helpers for official BRAIN API collection endpoints."""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Callable

from .official_helpers import page_signature as _page_signature
from .official_helpers import total_count as _total_count


logger = logging.getLogger("brain_alpha_ops.brain_api.official")


def _standard_pagination_progress(
    rows: list[dict[str, Any]],
    total: int,
    *,
    page_size: int,
    offset: int,
    **extra: Any,
) -> dict[str, Any]:
    page_limit = _coerce_positive_int(extra.get("page_limit")) or page_size
    expected_pages = _expected_pages(total, page_limit)
    payload: dict[str, Any] = {
        "scanned": len(rows),
        "total": total,
        "page_size": page_size,
        "page_limit": page_limit,
        "offset": offset,
        "next_offset": offset + page_limit if page_limit > 0 else offset,
        "expected_pages": expected_pages,
        "pages_fetched": _pages_fetched(offset, page_limit),
    }
    api_reported_total = _coerce_positive_int(extra.get("api_reported_total"))
    if api_reported_total > 0:
        payload["api_reported_total"] = api_reported_total
    if expected_pages > 0:
        payload["pagination_target"] = "api_total"
    payload.update(extra)
    return payload


def _paginate_collection(
    *,
    label: str,
    page_params: dict[str, Any],
    request_page: Callable[[dict[str, Any]], tuple[Any, Any]],
    normalize_page: Callable[[Any], list[dict[str, Any]]],
    signature_keys: tuple[str, ...],
    max_pages: int | None,
    max_items: int | None = None,
    progress_callback: Callable[[dict[str, Any]], Any] | None = None,
    progress_payload: Callable[..., dict[str, Any]] = _standard_pagination_progress,
    total_update: Callable[[Any, int, int], int] | None = None,
    page_error_recovery: Callable[[Exception, list[dict[str, Any]], dict[str, Any], int], dict[str, Any] | None] | None = None,
    postprocess_items: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    stop_when_total_reached: bool = True,
    confirm_full_page_at_total_boundary: bool = False,
    unique_item_key: Callable[[dict[str, Any]], str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    total = 0
    params = dict(page_params)
    seen_page_signatures: set[str] = set()
    seen_item_keys: set[str] = set()
    stalled_unique_pages = 0
    update_total = total_update or (lambda data, current, _count: _total_count(data) or current)
    page_number = 0
    # C26 P2: stall-aware loop — exits if no page for 600s
    while True:
        page_number += 1
        if max_pages is not None and page_number > max_pages:
            logger.warning(
                "%s pagination reached max pages limit (%d), items=%d total=%d",
                label,
                max_pages,
                len(items),
                total,
            )
            break
        try:
            data, _headers = request_page(params)
        except Exception as exc:
            recovery = page_error_recovery(exc, items, params, total) if page_error_recovery else None
            if not recovery:
                raise
            params = dict(recovery.get("page_params") or params)
            total = int(recovery.get("total", total) or 0)
            if recovery.get("clear_seen"):
                seen_page_signatures.clear()
            if progress_callback and recovery.get("progress"):
                if _progress_cancelled(progress_callback, recovery["progress"]):
                    logger.warning(
                        "%s pagination stopped by progress callback, offset=%s items=%d total=%d",
                        label,
                        int(params.get("offset", 0)),
                        len(items),
                        total,
                    )
                    break
            sleep_seconds = _coerce_sleep_seconds(recovery.get("sleep_seconds"))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            continue

        page_items = normalize_page(data)
        api_reported_total = _total_count(data) or 0
        page_signature = _page_signature(page_items, keys=signature_keys)
        offset = int(params.get("offset", 0))
        if page_items and page_signature in seen_page_signatures:
            logger.warning(
                "%s pagination stopped on repeated page signature, offset=%s items=%d total=%d",
                label,
                offset,
                len(items),
                total,
            )
            if progress_callback:
                progress_callback(progress_payload(
                    items,
                    total,
                    page_size=len(page_items),
                    offset=offset,
                    truncated=True,
                    warning="repeated_page",
                    page_limit=int(params.get("limit", 0) or 0),
                    api_reported_total=api_reported_total,
                    has_more=False,
                    pagination_complete=False,
                    stop_reason="repeated_page",
                ))
            break
        if page_items:
            seen_page_signatures.add(page_signature)
        progress_extra: dict[str, Any] = {"page_number": page_number}
        if unique_item_key is not None and page_items:
            page_item_keys = {unique_item_key(item) for item in page_items}
            page_item_keys.discard("")
            if page_item_keys:
                new_item_keys = page_item_keys - seen_item_keys
                duplicate_item_count = len(page_item_keys) - len(new_item_keys)
                if not new_item_keys:
                    stalled_unique_pages += 1
                    logger.warning(
                        "%s pagination page added no new unique items, offset=%s items=%d total=%d",
                        label,
                        offset,
                        len(items),
                        total,
                    )
                    progress_extra.update({
                        "warning": "no_new_unique_items",
                    })
                else:
                    stalled_unique_pages = 0
                seen_item_keys.update(page_item_keys)
                progress_extra.update({
                    "new_unique_items": len(new_item_keys),
                    "duplicate_unique_items": duplicate_item_count,
                    "unique_items": len(seen_item_keys),
                    "stalled_unique_pages": stalled_unique_pages,
                })
        items.extend(page_items)
        total = update_total(data, total, len(items))
        page_limit = int(params["limit"])
        pagination_state = _pagination_state(
            total=total,
            scanned=len(items),
            page_size=len(page_items),
            page_limit=page_limit,
            stop_when_total_reached=stop_when_total_reached,
            confirm_full_page_at_total_boundary=confirm_full_page_at_total_boundary,
        )
        progress_extra.update(pagination_state)
        if api_reported_total > 0:
            progress_extra["api_reported_total"] = api_reported_total
        if progress_callback:
            payload = progress_payload(
                items,
                total,
                page_size=len(page_items),
                offset=offset,
                page_limit=page_limit,
                next_offset=offset + page_limit,
                **progress_extra,
            )
            if _progress_cancelled(progress_callback, payload):
                logger.warning(
                    "%s pagination stopped by progress callback, offset=%s items=%d total=%d",
                    label,
                    offset,
                    len(items),
                    total,
                )
                break
        if pagination_state.get("stop_reason") == "confirming_total_boundary":
            params["offset"] = offset + page_limit
            continue
        if stop_when_total_reached and total and len(items) >= total:
            if confirm_full_page_at_total_boundary and len(page_items) >= page_limit:
                params["offset"] = offset + page_limit
                continue
            break
        if max_items is not None and len(items) >= max_items:
            logger.warning("%s pagination reached max item limit (%d), total=%d", label, max_items, total)
            items = items[:max_items]
            break
        if len(page_items) < page_limit:
            break
        params["offset"] = offset + page_limit
    if postprocess_items:
        items = postprocess_items(items)
    return items, total


def _progress_cancelled(
    progress_callback: Callable[[dict[str, Any]], Any],
    payload: dict[str, Any],
) -> bool:
    return progress_callback(payload) is False


def _coerce_sleep_seconds(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _coerce_positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _pagination_state(
    *,
    total: int,
    scanned: int,
    page_size: int,
    page_limit: int,
    stop_when_total_reached: bool,
    confirm_full_page_at_total_boundary: bool,
) -> dict[str, Any]:
    total_value = max(0, int(total or 0))
    scanned_value = max(0, int(scanned or 0))
    page_size_value = max(0, int(page_size or 0))
    page_limit_value = max(0, int(page_limit or 0))
    remaining_items = max(total_value - scanned_value, 0) if total_value > 0 else None
    reached_total = bool(stop_when_total_reached and total_value > 0 and scanned_value >= total_value)
    full_page = bool(page_limit_value > 0 and page_size_value >= page_limit_value)
    has_more = bool(full_page)
    stop_reason = ""
    pagination_complete = False
    confirming_total_boundary = False

    if reached_total:
        if confirm_full_page_at_total_boundary and full_page:
            has_more = True
            confirming_total_boundary = True
            stop_reason = "confirming_total_boundary"
        else:
            has_more = False
            pagination_complete = True
            stop_reason = "api_total_reached"
    elif page_limit_value <= 0 or page_size_value <= 0:
        has_more = False
        pagination_complete = True
        stop_reason = "empty_page"
    elif page_size_value < page_limit_value:
        has_more = False
        pagination_complete = True
        stop_reason = "short_page"

    payload: dict[str, Any] = {
        "has_more": has_more,
        "pagination_complete": pagination_complete,
    }
    if remaining_items is not None:
        payload["remaining_items"] = remaining_items
    if stop_reason:
        payload["stop_reason"] = stop_reason
    if confirming_total_boundary:
        payload["confirming_total_boundary"] = True
    return payload


def _expected_pages(total: int, page_size: int) -> int:
    try:
        total_value = int(total or 0)
        page_size_value = int(page_size or 0)
    except (TypeError, ValueError):
        return 0
    if total_value <= 0 or page_size_value <= 0:
        return 0
    return int(math.ceil(total_value / page_size_value))


def _pages_fetched(offset: int, page_size: int) -> int:
    try:
        offset_value = max(0, int(offset or 0))
        page_size_value = int(page_size or 0)
    except (TypeError, ValueError):
        return 0
    if page_size_value <= 0:
        return 0
    return int(offset_value / page_size_value) + 1

"""Pagination helpers for official BRAIN API collection endpoints."""

from __future__ import annotations

import logging
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
    payload: dict[str, Any] = {
        "scanned": len(rows),
        "total": total,
        "page_size": page_size,
        "offset": offset,
    }
    payload.update(extra)
    return payload


def _paginate_collection(
    *,
    label: str,
    page_params: dict[str, Any],
    request_page: Callable[[dict[str, Any]], tuple[Any, Any]],
    normalize_page: Callable[[Any], list[dict[str, Any]]],
    signature_keys: tuple[str, ...],
    max_pages: int,
    max_items: int | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    progress_payload: Callable[..., dict[str, Any]] = _standard_pagination_progress,
    total_update: Callable[[Any, int, int], int] | None = None,
    page_error_recovery: Callable[[Exception, list[dict[str, Any]], dict[str, Any], int], dict[str, Any] | None] | None = None,
    postprocess_items: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    stop_when_total_reached: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    total = 0
    params = dict(page_params)
    seen_page_signatures: set[str] = set()
    update_total = total_update or (lambda data, current, _count: _total_count(data) or current)
    for _page in range(1, max_pages + 1):
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
                progress_callback(recovery["progress"])
            continue

        page_items = normalize_page(data)
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
                ))
            break
        if page_items:
            seen_page_signatures.add(page_signature)
        items.extend(page_items)
        total = update_total(data, total, len(items))
        if progress_callback:
            progress_callback(progress_payload(items, total, page_size=len(page_items), offset=offset))
        if stop_when_total_reached and total and len(items) >= total:
            break
        if max_items is not None and len(items) >= max_items:
            logger.warning("%s pagination reached max item limit (%d), total=%d", label, max_items, total)
            items = items[:max_items]
            break
        if len(page_items) < int(params["limit"]):
            break
        params["offset"] = offset + int(params["limit"])
    else:
        logger.warning("%s pagination reached max pages limit (%d), items=%d total=%d", label, max_pages, len(items), total)
    if postprocess_items:
        items = postprocess_items(items)
    return items, total

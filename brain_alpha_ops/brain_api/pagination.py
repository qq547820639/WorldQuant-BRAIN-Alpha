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
    max_pages: int | None,
    max_items: int | None = None,
    progress_callback: Callable[[dict[str, Any]], Any] | None = None,
    progress_payload: Callable[..., dict[str, Any]] = _standard_pagination_progress,
    total_update: Callable[[Any, int, int], int] | None = None,
    page_error_recovery: Callable[[Exception, list[dict[str, Any]], dict[str, Any], int], dict[str, Any] | None] | None = None,
    postprocess_items: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
    stop_when_total_reached: bool = True,
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
        if progress_callback:
            payload = progress_payload(
                items,
                total,
                page_size=len(page_items),
                offset=offset,
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
        if stop_when_total_reached and total and len(items) >= total:
            break
        if max_items is not None and len(items) >= max_items:
            logger.warning("%s pagination reached max item limit (%d), total=%d", label, max_items, total)
            items = items[:max_items]
            break
        if len(page_items) < int(params["limit"]):
            break
        params["offset"] = offset + int(params["limit"])
    if postprocess_items:
        items = postprocess_items(items)
    return items, total


def _progress_cancelled(
    progress_callback: Callable[[dict[str, Any]], Any],
    payload: dict[str, Any],
) -> bool:
    return progress_callback(payload) is False

"""Patch properties and list user alphas mixin."""

from __future__ import annotations

from typing import Any

from .. import pagination as pagination_limits
from ..base import BrainAPIError
from ..official_helpers import (
    dedupe_alpha_items as _dedupe_alpha_items,
)
from ..official_helpers import (
    items as _items,
)
from ..official_helpers import (
    normal_alpha as _normal_alpha,
)
from ..official_helpers import (
    page_signature as _page_signature,
)
from ..official_helpers import (
    total_count as _total_count,
)
from ..official_helpers import (
    user_alpha_cursor_recovery as _user_alpha_cursor_recovery,
)
from ..official_helpers import (
    user_alpha_offset_recovery as _user_alpha_offset_recovery,
)
from ..official_helpers import (
    user_alpha_progress as _user_alpha_progress,
)
from ._helpers import (
    _USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS as _USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS,
)
from ._helpers import (
    _USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS as _USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS,
)
from ._helpers import (
    _is_user_alpha_transient_page_error,
)


class _AlphaQueryLifecycleMixin:

    def patch_properties(
        self,
        alpha_id: str,
        *,
        name: str | None = None,
        alpha_type: str | None = None,
        decay: int | None = None,
        neutralization: str | None = None,
        pasteurization: str | None = None,
        truncation: Any = None,
        unit_handling: str | None = None,
        nan_handling: str | None = None,
        hidden: bool | None = None,
        favorite: bool | None = None,
        category: str | None = None,
        color: str | None = None,
        tag: str | None = None,
        stage: str | None = None,
        **extra: Any,
    ) -> dict:
        """PATCH alpha properties on the BRAIN platform.

        Only non-None parameters are sent. Uses the standard
        ``/alphas/{alpha_id}`` endpoint with PATCH method, matching
        the WQB ``patch_properties`` API surface.
        """
        value = str(alpha_id or "").strip()
        if not value:
            raise BrainAPIError("alpha_id is required for patch_properties")
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if alpha_type is not None:
            body["type"] = alpha_type
        if decay is not None:
            body["decay"] = decay
        if neutralization is not None:
            body["neutralization"] = neutralization
        if pasteurization is not None:
            body["pasteurization"] = pasteurization
        if truncation is not None:
            body["truncation"] = truncation
        if unit_handling is not None:
            body["unitHandling"] = unit_handling
        if nan_handling is not None:
            body["nanHandling"] = nan_handling
        if hidden is not None:
            body["hidden"] = hidden
        if favorite is not None:
            body["favorite"] = favorite
        if category is not None:
            body["category"] = category
        if color is not None:
            body["color"] = color
        if tag is not None:
            body["tag"] = tag
        if stage is not None:
            body["stage"] = stage
        body.update(extra)
        if not body:
            raise BrainAPIError("patch_properties requires at least one property to update")
        # P1-3 fix: audit log for alpha property changes
        if hlr := self._hidden_for_audit_log():
            hlr.info("patch_properties: alpha_id=%s fields=%s", value, sorted(body.keys()))
        else:
            import logging
            logging.getLogger(__name__).info("patch_properties: alpha_id=%s fields=%s", value, sorted(body.keys()))
        path = self.config.alpha_path_template.format(alpha_id=value)
        data, _headers = self._request("PATCH", path, body=body)
        return _normal_alpha(data if isinstance(data, dict) else {})

    def list_user_alphas(
        self,
        sync_range: str = "all",
        progress_callback=None,
        *,
        force_refresh: bool = False,
    ) -> list[dict]:
        params = {"limit": 100, "offset": 0}
        range_days = {"3d": 3, "7d": 7, "recent": 30, "6months": 180}.get(sync_range)
        if range_days:
            params["days"] = range_days
        def user_alpha_progress(rows: list[dict[str, Any]], total: int, *, page_size: int, offset: int, **extra: Any) -> dict[str, Any]:
            return _user_alpha_progress(sync_range, rows, total, page_size=page_size, offset=offset, **extra)

        transient_retry_counts: dict[tuple[tuple[str, str], ...], int] = {}

        def recover_user_alpha_offset(
            exc: Exception,
            rows: list[dict[str, Any]],
            page_params: dict[str, Any],
            total: int,
        ) -> dict[str, Any] | None:
            recovery = _user_alpha_offset_recovery(exc, rows, page_params, sync_range=sync_range, total=total)
            if recovery:
                return {
                    "page_params": recovery["page_params"],
                    "progress": recovery["progress"],
                    "clear_seen": True,
                }
            status_code = getattr(exc, "status_code", None)
            if not _is_user_alpha_transient_page_error(exc):
                return None
            retry_key = tuple(sorted((str(key), str(value)) for key, value in page_params.items()))
            retry_attempt = transient_retry_counts.get(retry_key, 0) + 1
            retry_after = getattr(exc, "retry_after", None)
            try:
                retry_after_seconds = float(retry_after) if retry_after is not None else _USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS
            except (TypeError, ValueError):
                retry_after_seconds = _USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS
            retry_after_seconds = max(0.0, min(_USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS, retry_after_seconds))
            if retry_attempt > _USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS:
                recovery = _user_alpha_cursor_recovery(
                    rows,
                    page_params,
                    sync_range=sync_range,
                    total=total,
                    warning="transient_page_retry_narrowed_by_date",
                    retry_attempt=_USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS,
                    retry_exhausted=True,
                    retry_after_seconds=retry_after_seconds,
                    error_status=status_code,
                )
                if recovery:
                    return {
                        "page_params": recovery["page_params"],
                        "progress": recovery["progress"],
                        "clear_seen": True,
                        "total": max(total, len(rows)),
                        "sleep_seconds": retry_after_seconds,
                    }
                return None
            transient_retry_counts[retry_key] = retry_attempt
            return {
                "page_params": dict(page_params),
                "total": total,
                "progress": _user_alpha_progress(
                    sync_range,
                    rows,
                    max(total, len(rows)),
                    page_size=0,
                    offset=int(page_params.get("offset", 0) or 0),
                    warning="transient_page_retry",
                    retry_attempt=retry_attempt,
                    retry_after_seconds=retry_after_seconds,
                    error_status=status_code,
                ),
                "sleep_seconds": retry_after_seconds,
            }

        return self._cached_paginated_context(
            cache_name="user_alphas",
            cache_params=params,
            cache_label="user_alphas",
            cached_progress=lambda cached: _user_alpha_progress(
                sync_range,
                cached["items"],
                cached.get("total") or len(cached["items"]),
                cached=True,
                stale=False,
            ),
            progress_callback=progress_callback,
            progress_payload=user_alpha_progress,
            fresh_cache_is_partial=lambda cached: int(cached.get("total") or 0) > len(cached.get("items") or []),
            request_page=lambda page_params: self._request("GET", self.config.user_alphas_path, query=page_params),
            normalize_page=lambda data: [_normal_alpha(item) for item in _items(data)],
            signature_keys=("id", "expression", "created_at"),
            max_pages=pagination_limits.coerce_limit(pagination_limits.MAX_USER_ALPHAS_PAGES),
            total_update=lambda data, current, count: max(_total_count(data) or 0, current, count),
            page_error_recovery=recover_user_alpha_offset,
            postprocess_items=_dedupe_alpha_items,
            stop_when_total_reached=False,
            unique_item_key=lambda row: str(row.get("id") or "").strip(),
            stale_progress=lambda cached, exc: _user_alpha_progress(  # P2-4: generic warning
                sync_range,
                cached["items"],
                cached.get("total") or len(cached["items"]),
                cached=True,
                stale=True,
                warning=f"using stale cache due to API rate limit (status={getattr(exc, 'status_code', '?')})",
            ),
            use_cache=not force_refresh,
        )

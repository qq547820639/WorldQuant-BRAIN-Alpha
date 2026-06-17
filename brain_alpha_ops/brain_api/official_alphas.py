"""Alpha query and filter methods extracted from official_context.py.

These methods were part of OfficialContextDataMixin and are now provided
as a separate mixin class to keep official_context.py under the module-size limit.
"""

from __future__ import annotations

from . import pagination_limits
from .base import BrainAPIError
from .official_filtering import (
    clamp_query_limit,
    clamp_query_offset,
    normalize_wqb_options,
    resolve_compat_alias,
    resolve_compat_value,
)
from .official_helpers import (
    dedupe_alpha_items as _dedupe_alpha_items,
    items as _items,
    normal_alpha as _normal_alpha,
    normal_dataset as _normal_dataset,
    normal_field as _normal_field,
    page_signature as _page_signature,
    total_count as _total_count,
    user_alpha_cursor_recovery as _user_alpha_cursor_recovery,
    user_alpha_offset_recovery as _user_alpha_offset_recovery,
    user_alpha_progress as _user_alpha_progress,
)
from .pagination import _paginate_collection
from .official_query_params import (
    alpha_filter_params,
    apply_market_discovery_filters,
)

from typing import Any, Callable

# P2-4: transient retry constants centralised in user_alpha_transient.
# Kept as module-level aliases here so existing in-file references
# (``_USER_ALPHA_TRANSIENT_*``) keep working.
from .user_alpha_transient import (
    USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS as _USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS,
    USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS as _USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS,
    USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS as _USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS,
    USER_ALPHA_TRANSIENT_RETRY_STATUSES as _USER_ALPHA_TRANSIENT_RETRY_STATUSES,
)

_DISCOVERY_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay", "dataset"})
_ALPHA_FILTER_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay"})


def _is_user_alpha_transient_page_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in _USER_ALPHA_TRANSIENT_RETRY_STATUSES:
        return True
    if isinstance(exc, _USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS):
        return True
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, _USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS):
        return True
    if status_code is not None:
        return False
    text = str(exc).lower()
    return text.startswith("network error:") and any(
        marker in text
        for marker in (
            "urlopen error",
            "ssl",
            "eof",
            "timed out",
            "connection reset",
            "connection aborted",
            "remote end closed",
            "temporarily unavailable",
        )
    )


def _pop_compat_alias(filters: dict[str, Any], canonical: str, *aliases: str) -> Any:
    value = filters.pop(canonical, "")
    for alias in aliases:
        value = resolve_compat_alias(canonical, value, filters.pop(alias, ""), alias_name=alias)
    return value


def _compat_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


class AlphaQueryMixin:

    def locate_dataset(self, dataset_id: str) -> dict:
        value = str(dataset_id or "").strip()
        if not value:
            raise BrainAPIError("dataset_id is required")
        path = self.config.data_set_path_template.format(dataset_id=value)
        data, _headers = self._request("GET", path)
        return _normal_dataset(data if isinstance(data, dict) else {})

    def locate_field(self, field_id: str) -> dict:
        value = str(field_id or "").strip()
        if not value:
            raise BrainAPIError("field_id is required")
        path = self.config.data_field_path_template.format(field_id=value)
        data, _headers = self._request("GET", path)
        return _normal_field(data if isinstance(data, dict) else {})

    def locate_alpha(self, alpha_id: str) -> dict:
        value = str(alpha_id or "").strip()
        if not value:
            raise BrainAPIError("alpha_id is required")
        path = self.config.alpha_path_template.format(alpha_id=value)
        data, _headers = self._request("GET", path)
        return _normal_alpha(data if isinstance(data, dict) else {})

    def get_dataset(self, dataset_id: str = "", *, id: str = "") -> dict:
        return self.locate_dataset(resolve_compat_alias("dataset_id", dataset_id, id, alias_name="id"))

    def get_field(self, field_id: str = "", *, id: str = "") -> dict:
        return self.locate_field(resolve_compat_alias("field_id", field_id, id, alias_name="id"))

    def get_alpha(self, alpha_id: str = "", *, id: str = "") -> dict:
        return self.locate_alpha(resolve_compat_alias("alpha_id", alpha_id, id, alias_name="id"))

    def filter_alphas_limited(
        self,
        *,
        name: str = "",
        competition: str = "",
        alpha_type: str = "",
        type: str = "",
        status: str = "",
        date_created: Any = None,
        instrument_type: str = "",
        region: str = "",
        universe: str = "",
        delay: int | None = None,
        sharpe: Any = None,
        fitness: Any = None,
        turnover: Any = None,
        prod_correlation: Any = None,
        self_correlation: Any = None,
        returns: Any = None,
        pnl: Any = None,
        drawdown: Any = None,
        margin: Any = None,
        book_size: Any = None,
        long_count: Any = None,
        short_count: Any = None,
        os_sharpe: Any = None,
        os_fitness: Any = None,
        os_turnover: Any = None,
        os_returns: Any = None,
        os_pnl: Any = None,
        os_drawdown: Any = None,
        os_margin: Any = None,
        os_long_count: Any = None,
        os_short_count: Any = None,
        date_submitted: Any = None,
        start_date: Any = None,
        language: str = "",
        decay: int | None = None,
        neutralization: str = "",
        pasteurization: str = "",
        truncation: Any = None,
        unit_handling: str = "",
        nan_handling: str = "",
        hidden: bool | None = None,
        favorite: bool | None = None,
        category: str = "",
        color: str = "",
        tag: str = "",
        stage: str = "",
        order: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        page_limit = clamp_query_limit(limit, maximum=100, label="user alpha")
        page_offset = clamp_query_offset(offset, limit=page_limit, max_window=10_000, label="user alpha")
        params = alpha_filter_params(
            name=name,
            competition=competition,
            alpha_type=alpha_type,
            type=type,
            status=status,
            date_created=date_created,
            instrument_type=instrument_type,
            region=region,
            universe=universe,
            delay=delay,
            sharpe=sharpe,
            fitness=fitness,
            turnover=turnover,
            prod_correlation=prod_correlation,
            self_correlation=self_correlation,
            returns=returns,
            pnl=pnl,
            drawdown=drawdown,
            margin=margin,
            book_size=book_size,
            long_count=long_count,
            short_count=short_count,
            os_sharpe=os_sharpe,
            os_fitness=os_fitness,
            os_turnover=os_turnover,
            os_returns=os_returns,
            os_pnl=os_pnl,
            os_drawdown=os_drawdown,
            os_margin=os_margin,
            os_long_count=os_long_count,
            os_short_count=os_short_count,
            date_submitted=date_submitted,
            start_date=start_date,
            language=language,
            decay=decay,
            neutralization=neutralization,
            pasteurization=pasteurization,
            truncation=truncation,
            unit_handling=unit_handling,
            nan_handling=nan_handling,
            hidden=hidden,
            favorite=favorite,
            category=category,
            color=color,
            tag=tag,
            stage=stage,
            order=order,
            limit=page_limit,
            offset=page_offset,
        )
        data, headers = self._request("GET", self.config.user_alphas_path, query=params)
        return {
            "items": [_normal_alpha(item) for item in _items(data)],
            "count": _total_count(data),
            "limit": page_limit,
            "offset": page_offset,
            "headers": headers,
            "raw": data,
        }

    def query_alphas_limited(self, *, options: dict[str, Any] | None = None, **filters: Any) -> dict[str, Any]:
        return self.filter_alphas_limited(**self._normalize_alpha_filter_compat(filters, options))

    def filter_alphas(self, progress_callback=None, **filters: Any) -> list[dict]:
        limit = clamp_query_limit(filters.pop("limit", 100), maximum=100, label="user alpha")
        offset = clamp_query_offset(filters.pop("offset", 0), limit=limit, max_window=10_000, label="user alpha")
        params = alpha_filter_params(**filters, limit=limit, offset=offset)
        rows: list[dict[str, Any]] = []
        total = 0
        seen_page_signatures: set[str] = set()
        while True:
            current_offset = int(params.get("offset", 0) or 0)
            remaining_window = 10_000 - current_offset
            if remaining_window <= 0:
                break
            page_limit = min(limit, remaining_window)
            params["limit"] = page_limit
            data, _headers = self._request("GET", self.config.user_alphas_path, query=params)
            page_items = [_normal_alpha(item) for item in _items(data)]
            api_count = _total_count(data)
            if api_count > 0:
                total = api_count
            signature = _page_signature(page_items, keys=("id", "expression", "created_at"))
            repeated_page = bool(page_items and signature in seen_page_signatures)
            if page_items:
                seen_page_signatures.add(signature)
            rows.extend(page_items)
            next_offset = current_offset + page_limit
            filter_window_count = min(total, 10_000) if total > 0 else 0
            progress_payload = {
                "scanned": len(rows),
                "total": total,
                "api_reported_total": total,
                "filter_window_count": filter_window_count,
                "page_size": len(page_items),
                "page_limit": page_limit,
                "offset": current_offset,
                "next_offset": next_offset,
                "pagination_target": "api_filter_window",
                "window_limit": 10_000,
                "has_more": False,
                "pagination_complete": True,
            }
            if repeated_page:
                progress_payload.update({
                    "warning": "repeated_page",
                    "truncated": True,
                    "stop_reason": "repeated_page",
                })
            elif total > 0 and next_offset >= total:
                progress_payload["stop_reason"] = "api_total_reached"
            elif len(page_items) < page_limit:
                progress_payload["stop_reason"] = "short_page"
            elif next_offset >= 10_000:
                progress_payload["stop_reason"] = "filter_window_exhausted"
            else:
                progress_payload["has_more"] = True
                progress_payload["pagination_complete"] = False
            if progress_callback and progress_callback(progress_payload) is False:
                break
            if progress_payload["pagination_complete"]:
                break
            params["offset"] = next_offset
        return _dedupe_alpha_items(rows)

    def query_alphas(self, progress_callback=None, *, options: dict[str, Any] | None = None, **filters: Any) -> list[dict]:
        return self.filter_alphas(
            progress_callback=progress_callback,
            **self._normalize_alpha_filter_compat(filters, options),
        )

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
        path = self.config.alpha_path_template.format(alpha_id=value)
        data, _headers = self._request("PATCH", path, body=body)
        return _normal_alpha(data if isinstance(data, dict) else {})

    def _normalize_alpha_filter_compat(
        self,
        filters: dict[str, Any],
        options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        options_data = normalize_wqb_options(options, allowed=_ALPHA_FILTER_OPTION_KEYS)
        normalized = dict(filters)
        instrument_type = _pop_compat_alias(normalized, "instrument_type", "instrumentType")
        normalized["instrument_type"] = resolve_compat_value(
            "instrument_type",
            instrument_type,
            options_data,
        )
        normalized["region"] = resolve_compat_value("region", normalized.get("region", ""), options_data)
        normalized["universe"] = resolve_compat_value("universe", normalized.get("universe", ""), options_data)
        normalized["delay"] = resolve_compat_value("delay", normalized.get("delay"), options_data)
        return normalized

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

"""Official context collection methods for the BRAIN API adapter."""

from __future__ import annotations

from typing import Any, Callable


from . import pagination_limits
from .base import BrainAPIError
from .official_alphas import AlphaQueryMixin, _compat_blank, _pop_compat_alias
from .official_filtering import (
    clamp_query_limit,
    clamp_query_offset,
    normalize_wqb_options,
    resolve_compat_alias,
    resolve_compat_value,
)
from .official_helpers import (
    dedupe_alpha_items as _dedupe_alpha_items,
)
from .official_helpers import (
    items as _items,
)
from .official_helpers import (
    looks_partial_context_cache as _looks_partial_context_cache,
)
from .official_helpers import (
    normal_data_category as _normal_data_category,
)
from .official_helpers import (
    normal_dataset as _normal_dataset,
)
from .official_helpers import (
    normal_field as _normal_field,
)
from .official_helpers import (
    normal_operator as _normal_operator,
)
from .official_helpers import (
    page_signature as _page_signature,
)
from .official_helpers import (
    total_count as _total_count,
)
from .official_query_params import (
    apply_market_discovery_filters,
)
from .pagination import _paginate_collection

_DISCOVERY_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay", "dataset"})
_ALPHA_FILTER_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay"})


class OfficialContextDataMixin(AlphaQueryMixin):
    def _market_context_params(
        self,
        query: str,
        region: str,
        limit: int,
        *,
        dataset: str = "",
        include_dataset: bool = False,
        include_scope_dataset: bool = False,
        instrument_type: str = "",
    ) -> dict[str, Any]:
        scope_region = region or self._market_scope.get("region", "USA")
        params = {
            "instrumentType": instrument_type or self._market_scope.get("instrumentType", "EQUITY"),
            "region": scope_region,
            "delay": int(self._market_scope.get("delay", 1)),
            "universe": self._market_scope.get("universe", "TOP3000"),
            "limit": limit,
            "offset": 0,
        }
        dataset_filter = dataset or (self._market_scope.get("dataset", "") if include_scope_dataset else "")
        if include_dataset and dataset_filter:
            dataset_key = str(getattr(self.config, "data_fields_dataset_query_key", "dataset") or "dataset")
            params[dataset_key] = dataset_filter
        if query and query != "all":
            params["search"] = query
        return params

    def _cached_paginated_context(
        self,
        *,
        cache_name: str,
        cache_params: dict[str, Any],
        cache_label: str,
        cached_progress: Callable[[dict[str, Any]], Any] | None,
        progress_callback,
        progress_payload: Callable[..., dict[str, Any]] | None,
        fresh_cache_is_partial: Callable[[dict[str, Any]], bool],
        request_page: Callable[[dict[str, Any]], tuple[Any, Any]],
        normalize_page: Callable[[Any], list[dict[str, Any]]],
        signature_keys: tuple[str, ...],
        max_pages: int | None,
        max_items: int | None = None,
        total_update: Callable[[Any, int, int], int] | None = None,
        page_error_recovery: Callable[[Exception, list[dict[str, Any]], dict[str, Any], int], dict[str, Any] | None] | None = None,
        postprocess_items: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
        stop_when_total_reached: bool = True,
        confirm_full_page_at_total_boundary: bool = False,
        unique_item_key: Callable[[dict[str, Any]], str] | None = None,
        stale_progress: Callable[[dict[str, Any], Exception], dict[str, Any] | None] | None = None,
        write_total: Callable[[list[dict[str, Any]], int], int] | None = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        cache_key = self._cache_key(cache_name, cache_params)
        cached = self._read_cache(cache_key) if use_cache else {"items": [], "fresh": False, "missing": True}
        if cached["fresh"] and not fresh_cache_is_partial(cached):
            if progress_callback and cached_progress:
                progress_callback(cached_progress(cached))
            return cached["items"]
        try:
            paginate_kwargs = {
                "label": cache_label,
                "page_params": cache_params,
                "request_page": request_page,
                "normalize_page": normalize_page,
                "signature_keys": signature_keys,
                "max_pages": max_pages,
                "max_items": max_items,
                "progress_callback": progress_callback,
                "total_update": total_update,
                "page_error_recovery": page_error_recovery,
                "postprocess_items": postprocess_items,
                "stop_when_total_reached": stop_when_total_reached,
                "confirm_full_page_at_total_boundary": confirm_full_page_at_total_boundary,
                "unique_item_key": unique_item_key,
            }
            if progress_payload is not None:
                paginate_kwargs["progress_payload"] = progress_payload
            items, total = _paginate_collection(**paginate_kwargs)
            total_for_cache = write_total(items, total) if write_total else max(total, len(items))
            self._write_cache(cache_key, items, total_for_cache)
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                if progress_callback and stale_progress:
                    payload = stale_progress(cached, exc)
                    if payload:
                        progress_callback(payload)
                return cached["items"]
            raise

    def list_fields(self, query: str = "all", region: str = "", dataset: str = "", progress_callback=None) -> list[dict]:
        params = self._market_context_params(query, region, 50, dataset=dataset, include_dataset=True)
        return self._cached_paginated_context(
            cache_name="fields",
            cache_params=params,
            cache_label="fields",
            cached_progress=lambda cached: {"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True},
            progress_callback=progress_callback,
            progress_payload=None,
            fresh_cache_is_partial=lambda cached: _looks_partial_context_cache("fields", cached["items"], cached.get("total", 0), params["limit"]),
            request_page=lambda page_params: self._request("GET", self.config.data_fields_path, query=page_params),
            normalize_page=lambda data: [_normal_field(item) for item in _items(data)],
            signature_keys=("name", "category"),
            max_pages=pagination_limits.coerce_limit(pagination_limits.MAX_FIELDS_PAGES),
            max_items=pagination_limits.coerce_limit(pagination_limits.MAX_FIELDS_ITEMS),
            confirm_full_page_at_total_boundary=True,
        )

    def list_datasets(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        params = self._market_context_params(query, region, 50)
        return self._cached_paginated_context(
            cache_name="datasets",
            cache_params=params,
            cache_label="datasets",
            cached_progress=lambda cached: {"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True},
            progress_callback=progress_callback,
            progress_payload=None,
            fresh_cache_is_partial=lambda cached: _looks_partial_context_cache("datasets", cached["items"], cached.get("total", 0), params["limit"]),
            request_page=lambda page_params: self._request("GET", self.config.data_sets_path, query=page_params),
            normalize_page=lambda data: [
                row
                for row in (_normal_dataset(item) for item in _items(data))
                if row.get("id")
            ],
            signature_keys=("id", "name"),
            max_pages=pagination_limits.coerce_limit(pagination_limits.MAX_DATASETS_PAGES),
            max_items=pagination_limits.coerce_limit(pagination_limits.MAX_DATASETS_ITEMS),
            postprocess_items=_dedupe_alpha_items,
            confirm_full_page_at_total_boundary=True,
        )

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        params = {"search": query if query != "all" else "", "limit": 100, "offset": 0}
        return self._cached_paginated_context(
            cache_name="operators",
            cache_params=params,
            cache_label="operators",
            cached_progress=lambda cached: {"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True},
            progress_callback=progress_callback,
            progress_payload=None,
            fresh_cache_is_partial=lambda cached: _looks_partial_context_cache("operators", cached["items"], cached.get("total", 0), params["limit"]),
            request_page=lambda page_params: self._request("GET", self.config.operators_path, query=page_params),
            normalize_page=lambda data: [_normal_operator(item) for item in _items(data)],
            signature_keys=("name", "category"),
            max_pages=pagination_limits.coerce_limit(pagination_limits.MAX_OPERATORS_PAGES),
            max_items=pagination_limits.coerce_limit(pagination_limits.MAX_OPERATORS_ITEMS),
            confirm_full_page_at_total_boundary=True,
        )

    def list_data_categories(self, progress_callback=None) -> list[dict]:
        data, _headers = self._request("GET", self.config.data_categories_path)
        rows = [_normal_data_category(item) for item in _items(data)]
        if progress_callback:
            progress_callback({
                "scanned": len(rows),
                "total": len(rows),
                "pagination_target": "single_collection",
                "pagination_complete": True,
            })
        return rows

    def search_datasets_limited(
        self,
        query: str = "all",
        region: str = "",
        *,
        instrument_type: str = "",
        category: str = "",
        universe: str = "",
        delay: int | None = None,
        coverage: Any = None,
        value_score: Any = None,
        alpha_count: Any = None,
        user_count: Any = None,
        order: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        page_limit = clamp_query_limit(limit, maximum=50, label="data-sets")
        page_offset = clamp_query_offset(offset, limit=page_limit, max_window=10_000, label="data-sets")
        params = self._market_context_params(query, region, page_limit, instrument_type=instrument_type)
        apply_market_discovery_filters(
            params,
            category=category,
            universe=universe,
            delay=delay,
            coverage=coverage,
            value_score=value_score,
            alpha_count=alpha_count,
            user_count=user_count,
            order=order,
        )
        params["offset"] = page_offset
        data, headers = self._request("GET", self.config.data_sets_path, query=params)
        return {
            "items": [
                row
                for row in (_normal_dataset(item) for item in _items(data))
                if row.get("id")
            ],
            "count": _total_count(data),
            "limit": page_limit,
            "offset": page_offset,
            "headers": headers,
            "raw": data,
        }

    def search_datasets(
        self,
        query: str = "all",
        region: str = "",
        *,
        instrument_type: str = "",
        category: str = "",
        universe: str = "",
        delay: int | None = None,
        coverage: Any = None,
        value_score: Any = None,
        alpha_count: Any = None,
        user_count: Any = None,
        order: str = "",
        limit: int = 50,
        offset: int = 0,
        progress_callback=None,
    ) -> list[dict]:
        return self._collect_limited_search_pages(
            lambda page_limit, page_offset: self.search_datasets_limited(
                query,
                region,
                instrument_type=instrument_type,
                category=category,
                universe=universe,
                delay=delay,
                coverage=coverage,
                value_score=value_score,
                alpha_count=alpha_count,
                user_count=user_count,
                order=order,
                limit=page_limit,
                offset=page_offset,
            ),
            label="data-sets",
            limit=limit,
            offset=offset,
            progress_callback=progress_callback,
        )

    def discover_datasets_limited(
        self,
        query: str = "all",
        region: str = "",
        *,
        options: dict[str, Any] | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        options_data = normalize_wqb_options(options, allowed=_DISCOVERY_OPTION_KEYS)
        region_value = resolve_compat_value("region", region, options_data)
        filters = dict(filters)
        instrument_type = _pop_compat_alias(filters, "instrument_type", "instrumentType")
        filters["instrument_type"] = resolve_compat_value("instrument_type", instrument_type, options_data)
        filters["universe"] = resolve_compat_value("universe", filters.get("universe", ""), options_data)
        filters["delay"] = resolve_compat_value("delay", filters.get("delay"), options_data)
        if options_data.get("dataset"):
            raise BrainAPIError("dataset option is only supported for field discovery")
        return self.search_datasets_limited(query, region_value or "", **filters)

    def discover_datasets(
        self,
        query: str = "all",
        region: str = "",
        *,
        options: dict[str, Any] | None = None,
        progress_callback=None,
        **filters: Any,
    ) -> list[dict]:
        options_data = normalize_wqb_options(options, allowed=_DISCOVERY_OPTION_KEYS)
        region_value = resolve_compat_value("region", region, options_data)
        filters = dict(filters)
        instrument_type = _pop_compat_alias(filters, "instrument_type", "instrumentType")
        filters["instrument_type"] = resolve_compat_value("instrument_type", instrument_type, options_data)
        filters["universe"] = resolve_compat_value("universe", filters.get("universe", ""), options_data)
        filters["delay"] = resolve_compat_value("delay", filters.get("delay"), options_data)
        if options_data.get("dataset"):
            raise BrainAPIError("dataset option is only supported for field discovery")
        return self.search_datasets(
            query,
            region_value or "",
            progress_callback=progress_callback,
            **filters,
        )

    def search_fields_limited(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        instrument_type: str = "",
        field_type: str = "",
        category: str = "",
        universe: str = "",
        delay: int | None = None,
        coverage: Any = None,
        value_score: Any = None,
        alpha_count: Any = None,
        user_count: Any = None,
        order: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        page_limit = clamp_query_limit(limit, maximum=50, label="data-fields")
        page_offset = clamp_query_offset(offset, limit=page_limit, max_window=10_000, label="data-fields")
        params = self._market_context_params(
            query,
            region,
            page_limit,
            dataset=dataset,
            include_dataset=True,
            instrument_type=instrument_type,
        )
        if field_type:
            params["type"] = field_type
        apply_market_discovery_filters(
            params,
            category=category,
            universe=universe,
            delay=delay,
            coverage=coverage,
            value_score=value_score,
            alpha_count=alpha_count,
            user_count=user_count,
            order=order,
        )
        params["offset"] = page_offset
        data, headers = self._request("GET", self.config.data_fields_path, query=params)
        return {
            "items": [_normal_field(item) for item in _items(data)],
            "count": _total_count(data),
            "limit": page_limit,
            "offset": page_offset,
            "headers": headers,
            "raw": data,
        }

    def search_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        instrument_type: str = "",
        field_type: str = "",
        category: str = "",
        universe: str = "",
        delay: int | None = None,
        coverage: Any = None,
        value_score: Any = None,
        alpha_count: Any = None,
        user_count: Any = None,
        order: str = "",
        limit: int = 50,
        offset: int = 0,
        progress_callback=None,
    ) -> list[dict]:
        return self._collect_limited_search_pages(
            lambda page_limit, page_offset: self.search_fields_limited(
                query,
                region,
                dataset=dataset,
                instrument_type=instrument_type,
                field_type=field_type,
                category=category,
                universe=universe,
                delay=delay,
                coverage=coverage,
                value_score=value_score,
                alpha_count=alpha_count,
                user_count=user_count,
                order=order,
                limit=page_limit,
                offset=page_offset,
            ),
            label="data-fields",
            limit=limit,
            offset=offset,
            progress_callback=progress_callback,
        )

    def discover_fields_limited(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        dataset_id: str = "",
        options: dict[str, Any] | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        options_data = normalize_wqb_options(options, allowed=_DISCOVERY_OPTION_KEYS)
        filters = dict(filters)
        region_value = resolve_compat_value("region", region, options_data)
        instrument_type = _pop_compat_alias(filters, "instrument_type", "instrumentType")
        filters["instrument_type"] = resolve_compat_value("instrument_type", instrument_type, options_data)
        dataset_alias = _pop_compat_alias(filters, "dataset", "datasetId", "dataSetId", "data_set_id")
        dataset_value = resolve_compat_value(
            "dataset",
            resolve_compat_alias(
                "dataset",
                resolve_compat_alias("dataset", dataset, dataset_id, alias_name="dataset_id"),
                dataset_alias,
                alias_name="dataset",
            ),
            options_data,
        )
        filters["universe"] = resolve_compat_value("universe", filters.get("universe", ""), options_data)
        filters["delay"] = resolve_compat_value("delay", filters.get("delay"), options_data)
        field_type = _pop_compat_alias(filters, "field_type", "type")
        if not _compat_blank(field_type):
            filters["field_type"] = field_type
        return self.search_fields_limited(
            query,
            region_value or "",
            dataset=dataset_value or "",
            **filters,
        )

    def discover_fields(
        self,
        query: str = "all",
        region: str = "",
        dataset: str = "",
        *,
        dataset_id: str = "",
        options: dict[str, Any] | None = None,
        progress_callback=None,
        **filters: Any,
    ) -> list[dict]:
        options_data = normalize_wqb_options(options, allowed=_DISCOVERY_OPTION_KEYS)
        filters = dict(filters)
        region_value = resolve_compat_value("region", region, options_data)
        instrument_type = _pop_compat_alias(filters, "instrument_type", "instrumentType")
        filters["instrument_type"] = resolve_compat_value("instrument_type", instrument_type, options_data)
        dataset_alias = _pop_compat_alias(filters, "dataset", "datasetId", "dataSetId", "data_set_id")
        dataset_value = resolve_compat_value(
            "dataset",
            resolve_compat_alias(
                "dataset",
                resolve_compat_alias("dataset", dataset, dataset_id, alias_name="dataset_id"),
                dataset_alias,
                alias_name="dataset",
            ),
            options_data,
        )
        filters["universe"] = resolve_compat_value("universe", filters.get("universe", ""), options_data)
        filters["delay"] = resolve_compat_value("delay", filters.get("delay"), options_data)
        field_type = _pop_compat_alias(filters, "field_type", "type")
        if not _compat_blank(field_type):
            filters["field_type"] = field_type
        return self.search_fields(
            query,
            region_value or "",
            dataset=dataset_value or "",
            progress_callback=progress_callback,
            **filters,
        )

    def _collect_limited_search_pages(
        self,
        fetch_page: Callable[[int, int], dict[str, Any]],
        *,
        label: str,
        limit: int,
        offset: int,
        progress_callback=None,
    ) -> list[dict]:
        page_limit = clamp_query_limit(limit, maximum=50, label=label)
        page_offset = clamp_query_offset(offset, limit=page_limit, max_window=10_000, label=label)
        count_page = fetch_page(1, page_offset)
        api_count = max(0, int(count_page.get("count") or 0))
        rows: list[dict[str, Any]] = []
        seen_page_signatures: set[str] = set()
        current_offset = page_offset
        target_end = min(api_count, 10_000)
        if current_offset >= target_end:
            if progress_callback:
                progress_callback({
                    "scanned": 0,
                    "total": api_count,
                    "api_reported_total": api_count,
                    "filter_window_count": api_count,
                    "page_size": 0,
                    "page_limit": page_limit,
                    "offset": current_offset,
                    "next_offset": current_offset,
                    "pagination_target": "api_filter_window",
                    "window_limit": 10_000,
                    "has_more": False,
                    "pagination_complete": True,
                    "stop_reason": "api_total_reached",
                })
            return []
        while current_offset < target_end:
            remaining_window = 10_000 - current_offset
            if remaining_window <= 0:
                break
            current_limit = min(page_limit, remaining_window, target_end - current_offset)
            page = fetch_page(current_limit, current_offset)
            page_items = list(page.get("items") or [])
            page_count = max(0, int(page.get("count") or 0))
            if page_count > 0:
                api_count = page_count
                target_end = min(api_count, 10_000)
            signature = _page_signature(page_items, keys=("id", "name"))
            repeated_page = bool(page_items and signature in seen_page_signatures)
            if page_items:
                seen_page_signatures.add(signature)
            rows.extend(page_items)
            next_offset = current_offset + current_limit
            progress_payload = {
                "scanned": len(rows),
                "total": api_count,
                "api_reported_total": api_count,
                "filter_window_count": api_count,
                "page_size": len(page_items),
                "page_limit": current_limit,
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
            elif next_offset >= target_end:
                progress_payload["stop_reason"] = "api_total_reached"
            elif len(page_items) < current_limit:
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
            current_offset = next_offset
        return _dedupe_alpha_items(rows)


# ═════════════════════════════════════════════════════════════════════
# Phase 3.2 (W-08): Dynamic gate threshold polling infrastructure.
# Provides optional BRAIN API-driven threshold refresh with static
# fallback. Enabled via `threshold_mode: "dynamic"` in run_config.json.
# ═════════════════════════════════════════════════════════════════════

def fetch_official_thresholds(
    api: Any,
    *,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Poll BRAIN API for current quality gate thresholds.

    Returns a dict with min_sharpe, min_fitness, max_turnover, etc.
    Falls back to an empty dict on any error — callers should merge
    with their static QualityThresholds defaults.

    This is a best-effort advisory function: failure here MUST NOT
    block pipeline startup or gate evaluation.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        raw = api._request("GET", "/data-check", timeout=timeout_seconds) or {}
    except Exception as exc:
        from brain_alpha_ops.redaction import redact_error_message
        logger.info(
            "Dynamic threshold fetch failed (static defaults will be used): %s",
            redact_error_message(exc, max_length=160),
        )
        return {}
    if not isinstance(raw, dict):
        return {}
    checks = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
    thresholds: dict[str, Any] = {}
    for check_name, check_data in checks.items():
        if not isinstance(check_data, dict):
            continue
        value = check_data.get("threshold")
        if value is not None:
            thresholds[check_name] = value
    return thresholds


def merge_dynamic_thresholds(
    static_thresholds: Any,
    dynamic_data: dict[str, Any],
) -> dict[str, Any]:
    """Merge dynamic BRAIN API thresholds into static QualityThresholds.

    Only updates fields that are present in the dynamic response;
    all other values remain unchanged.
    """
    import dataclasses
    if not dynamic_data:
        return dataclasses.asdict(static_thresholds) if dataclasses.is_dataclass(static_thresholds) else dict(static_thresholds)
    merged = dataclasses.asdict(static_thresholds) if dataclasses.is_dataclass(static_thresholds) else dict(static_thresholds)

    mapping = {
        "LOW_SHARPE": ("min_sharpe", "min_sharpe_delay0"),
        "LOW_FITNESS": ("min_fitness", "min_fitness_delay0"),
        "HIGH_TURNOVER": ("platform_max_turnover",),
        "SELF_CORRELATION": ("max_self_correlation",),
        "CONCENTRATED_WEIGHT": ("max_weight_concentration",),
        "LOW_SUB_UNIVERSE_SHARPE": ("sub_universe_sharpe_min_ratio",),
    }
    for check_name, threshold_value in dynamic_data.items():
        fields = mapping.get(check_name)
        if not fields:
            continue
        try:
            numeric = float(threshold_value)
        except (TypeError, ValueError):
            continue
        for field in fields:
            merged[field] = numeric

    return merged

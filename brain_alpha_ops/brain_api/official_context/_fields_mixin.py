"""Field-fetching context mixin for the BRAIN API adapter."""

from __future__ import annotations

from typing import Any, Callable


from .. import pagination as pagination_limits
from ..official_alphas import _compat_blank, _pop_compat_alias
from ..official_filtering import (
    clamp_query_limit,
    clamp_query_offset,
    normalize_wqb_options,
    resolve_compat_alias,
    resolve_compat_value,
)
from ..official_helpers import (
    items as _items,
)
from ..official_helpers import (
    looks_partial_context_cache as _looks_partial_context_cache,
)
from ..official_helpers import (
    normal_field as _normal_field,
)
from ..official_helpers import (
    page_signature as _page_signature,
)
from ..official_helpers import (
    total_count as _total_count,
)
from ..official_query_params import (
    apply_market_discovery_filters,
)

_DISCOVERY_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay", "dataset"})


class _FieldsContextMixin:
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

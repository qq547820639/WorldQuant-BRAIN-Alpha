"""Dataset-fetching context mixin for the BRAIN API adapter."""

from __future__ import annotations

from typing import Any, Callable


from .. import pagination_limits
from ..base import BrainAPIError
from ..official_alphas import _compat_blank, _pop_compat_alias
from ..official_filtering import (
    clamp_query_limit,
    clamp_query_offset,
    normalize_wqb_options,
    resolve_compat_alias,
    resolve_compat_value,
)
from ..official_helpers import (
    dedupe_alpha_items as _dedupe_alpha_items,
)
from ..official_helpers import (
    items as _items,
)
from ..official_helpers import (
    looks_partial_context_cache as _looks_partial_context_cache,
)
from ..official_helpers import (
    normal_dataset as _normal_dataset,
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


class _DatasetsContextMixin:
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

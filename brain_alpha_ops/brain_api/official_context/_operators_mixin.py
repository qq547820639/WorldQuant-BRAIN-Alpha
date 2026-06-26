"""Operator-fetching context mixin for the BRAIN API adapter."""

from __future__ import annotations


from .. import pagination_limits
from ..official_helpers import (
    items as _items,
)
from ..official_helpers import (
    looks_partial_context_cache as _looks_partial_context_cache,
)
from ..official_helpers import (
    normal_data_category as _normal_data_category,
)
from ..official_helpers import (
    normal_operator as _normal_operator,
)


class _OperatorsContextMixin:
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

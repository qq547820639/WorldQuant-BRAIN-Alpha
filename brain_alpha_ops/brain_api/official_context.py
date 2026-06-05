"""Official context collection methods for the BRAIN API adapter."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.redaction import redact_error_message

from . import pagination_limits
from .base import BrainAPIError
from .official_helpers import (
    dedupe_alpha_items as _dedupe_alpha_items,
    items as _items,
    looks_partial_context_cache as _looks_partial_context_cache,
    normal_alpha as _normal_alpha,
    normal_dataset as _normal_dataset,
    normal_field as _normal_field,
    normal_operator as _normal_operator,
    total_count as _total_count,
    user_alpha_offset_recovery as _user_alpha_offset_recovery,
    user_alpha_progress as _user_alpha_progress,
)
from .pagination import _paginate_collection


class OfficialContextDataMixin:
    def _market_context_params(self, query: str, region: str, limit: int, *, dataset: str = "") -> dict[str, Any]:
        scope_region = region or self._market_scope.get("region", "USA")
        params = {
            "instrumentType": self._market_scope.get("instrumentType", "EQUITY"),
            "region": scope_region,
            "delay": int(self._market_scope.get("delay", 1)),
            "universe": self._market_scope.get("universe", "TOP3000"),
            "limit": limit,
            "offset": 0,
        }
        if dataset or self._market_scope.get("dataset"):
            params["dataset"] = dataset or self._market_scope.get("dataset", "")
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
        unique_item_key: Callable[[dict[str, Any]], str] | None = None,
        stale_progress: Callable[[dict[str, Any], Exception], dict[str, Any] | None] | None = None,
        write_total: Callable[[list[dict[str, Any]], int], int] | None = None,
    ) -> list[dict[str, Any]]:
        cache_key = self._cache_key(cache_name, cache_params)
        cached = self._read_cache(cache_key)
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
        params = self._market_context_params(query, region, 50, dataset=dataset)
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
        )

    def list_user_alphas(self, sync_range: str = "3d", progress_callback=None) -> list[dict]:
        params = {"limit": 100, "offset": 0}
        if sync_range in {"3d", "7d"}:
            params["days"] = 3 if sync_range == "3d" else 7
        def user_alpha_progress(rows: list[dict[str, Any]], total: int, *, page_size: int, offset: int, **extra: Any) -> dict[str, Any]:
            return _user_alpha_progress(sync_range, rows, total, page_size=page_size, offset=offset, **extra)

        def recover_user_alpha_offset(
            exc: Exception,
            rows: list[dict[str, Any]],
            page_params: dict[str, Any],
            total: int,
        ) -> dict[str, Any] | None:
            recovery = _user_alpha_offset_recovery(exc, rows, page_params, sync_range=sync_range, total=total)
            if not recovery:
                return None
            return {
                "page_params": recovery["page_params"],
                "progress": recovery["progress"],
                "clear_seen": True,
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
            fresh_cache_is_partial=lambda _cached: False,
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
        )

"""Official context collection methods for the BRAIN API adapter."""

from __future__ import annotations

import sys
from typing import Any

from brain_alpha_ops.redaction import redact_error_message

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


_MAX_FIELDS_PAGES = 200
_MAX_DATASETS_PAGES = 20
_MAX_OPERATORS_PAGES = 20
_MAX_USER_ALPHAS_PAGES = 500
_MAX_FIELDS_ITEMS = 20_000
_MAX_DATASETS_ITEMS = 2_000
_MAX_OPERATORS_ITEMS = 2_000


def _official_limit(name: str, default: int) -> int:
    official_module = sys.modules.get("brain_alpha_ops.brain_api.official")
    value = getattr(official_module, name, default) if official_module is not None else default
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


class OfficialContextDataMixin:
    def list_fields(self, query: str = "all", region: str = "", dataset: str = "", progress_callback=None) -> list[dict]:
        scope_region = region or self._market_scope.get("region", "USA")
        params = {
            "instrumentType": self._market_scope.get("instrumentType", "EQUITY"),
            "region": scope_region,
            "delay": int(self._market_scope.get("delay", 1)),
            "universe": self._market_scope.get("universe", "TOP3000"),
            "limit": 50,
            "offset": 0,
        }
        if dataset or self._market_scope.get("dataset"):
            params["dataset"] = dataset or self._market_scope.get("dataset", "")
        if query and query != "all":
            params["search"] = query
        cache_key = self._cache_key("fields", params)
        cached = self._read_cache(cache_key)
        if cached["fresh"] and not _looks_partial_context_cache("fields", cached["items"], cached.get("total", 0), params["limit"]):
            if progress_callback:
                progress_callback({"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True})
            return cached["items"]
        try:
            items, total = _paginate_collection(
                label="fields",
                page_params=params,
                request_page=lambda page_params: self._request("GET", self.config.data_fields_path, query=page_params),
                normalize_page=lambda data: [_normal_field(item) for item in _items(data)],
                signature_keys=("name", "category"),
                max_pages=_official_limit("_MAX_FIELDS_PAGES", _MAX_FIELDS_PAGES),
                max_items=_official_limit("_MAX_FIELDS_ITEMS", _MAX_FIELDS_ITEMS),
                progress_callback=progress_callback,
            )
            self._write_cache(cache_key, items, max(total, len(items)))
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                return cached["items"]
            raise

    def list_datasets(self, query: str = "all", region: str = "", progress_callback=None) -> list[dict]:
        scope_region = region or self._market_scope.get("region", "USA")
        params = {
            "instrumentType": self._market_scope.get("instrumentType", "EQUITY"),
            "region": scope_region,
            "delay": int(self._market_scope.get("delay", 1)),
            "universe": self._market_scope.get("universe", "TOP3000"),
            "limit": 50,
            "offset": 0,
        }
        if query and query != "all":
            params["search"] = query
        cache_key = self._cache_key("datasets", params)
        cached = self._read_cache(cache_key)
        if cached["fresh"] and not _looks_partial_context_cache("datasets", cached["items"], cached.get("total", 0), params["limit"]):
            if progress_callback:
                progress_callback({"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True})
            return cached["items"]
        try:
            items, total = _paginate_collection(
                label="datasets",
                page_params=params,
                request_page=lambda page_params: self._request("GET", self.config.data_sets_path, query=page_params),
                normalize_page=lambda data: [
                    row
                    for row in (_normal_dataset(item) for item in _items(data))
                    if row.get("id")
                ],
                signature_keys=("id", "name"),
                max_pages=_official_limit("_MAX_DATASETS_PAGES", _MAX_DATASETS_PAGES),
                max_items=_official_limit("_MAX_DATASETS_ITEMS", _MAX_DATASETS_ITEMS),
                progress_callback=progress_callback,
                postprocess_items=_dedupe_alpha_items,
            )
            self._write_cache(cache_key, items, max(total, len(items)))
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                return cached["items"]
            raise

    def list_operators(self, query: str = "all", progress_callback=None) -> list[dict]:
        params = {"search": query if query != "all" else "", "limit": 100, "offset": 0}
        cache_key = self._cache_key("operators", params)
        cached = self._read_cache(cache_key)
        if cached["fresh"] and not _looks_partial_context_cache("operators", cached["items"], cached.get("total", 0), params["limit"]):
            if progress_callback:
                progress_callback({"scanned": len(cached["items"]), "total": cached.get("total") or len(cached["items"]), "cached": True})
            return cached["items"]
        try:
            items, total = _paginate_collection(
                label="operators",
                page_params=params,
                request_page=lambda page_params: self._request("GET", self.config.operators_path, query=page_params),
                normalize_page=lambda data: [_normal_operator(item) for item in _items(data)],
                signature_keys=("name", "category"),
                max_pages=_official_limit("_MAX_OPERATORS_PAGES", _MAX_OPERATORS_PAGES),
                max_items=_official_limit("_MAX_OPERATORS_ITEMS", _MAX_OPERATORS_ITEMS),
                progress_callback=progress_callback,
            )
            self._write_cache(cache_key, items, total)
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                return cached["items"]
            raise

    def list_user_alphas(self, sync_range: str = "3d", progress_callback=None) -> list[dict]:
        params = {"limit": 100, "offset": 0}
        if sync_range in {"3d", "7d"}:
            params["days"] = 3 if sync_range == "3d" else 7
        cache_key = self._cache_key("user_alphas", params)
        cached = self._read_cache(cache_key)
        if cached["fresh"]:
            if progress_callback:
                progress_callback(_user_alpha_progress(
                    sync_range,
                    cached["items"],
                    cached.get("total") or len(cached["items"]),
                    cached=True,
                    stale=False,
            ))
            return cached["items"]
        try:
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

            items, total = _paginate_collection(
                label="user_alphas",
                page_params=params,
                request_page=lambda page_params: self._request("GET", self.config.user_alphas_path, query=page_params),
                normalize_page=lambda data: [_normal_alpha(item) for item in _items(data)],
                signature_keys=("id", "expression", "created_at"),
                max_pages=_official_limit("_MAX_USER_ALPHAS_PAGES", _MAX_USER_ALPHAS_PAGES),
                progress_callback=progress_callback,
                progress_payload=user_alpha_progress,
                total_update=lambda data, current, count: max(_total_count(data) or 0, current, count),
                page_error_recovery=recover_user_alpha_offset,
                stop_when_total_reached=False,
            )
            self._write_cache(cache_key, items, total)
            return items
        except BrainAPIError as exc:
            if self.config.allow_stale_context_on_rate_limit and exc.status_code == 429 and cached["items"]:
                if progress_callback:
                    progress_callback(_user_alpha_progress(sync_range, cached["items"], cached.get("total") or len(cached["items"]), cached=True, stale=True, warning=redact_error_message(exc)))
                return cached["items"]
            raise

"""Composite ``OfficialContextDataMixin`` plus shared helpers and threshold functions."""

from __future__ import annotations

from typing import Any, Callable


from .. import pagination_limits
from ..base import BrainAPIError
from ..official_alphas import AlphaQueryMixin
from ..official_filtering import (
    clamp_query_limit,
    clamp_query_offset,
)
from ..official_helpers import (
    dedupe_alpha_items as _dedupe_alpha_items,
)
from ..official_helpers import (
    items as _items,
)
from ..official_helpers import (
    page_signature as _page_signature,
)
from ..pagination import _paginate_collection
from ._datasets_mixin import _DatasetsContextMixin
from ._fields_mixin import _FieldsContextMixin
from ._operators_mixin import _OperatorsContextMixin

_DISCOVERY_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay", "dataset"})
_ALPHA_FILTER_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay"})


class OfficialContextDataMixin(_FieldsContextMixin, _OperatorsContextMixin, _DatasetsContextMixin, AlphaQueryMixin):
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
    logger = logging.getLogger("brain_alpha_ops.brain_api.official_context")
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

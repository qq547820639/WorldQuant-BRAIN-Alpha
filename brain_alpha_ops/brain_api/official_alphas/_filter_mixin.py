"""Filter and query mixin for alpha operations."""

from __future__ import annotations

from typing import Any

from ..official_filtering import (
    clamp_query_limit,
    clamp_query_offset,
    normalize_wqb_options,
    resolve_compat_value,
)
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
from ..official_query_params import (
    alpha_filter_params,
)
from ._helpers import (
    _ALPHA_FILTER_OPTION_KEYS,
    _pop_compat_alias,
)


class _AlphaQueryFilterMixin:

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

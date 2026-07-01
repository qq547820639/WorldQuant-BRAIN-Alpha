"""Unified A-Share data provider with transparent caching."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_error_message, redact_text

from ._state import logger, _pkg, _DAILY_NUMERIC_FIELDS
from ._cache import CacheStore
from ._adapters import BaoStockAdapter, AKShareAdapter


class AShareDataProvider:
    """Unified A-share market data provider with transparent caching.

    Usage::

        provider = AShareDataProvider(cache_dir="data/ashare_cache")
        df = provider.load_daily_batch(
            symbols=["000001", "000002", "600000"],
            start="2023-01-01",
            end="2024-12-31",
        )
        # Returns a dict symbol → list[DailyBar] for each stock
    """

    def __init__(
        self,
        cache_dir: str | Path = "data/ashare_cache",
        *,
        source: str = "baostock",  # "baostock" | "akshare" | "auto"
    ):
        self.cache = CacheStore(cache_dir)
        self.source = source
        self._baostock = BaoStockAdapter()
        self._akshare = AKShareAdapter()
        self._stock_list: list[dict[str, Any]] | None = None
        self._diagnostics: list[dict[str, Any]] = []

    @property
    def available(self) -> bool:
        return self._baostock.available or self._akshare.available

    def load_daily_batch(
        self,
        symbols: list[str],
        *,
        start: str = "2020-01-01",
        end: str | None = None,
        force_refresh: bool = False,
        reset_diagnostics: bool = True,
    ) -> dict[str, list[dict[str, Any]]]:
        """Load daily OHLCV data for multiple stocks.

        Uses cache when possible.  Each stock is cached independently under
        the key ``daily_{symbol}_{start}_{end}``.

        Args:
            symbols: List of 6-digit stock codes.
            start: Start date (ISO format).
            end: End date (ISO format, defaults to today).
            force_refresh: If True, skip cache and re-fetch from source.

        Returns:
            Dict mapping symbol → list of daily bar dicts.
        """
        if end is None:
            end = date.today().isoformat()
        if reset_diagnostics:
            self._diagnostics = []

        result: dict[str, list[dict[str, Any]]] = {}
        for symbol in symbols:
            cache_key = f"daily_{symbol}_{start}_{end}"
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached:
                    validated_cached = self._validate_daily_rows(symbol, cached, source="cache")
                    if validated_cached:
                        result[symbol] = validated_cached
                        continue

            # Fetch from source
            try:
                rows = self._baostock.fetch_daily(symbol, start_date=start, end_date=end)
                validated_rows = self._validate_daily_rows(symbol, rows, source="baostock")
                if validated_rows:
                    self.cache.put(cache_key, validated_rows)
                result[symbol] = validated_rows
            except Exception as exc:
                message = redact_error_message(exc)
                logger.warning(
                    "fetch_daily failed for %s: %s",
                    redact_text(symbol, max_length=64),
                    message,
                )
                self._record_diagnostic(
                    source="baostock",
                    status="daily_fetch_failed",
                    symbol=symbol,
                    error=message,
                )
                result[symbol] = []

        self._baostock.logout()
        return result

    def load_index_universe(
        self,
        index_code: str = "000300",
        *,
        start: str = "2020-01-01",
        end: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """Load daily data for all constituents of a major index.

        Convenience method that combines index constituent lookup + batch fetch.

        Args:
            index_code: Index code (e.g. "000300" for CSI 300).
            start/end: Date range.
            force_refresh: Force re-fetch.

        Returns:
            Same format as load_daily_batch.
        """
        cache_key = f"index_universe_{index_code}_{start}_{end}"
        self._diagnostics = []

        # Check for all-in-one cache first
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached:
                # Rebuild dict from flat list tagged with symbol
                result: dict[str, list[dict[str, Any]]] = {}
                for row in cached:
                    sym = row.get("symbol", "")
                    result.setdefault(sym, []).append(row)
                return result if result else {}

        # Get constituents
        if self._akshare.available:
            constituents = self._akshare.fetch_index_constituents(index_code)
            symbols = constituents.constituents
            if getattr(constituents, "status", "ok") != "ok" or not symbols:
                self._record_diagnostic(
                    source=getattr(constituents, "source", "akshare"),
                    status=getattr(constituents, "status", "empty") or "empty",
                    index_code=index_code,
                    error=getattr(constituents, "error", "") or "index constituents unavailable",
                )
        else:
            # Fallback: use stock_list to get all stocks
            if self._stock_list is None and self._baostock.available:
                self._stock_list = self._baostock.fetch_stock_list()
            symbols = [s.get("symbol", "") for s in (self._stock_list or [])]
            if len(symbols) > 500:
                import logging as _log
                _log.getLogger(__name__).warning("load_index_universe: truncating %d symbols to 500", len(symbols))
                symbols = symbols[:500]
            if not symbols:
                self._record_diagnostic(
                    source="baostock",
                    status="fallback_stock_list_empty",
                    index_code=index_code,
                    error="akshare unavailable and baostock fallback stock list is empty",
                )

        result = self.load_daily_batch(
            symbols,
            start=start,
            end=end,
            force_refresh=force_refresh,
            reset_diagnostics=False,
        )

        # Cache in flat format
        if result:
            flat = []
            for sym, rows in result.items():
                for row in rows:
                    row["symbol"] = sym
                    flat.append(row)
            self.cache.put(cache_key, flat)

        return result

    def to_backtest_format(
        self,
        data: dict[str, list[dict[str, Any]]],
        *,
        fields: list[str] | None = None,
    ) -> dict[str, list[list[float]]]:
        """Convert A-share daily data to LocalBacktestEngine format.

        Args:
            data: Output from load_daily_batch / load_index_universe.
            fields: Fields to extract (default: ["close", "volume", "amount"]).

        Returns:
            Dict mapping field_name → 2D array [dates][stocks].
        """
        fields = fields or ["close", "volume", "amount", "open", "high", "low", "turnover_rate"]

        # Gather all unique dates
        all_dates: set[str] = set()
        symbols: list[str] = []
        for sym, rows in data.items():
            if rows:
                symbols.append(sym)
                all_dates.update(r.get("date", "") for r in rows)
        dates = sorted(all_dates)
        date_idx = {d: i for i, d in enumerate(dates)}
        sym_idx = {s: i for i, s in enumerate(symbols)}

        n_dates = len(dates)
        n_symbols = len(symbols)

        result: dict[str, list[list[float]]] = {
            field: [[0.0] * n_symbols for _ in range(n_dates)]
            for field in fields
        }

        for sym, rows in data.items():
            si = sym_idx.get(sym)
            if si is None:
                continue
            for row in rows:
                di = date_idx.get(row.get("date", ""))
                if di is None:
                    continue
                for field in fields:
                    val = row.get(field, 0.0)
                    try:
                        result[field][di][si] = float(val)
                    except (TypeError, ValueError):
                        pass

        return result

    def cache_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        keys = self.cache.list_keys()
        total_size = sum(
            (self.cache.cache_dir / f"{k}.{'parquet' if _pkg()._PARQUET_AVAILABLE else 'json'}").stat().st_size
            for k in keys
            if (self.cache.cache_dir / f"{k}.{'parquet' if _pkg()._PARQUET_AVAILABLE else 'json'}").is_file()
        )
        return {
            "keys": len(keys),
            "total_size_bytes": total_size,
            "parquet_available": _pkg()._PARQUET_AVAILABLE,
            "baostock_available": self._baostock.available,
            "akshare_available": self._akshare.available,
            "cache_dir": str(self.cache.cache_dir),
            "diagnostics": self.last_diagnostics(),
        }

    def clear_cache(self) -> int:
        return self.cache.clear()

    def last_diagnostics(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._diagnostics]

    def _validate_daily_rows(self, symbol: str, rows: Any, *, source: str) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            self._record_diagnostic(
                source=source,
                status="daily_rows_invalid",
                symbol=symbol,
                error=f"daily rows must be a list, got {type(rows).__name__}",
            )
            return []

        valid_rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                self._record_diagnostic(
                    source=source,
                    status="daily_row_invalid",
                    symbol=symbol,
                    row_index=row_index,
                    error=f"daily row must be an object, got {type(row).__name__}",
                )
                continue

            row_date = str(row.get("date", "")).strip()
            try:
                date.fromisoformat(row_date)
            except ValueError:
                self._record_diagnostic(
                    source=source,
                    status="daily_row_invalid",
                    symbol=symbol,
                    row_index=row_index,
                    error="daily row has invalid ISO date",
                )
                continue

            invalid_fields: list[str] = []
            for field_name in _DAILY_NUMERIC_FIELDS:
                if field_name not in row:
                    continue
                try:
                    float(row[field_name])
                except (TypeError, ValueError):
                    invalid_fields.append(field_name)
            if invalid_fields:
                self._record_diagnostic(
                    source=source,
                    status="daily_row_invalid",
                    symbol=symbol,
                    row_index=row_index,
                    error="daily row has non-numeric fields: " + ", ".join(invalid_fields),
                )
                continue

            if not str(row.get("symbol", "")).strip():
                row = {**row, "symbol": symbol}
            valid_rows.append(row)

        return valid_rows

    def _record_diagnostic(self, **payload: Any) -> None:
        self._diagnostics.append({
            "timestamp": datetime.now().isoformat(),
            **payload,
        })


def _smoke_test() -> None:
    """Quick self-check — prints availability and cache stats."""
    provider = AShareDataProvider()
    print("AShareDataProvider available:", provider.available)
    print("Cache stats:", json.dumps(provider.cache_stats(), indent=2, ensure_ascii=False))

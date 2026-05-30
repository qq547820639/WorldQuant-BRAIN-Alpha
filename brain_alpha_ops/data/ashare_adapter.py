"""A-share (China) market data adapter with Parquet caching.

Provides a unified interface for Chinese stock market data from free sources
(baostock, akshare), cached as Parquet files for fast subsequent loads.
Normalizes output to a format compatible with LocalBacktestEngine.

Supported data sources
----------------------
  - baostock  : Fundamental daily data (open, high, low, close, volume, etc.)
                Free, no API key, stable API.
  - akshare   : Broader market data (industry classification, index constituents,
                financial statements, etc.). Free, no API key.

Usage
-----
    from brain_alpha_ops.data.ashare_adapter import AShareDataProvider

    provider = AShareDataProvider(cache_dir="data/ashare_cache")
    df = provider.fetch_daily("000001", start="2023-01-01", end="2024-12-31")
    # Uses baostock → Parquet cache → structured DataFrame
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Performance: try fast Parquet, fall back to CSV ──
try:
    import pyarrow as pa  # noqa: F401
    import pyarrow.parquet as pq  # noqa: F401
    _PARQUET_AVAILABLE = True
except ImportError:
    _PARQUET_AVAILABLE = False

# ── Feature flags for optional packages ──
_BAOSTOCK_AVAILABLE = False
_AKSHARE_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════
# Core data structures
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DailyBar:
    """Single daily bar for one stock."""
    date: str = ""             # ISO date
    symbol: str = ""           # Stock code (6-digit)
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    amount: float = 0.0        # Trading amount in CNY
    turnover_rate: float = 0.0 # Turnover rate (%)
    adj_factor: float = 1.0    # Adjustment factor


@dataclass
class StockInfo:
    """Basic stock metadata."""
    symbol: str = ""
    name: str = ""
    industry: str = ""
    list_date: str = ""
    market_cap: float = 0.0
    is_st: bool = False  # Special Treatment flag


@dataclass
class IndexConstituents:
    """Constituents of a stock index."""
    index_code: str = ""
    index_name: str = ""
    constituents: list[str] = field(default_factory=list)
    effective_date: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# Parquet / CSV cache layer
# ═══════════════════════════════════════════════════════════════════════════

class CacheStore:
    """Simple keyed cache with Parquet (preferred) or JSON (fallback)."""

    def __init__(self, cache_dir: str | Path = "data/ashare_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> list[dict[str, Any]] | None:
        """Load cached data by key.  Returns None on miss or corruption."""
        if _PARQUET_AVAILABLE:
            path = self.cache_dir / f"{key}.parquet"
            if path.is_file():
                try:
                    table = pq.read_table(str(path))
                    return table.to_pylist()
                except Exception as exc:
                    logger.warning("Parquet read failed for %s: %s — re-fetching", key, exc)
                    return None
        # Fallback: JSON
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def put(self, key: str, rows: list[dict[str, Any]]) -> None:
        """Persist rows to cache under the given key."""
        if _PARQUET_AVAILABLE:
            path = self.cache_dir / f"{key}.parquet"
            try:
                table = pa.Table.from_pylist(rows)
                pq.write_table(table, str(path))
                return
            except Exception as exc:
                logger.warning("Parquet write failed for %s: %s — using JSON fallback", key, exc)
        # Fallback: JSON
        path = self.cache_dir / f"{key}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")

    def list_keys(self) -> list[str]:
        keys: set[str] = set()
        for suffix in (".parquet", ".json"):
            for f in self.cache_dir.glob(f"*{suffix}"):
                keys.add(f.stem)
        return sorted(keys)

    def clear(self) -> int:
        count = 0
        for f in self.cache_dir.glob("*"):
            if f.suffix in (".parquet", ".json"):
                f.unlink()
                count += 1
        return count


# ═══════════════════════════════════════════════════════════════════════════
# BaoStock adapter
# ═══════════════════════════════════════════════════════════════════════════

class BaoStockAdapter:
    """Adapter for the baostock free A-share daily data API.

    Install: pip install baostock
    """

    def __init__(self):
        self._logged_in = False

    @property
    def available(self) -> bool:
        global _BAOSTOCK_AVAILABLE
        if not _BAOSTOCK_AVAILABLE:
            try:
                import baostock as _  # noqa: F401
                _BAOSTOCK_AVAILABLE = True
            except ImportError:
                return False
        return _BAOSTOCK_AVAILABLE

    def _ensure_login(self) -> None:
        if not self._logged_in:
            import baostock as bs
            lg = bs.login()
            if lg.error_code != "0":
                raise RuntimeError(f"baostock login failed: {lg.error_msg}")
            self._logged_in = True

    def logout(self) -> None:
        if self._logged_in:
            import baostock as bs
            bs.logout()
            self._logged_in = False

    def fetch_daily(
        self,
        symbol: str,
        *,
        start_date: str = "2020-01-01",
        end_date: str | None = None,
        adjustment: str = "2",  # 2 = forward-adjusted
    ) -> list[dict[str, Any]]:
        """Fetch daily OHLCV data for a single A-share stock.

        Args:
            symbol: 6-digit stock code (e.g. "000001" for Ping An Bank).
            start_date: ISO date string.
            end_date: ISO date string (defaults to today).
            adjustment: "1"=unadjusted, "2"=forward-adjusted, "3"=backward-adjusted.

        Returns:
            List of dicts with OHLCV fields.
        """
        if not self.available:
            raise ImportError("baostock not installed. Run: pip install baostock")

        self._ensure_login()
        if end_date is None:
            end_date = date.today().isoformat()
        code = _baostock_code(symbol)

        import baostock as bs
        # Try with adjfactor first (older baostock), fall back without it
        fields = "date,open,high,low,close,volume,amount,turn,adjfactor"
        rs = bs.query_history_k_data_plus(
            code,
            fields,
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag=adjustment,
        )
        if rs.error_code != "0":
            # Retry without adjfactor (newer baostock versions)
            fields = "date,open,high,low,close,volume,amount,turn"
            rs = bs.query_history_k_data_plus(
                code,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag=adjustment,
            )
        if rs.error_code != "0":
            logger.warning("baostock query failed for %s: %s", symbol, rs.error_msg)
            return []

        rows: list[dict[str, Any]] = []
        has_adjfactor = "adjfactor" in fields
        while rs.next():
            row = rs.get_row_data()
            rows.append({
                "date": row[0],
                "symbol": symbol,
                "open": _safe_float(row[1]),
                "high": _safe_float(row[2]),
                "low": _safe_float(row[3]),
                "close": _safe_float(row[4]),
                "volume": _safe_float(row[5]),
                "amount": _safe_float(row[6]),
                "turnover_rate": _safe_float(row[7]),
                "adj_factor": _safe_float(row[8], default=1.0) if has_adjfactor else 1.0,
            })
        return rows

    def fetch_stock_list(self) -> list[dict[str, Any]]:
        """Fetch basic info for all A-share stocks."""
        if not self.available:
            raise ImportError("baostock not installed")
        self._ensure_login()

        import baostock as bs
        rs = bs.query_stock_basic()
        if rs.error_code != "0":
            raise RuntimeError(f"stock_basic query failed: {rs.error_msg}")

        stocks = []
        while rs.next():
            row = rs.get_row_data()
            stocks.append({
                "symbol": row[0],
                "name": row[1],
                "ipo_date": row[2],
                "type": row[3],
                "status": row[4] if len(row) > 4 else "",
            })
        return stocks


# ═══════════════════════════════════════════════════════════════════════════
# AKShare adapter (supplementary)
# ═══════════════════════════════════════════════════════════════════════════

class AKShareAdapter:
    """Adapter for akshare (free, broader coverage — index constituents, etc.).

    Install: pip install akshare
    """

    @property
    def available(self) -> bool:
        global _AKSHARE_AVAILABLE
        if not _AKSHARE_AVAILABLE:
            try:
                import akshare as _  # noqa: F401
                _AKSHARE_AVAILABLE = True
            except ImportError:
                return False
        return _AKSHARE_AVAILABLE

    def fetch_index_constituents(self, index_code: str) -> IndexConstituents:
        """Fetch constituents of a major A-share index.

        Supported: "000300" (HS300), "000905" (CSI500), "000016" (SSE50),
                   "399006" (ChiNext), "000688" (STAR50).
        """
        if not self.available:
            raise ImportError("akshare not installed. Run: pip install akshare")

        import akshare as ak

        index_map = {
            "000300": ("沪深300", "index_stock_cons_weight_csindex", "000300"),
            "000905": ("中证500", "index_stock_cons_weight_csindex", "000905"),
            "000016": ("上证50", "index_stock_cons_weight_csindex", "000016"),
            "399006": ("创业板指", "index_stock_cons_weight_csindex", "399006"),
        }

        name, func_name, code = index_map.get(index_code, ("未知", "", index_code))
        if not func_name:
            return IndexConstituents(index_code=index_code, index_name=name)

        try:
            func = getattr(ak, func_name, None)
            if func is None:
                return IndexConstituents(index_code=index_code, index_name=name)
            df = func(code)
            if df is None or df.empty:
                return IndexConstituents(index_code=index_code, index_name=name)

            symbols = [str(row.get("成分券代码", row.get("constituent_code", ""))).strip()
                       for _, row in df.iterrows()]
            symbols = [s for s in symbols if s]
            return IndexConstituents(
                index_code=index_code,
                index_name=name,
                constituents=symbols,
                effective_date=date.today().isoformat(),
            )
        except Exception as exc:
            logger.warning("akshare index constituents failed for %s: %s", index_code, exc)
            return IndexConstituents(index_code=index_code, index_name=name)

    def fetch_industry_classification(self) -> dict[str, str]:
        """Fetch industry → sector mapping for A-share stocks.

        Returns:
            Dict mapping stock symbol → industry_name.
        """
        if not self.available:
            raise ImportError("akshare not installed")
        import akshare as ak
        try:
            df = ak.stock_board_industry_name_em()
            mapping: dict[str, str] = {}
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    code = str(row.get("代码", "")).strip()
                    name = str(row.get("名称", "")).strip()
                    if code:
                        mapping[code] = name
            return mapping
        except Exception as exc:
            logger.warning("akshare industry classification failed: %s", exc)
            return {}


# ═══════════════════════════════════════════════════════════════════════════
# Unified A-Share data provider
# ═══════════════════════════════════════════════════════════════════════════

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

        result: dict[str, list[dict[str, Any]]] = {}
        for symbol in symbols:
            cache_key = f"daily_{symbol}_{start}_{end}"
            if not force_refresh:
                cached = self.cache.get(cache_key)
                if cached:
                    result[symbol] = cached
                    continue

            # Fetch from source
            try:
                rows = self._baostock.fetch_daily(symbol, start_date=start, end_date=end)
                if rows:
                    self.cache.put(cache_key, rows)
                result[symbol] = rows
            except Exception as exc:
                logger.warning("fetch_daily failed for %s: %s", symbol, exc)
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
        else:
            # Fallback: use stock_list to get all stocks
            if self._stock_list is None and self._baostock.available:
                self._stock_list = self._baostock.fetch_stock_list()
            symbols = [s.get("symbol", "") for s in (self._stock_list or [])]
            symbols = symbols[:500]  # Limit

        result = self.load_daily_batch(symbols, start=start, end=end, force_refresh=force_refresh)

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
            (self.cache.cache_dir / f"{k}.{'parquet' if _PARQUET_AVAILABLE else 'json'}").stat().st_size
            for k in keys
            if (self.cache.cache_dir / f"{k}.{'parquet' if _PARQUET_AVAILABLE else 'json'}").is_file()
        )
        return {
            "keys": len(keys),
            "total_size_bytes": total_size,
            "parquet_available": _PARQUET_AVAILABLE,
            "baostock_available": self._baostock.available,
            "akshare_available": self._akshare.available,
            "cache_dir": str(self.cache.cache_dir),
        }

    def clear_cache(self) -> int:
        return self.cache.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _baostock_code(symbol: str) -> str:
    """Convert 6-digit symbol to baostock format (sh.600000 / sz.000001)."""
    code = symbol.strip().zfill(6)
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    elif code.startswith(("0", "3")):
        return f"sz.{code}"
    elif code.startswith(("4", "8")):
        return f"bj.{code}"
    return f"sh.{code}"


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value.strip() or "0")
    except (AttributeError, TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════════════════
# Quick smoke-test
# ═══════════════════════════════════════════════════════════════════════════

def _smoke_test() -> None:
    """Quick self-check — prints availability and cache stats."""
    provider = AShareDataProvider()
    print("AShareDataProvider available:", provider.available)
    print("Cache stats:", json.dumps(provider.cache_stats(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _smoke_test()

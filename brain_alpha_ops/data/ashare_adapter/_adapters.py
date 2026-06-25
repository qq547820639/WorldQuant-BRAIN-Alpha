"""BaoStock and AKShare data source adapters."""
from __future__ import annotations

from datetime import date
from typing import Any

from brain_alpha_ops.redaction import redact_error_message, redact_text

from ._state import logger, _pkg
from ._models import IndexConstituents, _baostock_code, _safe_float


class BaoStockAdapter:
    """Adapter for the baostock free A-share daily data API.

    Install: pip install baostock
    """

    def __init__(self):
        self._logged_in = False

    @property
    def available(self) -> bool:
        pkg = _pkg()
        if not pkg._BAOSTOCK_AVAILABLE:
            try:
                import baostock as _  # noqa: F401
                pkg._BAOSTOCK_AVAILABLE = True
            except ImportError:
                return False
        return pkg._BAOSTOCK_AVAILABLE

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
            logger.warning(
                "baostock query failed for %s: %s",
                redact_text(symbol, max_length=64),
                redact_text(rs.error_msg, max_length=180),
            )
            return []

        rows: list[dict[str, Any]] = []
        has_adjfactor = "adjfactor" in fields
        while rs.next():
            row = rs.get_row_data()
            if len(row) < 8:
                continue
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
                "adj_factor": _safe_float(row[8], default=1.0) if has_adjfactor and len(row) > 8 else 1.0,
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
            if len(row) < 5:
                continue
            stocks.append({
                "symbol": row[0],
                "name": row[1],
                "ipo_date": row[2],
                "type": row[3],
                "status": row[4],
            })
        return stocks


class AKShareAdapter:
    """Adapter for akshare (free, broader coverage — index constituents, etc.).

    Install: pip install akshare
    """

    @property
    def available(self) -> bool:
        pkg = _pkg()
        if not pkg._AKSHARE_AVAILABLE:
            try:
                import akshare as _  # noqa: F401
                pkg._AKSHARE_AVAILABLE = True
            except ImportError:
                return False
        return pkg._AKSHARE_AVAILABLE

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
            return IndexConstituents(
                index_code=index_code,
                index_name=name,
                status="unsupported_index",
                error=f"unsupported index code: {index_code}",
            )

        try:
            func = getattr(ak, func_name, None)
            if func is None:
                return IndexConstituents(
                    index_code=index_code,
                    index_name=name,
                    status="source_function_missing",
                    error=f"akshare function missing: {func_name}",
                )
            df = func(code)
            if df is None or df.empty:
                return IndexConstituents(
                    index_code=index_code,
                    index_name=name,
                    status="empty",
                    error="akshare returned empty index constituents",
                )

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
            message = redact_error_message(exc)
            logger.warning(
                "akshare index constituents failed for %s: %s",
                redact_text(index_code, max_length=64),
                message,
            )
            return IndexConstituents(
                index_code=index_code,
                index_name=name,
                status="failed",
                error=message,
            )

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
            logger.warning("akshare industry classification failed: %s", redact_error_message(exc))
            return {}

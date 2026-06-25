"""Core data structures and helpers for the ashare_adapter package."""
from __future__ import annotations

from dataclasses import dataclass, field


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
    status: str = "ok"
    source: str = "akshare"
    error: str = ""


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

"""A-share (China) market data adapter with Parquet caching.

Provides a unified interface for Chinese stock market data from free sources
(baostock, akshare), cached as Parquet files for fast subsequent loads.
Normalizes output to a format compatible with LocalBacktestEngine.

Subpackage of ``brain_alpha_ops.data``. Splits the original
``ashare_adapter.py`` monolith into focused modules while preserving the
public API surface via re-exports.
"""
from __future__ import annotations

from ._state import (
    _DAILY_NUMERIC_FIELDS,
    logger,
    pa,
    pq,
)

# ── Feature flags (defined on the package so tests can monkeypatch them) ──
_PARQUET_AVAILABLE = pa is not None
_BAOSTOCK_AVAILABLE = False
_AKSHARE_AVAILABLE = False

# Core data structures and helpers
from ._models import (
    DailyBar,
    IndexConstituents,
    StockInfo,
    _baostock_code,
    _safe_float,
)

# Cache layer
from ._cache import CacheStore

# Source adapters
from ._adapters import AKShareAdapter, BaoStockAdapter

# Unified provider
from ._provider import AShareDataProvider, _smoke_test

__all__ = [
    "AShareDataProvider",
    "AKShareAdapter",
    "BaoStockAdapter",
    "CacheStore",
    "DailyBar",
    "IndexConstituents",
    "StockInfo",
    "_baostock_code",
    "_safe_float",
    "_smoke_test",
]

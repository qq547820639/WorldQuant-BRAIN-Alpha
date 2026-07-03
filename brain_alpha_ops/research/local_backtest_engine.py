"""Local synthetic prefilter — evaluates alpha expressions using synthetic market data.

THIS IS NOT A REAL HISTORICAL BACKTEST. All data is synthetically generated
from the engine's configured ``synthetic_config``. Results are approximate
prefilter scores only.
Use official BRAIN simulation results for real historical performance estimates.

Supports a subset of FASTEXPR operators locally and computes standard metrics
(Sharpe, Fitness, Turnover, Drawdown) using vectorized operations.
Designed to pre-filter candidate expressions before consuming BRAIN API quota.

This module is a backward-compatible shim.  The component classes are now
defined in ``brain_alpha_ops.research.local_backtest``.  This module
re-exports them so existing import paths continue to work unchanged.

Architecture
------------
    LocalBacktestEngine
     ├── ExpressionEvaluator — evaluates a FASTEXPR AST on market data
     ├── PortfolioConstructor — daily cross-sectional ranking → long/short
     ├── MetricsComputer — Sharpe, Fitness, Turnover, Drawdown, IC, IR
     └── SyntheticDataProvider — generates test data when no real data

Usage::

    engine = LocalBacktestEngine()
    result = engine.evaluate("rank(ts_zscore(close, 20))")
    print(result["sharpe"], result["fitness"])
"""
from __future__ import annotations

from brain_alpha_ops.research.local_backtest.data_provider import SyntheticDataProvider
from brain_alpha_ops.research.local_backtest.engine import (
    LocalBacktestEngine,
    MarketDataFrame,
)
from brain_alpha_ops.research.local_backtest.expression_evaluator import (
    LocalExpressionEvaluator,
)
from brain_alpha_ops.research.local_backtest.metrics import (
    BacktestMetrics,
    MetricsComputer,
)
from brain_alpha_ops.research.local_backtest.portfolio import PortfolioConstructor

# Re-exports from local_backtest_metrics_helpers (P1-4 refactor).
# These underscore-prefixed helpers are part of the public API of this shim.
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    cumsum as _cumsum,
    rank_values as _rank_values,
    safe_corr as _safe_corr,
    safe_mean as _safe_mean,
    safe_stdev as _safe_stdev,
    spearman_r as _spearman_r,
)

# Shared prefilter backtest config (merged from local_backtest_config.py).
PREFILTER_BACKTEST_DATES = 84
PREFILTER_BACKTEST_SYMBOLS = 160

__all__ = [
    "SyntheticDataProvider",
    "LocalExpressionEvaluator",
    "PortfolioConstructor",
    "BacktestMetrics",
    "MetricsComputer",
    "LocalBacktestEngine",
    "MarketDataFrame",
    "_cumsum",
    "_rank_values",
    "_safe_corr",
    "_safe_mean",
    "_safe_stdev",
    "_spearman_r",
    "PREFILTER_BACKTEST_DATES",
    "PREFILTER_BACKTEST_SYMBOLS",
]

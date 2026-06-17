"""Statistical helpers extracted from local_backtest_engine.py.

P1-4 refactor: these pure-function math utilities previously inflated the
local backtest engine module (1148 lines).  They are now isolated so the
engine file can focus on ``LocalBacktestEngine`` and its direct
collaborators (``MarketDataFrame``, ``SyntheticDataProvider``,
``LocalExpressionEvaluator``, ``PortfolioConstructor``, ``BacktestMetrics``,
``MetricsComputer``).
"""

from __future__ import annotations

import statistics
from typing import List


def safe_mean(values: List[float]) -> float:
    """Mean of values, or 0.0 on empty list."""
    if not values:
        return 0.0
    return statistics.mean(values)


def safe_stdev(values: List[float]) -> float:
    """Sample standard deviation, or 0.0 if n<=1."""
    if len(values) <= 1:
        return 0.0
    return statistics.stdev(values)


def safe_corr(xs: List[float], ys: List[float]) -> float:
    """Pearson correlation coefficient, compatible with Python 3.9+."""
    n = min(len(xs), len(ys))
    if n <= 2:
        return 0.0
    return pearson_r(xs[:n], ys[:n])


def pearson_r(x: List[float], y: List[float]) -> float:
    """Manual Pearson correlation for Python <3.10 compatibility.

    Caller (``safe_corr``) already validated n > 2.
    """
    n = len(x)
    mx = statistics.mean(x)
    my = statistics.mean(y)
    sx = safe_stdev(x)
    sy = safe_stdev(y)
    if sx < 1e-10 or sy < 1e-10:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1)
    return cov / (sx * sy)


def spearman_r(xs: List[float], ys: List[float]) -> float:
    """Spearman rank correlation."""
    n = min(len(xs), len(ys))
    if n <= 2:
        return 0.0
    rank_x = rank_values(xs[:n])
    rank_y = rank_values(ys[:n])
    return pearson_r(rank_x, rank_y)


def rank_values(values: List[float]) -> List[float]:
    """Return normalised ranks (0.0..1.0) for each value."""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    for rank, (i, _) in enumerate(indexed):
        ranks[i] = float(rank) / max(1, len(values) - 1)
    return ranks


def cumsum(values: List[float]) -> List[float]:
    """Running cumulative sum."""
    result: List[float] = []
    total = 0.0
    for v in values:
        total += v
        result.append(total)
    return result

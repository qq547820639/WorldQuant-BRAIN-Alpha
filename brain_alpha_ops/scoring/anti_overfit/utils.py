from __future__ import annotations

import math


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _safe_std(values: list[float], mean_val: float | None = None) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    m = mean_val if mean_val is not None else _safe_mean(values)
    variance = sum((v - m) ** 2 for v in values) / (n - 1)
    return math.sqrt(max(0.0, variance))


def _pearson_r(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    mx = _safe_mean(x[:n])
    my = _safe_mean(y[:n])
    sx = _safe_std(x[:n], mx)
    sy = _safe_std(y[:n], my)
    if sx < 1e-15 or sy < 1e-15:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x[:n], y[:n])) / n
    return max(-1.0, min(1.0, cov / (sx * sy)))


def _rank_transform(values: list[float]) -> list[float]:
    """Replace values with their ranks (1-based, average for ties)."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda v: v[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _spearman_r(x: list[float], y: list[float]) -> float:
    """Compute Spearman rank correlation between two arrays."""
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x_ranks = _rank_transform(x[:n])
    y_ranks = _rank_transform(y[:n])
    return _pearson_r(x_ranks, y_ranks)


def _rank_ic(x: list[float], y: list[float]) -> list[float]:
    """Compute rank IC (Spearman correlation) per cross-section.

    When group_ids is not provided, treats entire series as one group.
    Returns a single-element list for the overall IC.
    """
    return [_spearman_r(x, y)] if x and y else [0.0]


def _sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualized Sharpe ratio from daily returns."""
    n = len(returns)
    if n < 5:
        return 0.0
    mean_ret = _safe_mean(returns) - risk_free / 252
    std_ret = _safe_std(returns, mean_ret + risk_free / 252)
    if std_ret < 1e-15:
        return 0.0
    return (mean_ret / std_ret) * math.sqrt(252)


def _auto_classify_regimes(returns: list[float]) -> list[str]:
    """Auto-classify returns into bull/bear/sideways regimes by percentile.

    Bottom third = bear, middle third = sideways, top third = bull.
    """
    if not returns:
        return []
    sorted_ret = sorted(returns)
    n = len(sorted_ret)
    lo = sorted_ret[n // 3]
    hi = sorted_ret[2 * n // 3]
    return [
        "bear" if r <= lo else "bull" if r >= hi else "sideways"
        for r in returns
    ]

"""Cross-sectional, rolling-window, and row-level operator helpers mixin."""

from __future__ import annotations

import statistics

from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_corr as _safe_corr,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_mean as _safe_mean,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_stdev as _safe_stdev,
)


class _OperatorsMixin:
    """Cross-sectional, rolling-window, and row-level operator helpers."""

    @staticmethod
    def _cross_rank(values: list[float]) -> list[float]:
        n = len(values)
        if n == 0:
            return []
        indexed = [(v, i) for i, v in enumerate(values)]
        indexed.sort(key=lambda x: (x[0], x[1]))
        ranks = [0.0] * n
        for rank, (v, i) in enumerate(indexed):
            ranks[i] = rank / max(1, n - 1)
        return ranks

    @staticmethod
    def _cross_zscore(values: list[float]) -> list[float]:
        n = len(values)
        if n <= 1:
            return [0.0] * n
        mean_val = statistics.mean(values)
        stdev_val = statistics.stdev(values) if n > 1 else 1.0
        if abs(stdev_val) < 1e-10:
            return [0.0] * n
        return [(v - mean_val) / stdev_val for v in values]

    @staticmethod
    def _rolling_apply(
        data: list[list[float]], window: int, func
    ) -> list[list[float]]:
        n_dates = len(data)
        n_symbols = len(data[0]) if data else 0
        result = [[0.0] * n_symbols for _ in range(n_dates)]
        for s in range(n_symbols):
            series = [data[d][s] for d in range(n_dates)]
            for d in range(n_dates):
                start = max(0, d - window + 1)
                win = series[start : d + 1]
                result[d][s] = func(win)
        return result

    @staticmethod
    def _ts_zscore_window(window: list[float]) -> float:
        if len(window) <= 1:
            return 0.0
        mean_val = statistics.mean(window)
        stdev_val = _safe_stdev(window)
        if abs(stdev_val) < 1e-10:
            return 0.0
        return (window[-1] - mean_val) / stdev_val

    @staticmethod
    def _ts_rank_window(window: list[float]) -> float:
        if not window:
            return 0.0
        ranked = sorted(
            (value, idx) for idx, value in enumerate(window)
        )
        positions = {
            idx: rank for rank, (_value, idx) in enumerate(ranked)
        }
        if len(window) == 1:
            return 0.0
        return positions[len(window) - 1] / max(1, len(window) - 1)

    @staticmethod
    def _ts_decay_linear_window(window: list[float]) -> float:
        if not window:
            return 0.0
        weights = list(range(1, len(window) + 1))
        denom = float(sum(weights) or 1.0)
        return (
            sum(
                value * weight
                for value, weight in zip(window, weights)
            )
            / denom
        )

    @staticmethod
    def _ts_delta(
        data: list[list[float]], window: int
    ) -> list[list[float]]:
        n_dates = len(data)
        n_symbols = len(data[0]) if data else 0
        result = [[0.0] * n_symbols for _ in range(n_dates)]
        for d in range(n_dates):
            if d >= window:
                result[d] = [
                    data[d][s] - data[d - window][s]
                    for s in range(n_symbols)
                ]
        return result

    @staticmethod
    def _group_neutralize(row: list[float]) -> list[float]:
        if not row:
            return []
        mean_val = _safe_mean(row)
        return [value - mean_val for value in row]

    @staticmethod
    def _winsorize_row(
        row: list[float], std_factor: float
    ) -> list[float]:
        if not row:
            return []
        mean_val = _safe_mean(row)
        stdev_val = _safe_stdev(row)
        limit = abs(float(std_factor or 3.0)) * max(stdev_val, 1e-10)
        lower = mean_val - limit
        upper = mean_val + limit
        return [min(max(value, lower), upper) for value in row]

    @staticmethod
    def _normalize_row(row: list[float]) -> list[float]:
        if not row:
            return []
        mean_val = _safe_mean(row)
        stdev_val = _safe_stdev(row)
        if abs(stdev_val) < 1e-10:
            return [0.0 for _ in row]
        return [(value - mean_val) / stdev_val for value in row]

    @staticmethod
    def _if_else(
        cond: list[list[float]],
        when_true: list[list[float]],
        when_false: list[list[float]],
    ) -> list[list[float]]:
        result: list[list[float]] = []
        for cond_row, true_row, false_row in zip(
            cond, when_true, when_false
        ):
            row = [
                true_val if cond_val > 0 else false_val
                for cond_val, true_val, false_val in zip(
                    cond_row, true_row, false_row
                )
            ]
            result.append(row)
        return result

    @staticmethod
    def _extract_window(arg: list[list[float]]) -> int:
        """Extract window size from an AST argument (scalar or array)."""
        if arg and arg[0]:
            val = arg[0][0]
            return max(1, int(abs(val)))
        return 20

    @staticmethod
    def _extract_scalar(arg: list[list[float]]) -> float:
        if arg and arg[0]:
            return float(arg[0][0])
        return 2.0

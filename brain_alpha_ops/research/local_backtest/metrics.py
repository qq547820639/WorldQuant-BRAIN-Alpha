"""BacktestMetrics and MetricsComputer — standard backtest metrics calculation."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any

from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    cumsum as _cumsum,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_corr as _safe_corr,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_stdev as _safe_stdev,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    spearman_r as _spearman_r,
)


@dataclass
class BacktestMetrics:
    """Standard backtest metrics aligned with BRAIN API format."""

    sharpe: float = 0.0
    fitness: float = 0.0
    turnover: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    correlation: float = 0.0
    weight_concentration: float = 0.0
    sub_universe_sharpe: float = 0.0
    margin_bps: float = 0.0
    ic_mean: float = 0.0
    ic_ir: float = 0.0
    n_dates: int = 0
    n_symbols: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sharpe": round(self.sharpe, 4),
            "fitness": round(self.fitness, 4),
            "turnover": round(self.turnover, 4),
            "returns": round(self.returns, 4),
            "drawdown": round(self.drawdown, 4),
            "correlation": round(self.correlation, 4),
            "weight_concentration": round(self.weight_concentration, 4),
            "sub_universe_sharpe": round(self.sub_universe_sharpe, 4),
            "margin": round(self.margin_bps, 4),
            "ic_mean": round(self.ic_mean, 4),
            "ic_ir": round(self.ic_ir, 4),
            "n_dates": self.n_dates,
            "n_symbols": self.n_symbols,
        }


class MetricsComputer:
    """Compute standard backtest metrics from portfolio weights and returns."""

    def compute(
        self,
        weights: list[list[float]],
        returns: list[list[float]],
        *,
        alphas: list[list[float]] | None = None,
        trading_days_per_year: int = 252,
    ) -> BacktestMetrics:
        """Compute all standard metrics.

        Args:
            weights: [dates][symbols] portfolio weights (dollar-neutral).
            returns: [dates][symbols] daily returns.
            alphas: Optional [dates][symbols] raw alpha signals.
                   Used for IC/IR computation (preferred over weights proxy).
            trading_days_per_year: Annualization factor.

        Returns:
            BacktestMetrics dataclass.
        """
        n_dates = len(weights)
        n_symbols = len(weights[0]) if weights else 0
        metrics = BacktestMetrics(n_dates=n_dates, n_symbols=n_symbols)

        # Daily PnL: dot product of weights and returns
        daily_pnl = []
        for d in range(n_dates):
            if d < len(returns):
                pnl = sum(
                    weights[d][s] * returns[d][s]
                    for s in range(n_symbols)
                )
                daily_pnl.append(pnl)
            else:
                daily_pnl.append(0.0)

        if not daily_pnl or n_dates < 2:
            return metrics

        # Sharpe ratio
        mean_pnl = statistics.mean(daily_pnl)
        stdev_pnl = _safe_stdev(daily_pnl)
        metrics.sharpe = (
            mean_pnl / max(stdev_pnl, 1e-10)
        ) * math.sqrt(trading_days_per_year)

        # Returns (annualized)
        metrics.returns = mean_pnl * trading_days_per_year

        # Turnover
        turnovers = []
        for d in range(1, n_dates):
            to = (
                sum(
                    abs(weights[d][s] - weights[d - 1][s])
                    for s in range(n_symbols)
                )
                / 2.0
            )
            turnovers.append(to)
        metrics.turnover = (
            statistics.mean(turnovers) if turnovers else 0.0
        )

        # Fitness (BRAIN formula: Sharpe * sqrt(|Returns| / max(Turnover, 0.125)))
        adj_turnover = max(metrics.turnover, 0.125)
        metrics.fitness = metrics.sharpe * math.sqrt(
            abs(metrics.returns) / adj_turnover
        )

        # Drawdown (max peak-to-trough)
        cumulative = _cumsum(daily_pnl)
        max_dd = 0.0
        peak = cumulative[0]
        for val in cumulative:
            if val > peak:
                peak = val
            dd = peak - val
            if dd > max_dd:
                max_dd = dd
        metrics.drawdown = max_dd

        # Correlation (auto-correlation of daily PnL — lag-1)
        if len(daily_pnl) >= 2:
            metrics.correlation = _safe_corr(
                daily_pnl[:-1], daily_pnl[1:]
            )

        # Weight concentration (max abs single-stock weight)
        max_w = 0.0
        for day_w in weights:
            for w in day_w:
                if abs(w) > max_w:
                    max_w = abs(w)
        metrics.weight_concentration = max_w

        # IC (Information Coefficient — Spearman rank correlation of alpha vs forward return)
        # Prefer raw alphas (quantitatively correct); fall back to weights proxy
        alpha_signal = alphas if alphas is not None else weights
        ics = []
        for d in range(n_dates - 1):
            day_alpha = (
                alpha_signal[d] if d < len(alpha_signal) else []
            )
            forward_returns = (
                returns[d + 1]
                if d + 1 < len(returns)
                else returns[d]
            )
            if not day_alpha:
                continue
            ic = _spearman_r(day_alpha, forward_returns)
            if not math.isnan(ic):
                ics.append(ic)
        if ics:
            metrics.ic_mean = statistics.mean(ics)
            metrics.ic_ir = metrics.ic_mean / max(
                _safe_stdev(ics), 1e-10
            )

        # Margin (bps) — simplified: mean daily PnL × 10000
        metrics.margin_bps = mean_pnl * 10000

        # Sub-universe Sharpe (simplified: Sharpe of top half by weight)
        mid = n_symbols // 2
        sub_pnl = []
        for d in range(n_dates):
            sub_pnl.append(
                sum(
                    weights[d][:mid][s] * returns[d][s]
                    for s in range(min(mid, len(returns[d])))
                )
            )
        sub_mean = statistics.mean(sub_pnl) if sub_pnl else 0.0
        sub_std = _safe_stdev(sub_pnl)
        metrics.sub_universe_sharpe = (
            sub_mean / max(sub_std, 1e-10)
        ) * math.sqrt(trading_days_per_year)

        return metrics


__all__ = ["BacktestMetrics", "MetricsComputer"]

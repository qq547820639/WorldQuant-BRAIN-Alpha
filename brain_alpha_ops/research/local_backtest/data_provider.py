"""SyntheticDataProvider — generates synthetic market data for local prefilter."""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from brain_alpha_ops.research.local_backtest_market_data import (
    MarketDataFrame,
)


class SyntheticDataProvider:
    """Generates synthetic market data for local prefilter evaluation (NOT real data).

    Creates realistic time-series data for standard BRAIN fields (close, volume,
    returns, etc.) with configurable trend, volatility, and correlation.
    """

    STANDARD_FIELDS = [
        "close", "volume", "returns", "market_cap", "book_to_price",
        "pe_ratio", "debt_to_equity", "roe", "revenue_growth",
        "momentum_1m", "momentum_3m", "momentum_12m",
        "volatility_1m", "volatility_3m",
        "rsi_14", "macd", "atr_14",
        "short_interest", "dividend_yield", "beta",
        "open", "high", "low", "vwap", "adv20",
        "assets", "revenue", "eps", "operating_income", "enterprise_value",
        "anl4_ebit_value", "anl4_ebitda_value",
        "anl4_cfo_value", "anl4_cfi_value", "anl4_fcf_value",
        "anl4_epsr_value", "anl4_epsr_mean",
        "sector", "industry", "subindustry", "market",
    ]

    def generate(
        self,
        *,
        n_dates: int = 252,
        n_symbols: int = 500,
        fields: list[str] | None = None,
        start_date: str = "2024-01-01",
        seed: int = 42,
    ) -> "MarketDataFrame":
        """Generate a synthetic market data frame.

        Args:
            n_dates: Number of trading days (default 252 ≈ 1 year).
            n_symbols: Number of stocks.
            fields: Field names to generate (defaults to STANDARD_FIELDS).
            start_date: ISO date string for the first trading day.
            seed: Random seed for reproducibility.

        Returns:
            A MarketDataFrame ready for backtest evaluation.
        """
        fields = fields or self.STANDARD_FIELDS
        rng = random.Random(seed)
        symbols = [f"STOCK_{i:04d}" for i in range(n_symbols)]

        # Generate trading dates (weekdays only)
        dates = []
        current = date.fromisoformat(start_date)
        while len(dates) < n_dates:
            if current.weekday() < 5:  # Monday-Friday
                dates.append(current.isoformat())
            current += timedelta(days=1)

        data = MarketDataFrame(
            fields={},
            dates=dates,
            symbols=symbols,
            n_dates=n_dates,
            n_symbols=n_symbols,
        )

        for field_name in fields:
            field_data = self._generate_field(
                field_name, n_dates, n_symbols, rng
            )
            data.fields[field_name] = field_data

        return data

    def _generate_field(
        self,
        name: str,
        n_dates: int,
        n_symbols: int,
        rng: random.Random,
    ) -> list[list[float]]:
        """Generate a single field's time-series cross-sectional data."""
        if name == "close":
            return self._generate_price_series(
                n_dates, n_symbols, rng, drift=0.0003, vol=0.015
            )
        elif name == "volume":
            return [
                [abs(rng.gauss(1_000_000, 500_000)) for _ in range(n_symbols)]
                for _ in range(n_dates)
            ]
        elif name == "returns":
            return [
                [rng.gauss(0.0005, 0.02) for _ in range(n_symbols)]
                for _ in range(n_dates)
            ]
        elif name == "market_cap":
            return self._generate_price_series(
                n_dates, n_symbols, rng, drift=0.0002, vol=0.01, base=1e9
            )
        elif name in ("momentum_1m", "momentum_3m", "momentum_12m"):
            window = {
                "momentum_1m": 21,
                "momentum_3m": 63,
                "momentum_12m": 252,
            }.get(name, 21)
            return [
                [rng.gauss(0.01, 0.08) for _ in range(n_symbols)]
                for _ in range(n_dates)
            ]
        elif name in ("volatility_1m", "volatility_3m"):
            return [
                [abs(rng.gauss(0.02, 0.01)) for _ in range(n_symbols)]
                for _ in range(n_dates)
            ]
        elif name == "rsi_14":
            return [
                [30.0 + rng.random() * 40.0 for _ in range(n_symbols)]
                for _ in range(n_dates)
            ]
        elif name == "beta":
            return [
                [0.5 + rng.random() * 1.5 for _ in range(n_symbols)]
                for _ in range(n_dates)
            ]
        else:
            # Generic mean-reverting signal
            return [
                [rng.gauss(0.0, 1.0) for _ in range(n_symbols)]
                for _ in range(n_dates)
            ]

    @staticmethod
    def _generate_price_series(
        n_dates: int,
        n_symbols: int,
        rng: random.Random,
        drift: float = 0.0003,
        vol: float = 0.015,
        base: float = 100.0,
    ) -> list[list[float]]:
        """Generate correlated geometric Brownian motion price series."""
        # Initialize starting prices
        prices = [[base * (0.5 + rng.random()) for _ in range(n_symbols)]]
        for _ in range(1, n_dates):
            # Market factor (common to all stocks)
            market_return = rng.gauss(drift, vol * 0.6)
            new_row = []
            for prev_price in prices[-1]:
                stock_return = rng.gauss(0.0, vol * 0.8) + market_return
                new_row.append(prev_price * math.exp(stock_return))
            prices.append(new_row)
        return prices


__all__ = ["SyntheticDataProvider"]

"""Market data structures for the local backtest engine.

Split from :mod:`brain_alpha_ops.research.local_backtest_engine` (P2-14,
2026-06-13). Defines the cross-sectional market data shape used by every
downstream component in the local backtest pipeline.

This module is intentionally dependency-free: importing it does not pull in
the heavier evaluator, portfolio constructor, or metrics computer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketDataFrame:
    """A simple cross-sectional market data frame.

    Columns map field names to 2D arrays: rows = dates, columns = stocks.
    """
    fields: dict[str, list[list[float]]] = field(default_factory=dict)
    dates: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    n_dates: int = 0
    n_symbols: int = 0

    def get(self, field: str) -> list[list[float]]:
        return self.fields.get(field, [])

    def column(self, field: str, date_idx: int) -> list[float]:
        rows = self.fields.get(field, [])
        if date_idx < len(rows):
            return list(rows[date_idx])
        return [0.0] * self.n_symbols

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": self.fields,
            "dates": self.dates,
            "symbols": self.symbols,
            "n_dates": self.n_dates,
            "n_symbols": self.n_symbols,
        }


__all__ = ["MarketDataFrame"]

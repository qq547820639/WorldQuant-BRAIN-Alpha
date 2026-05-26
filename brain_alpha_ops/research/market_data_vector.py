"""Vectorized local market-data views without heavy runtime dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from brain_alpha_ops.research.market_data_cache import MarketDataCache


@dataclass(frozen=True)
class VectorizedMarketDataView:
    fields: tuple[str, ...]
    symbols: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "schema_version": "market_data_vector.v1",
            "source": self.source,
            "field_count": len(self.fields),
            "symbol_count": len(self.symbols),
            "row_count": len(self.matrix),
            "fields": list(self.fields),
            "symbols": list(self.symbols),
            "matrix": [list(row) for row in self.matrix],
            "column_stats": self.column_stats(),
        }

    def column_stats(self) -> list[dict[str, Any]]:
        stats: list[dict[str, Any]] = []
        for column, field in enumerate(self.fields):
            values = [row[column] for row in self.matrix if column < len(row)]
            if not values:
                continue
            stats.append(
                {
                    "field": field,
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": round(mean(values), 6),
                }
            )
        return stats


class VectorizedMarketDataStore:
    """Build deterministic symbol x feature matrices from the local cache."""

    def __init__(self, storage_dir: str | Path = "data") -> None:
        self.cache = MarketDataCache(storage_dir)

    def build_view(self, *, fields: list[str] | None = None, limit_symbols: int = 200) -> dict[str, Any]:
        payload = self.cache.load()
        if not payload.get("ok"):
            return payload
        symbols_payload = payload.get("symbols") if isinstance(payload.get("symbols"), dict) else {}
        selected_symbols = sorted(symbols_payload)[: max(1, int(limit_symbols or 1))]
        selected_fields = _select_fields(symbols_payload, fields)
        matrix: list[tuple[float, ...]] = []
        for symbol in selected_symbols:
            records = symbols_payload.get(symbol) if isinstance(symbols_payload.get(symbol), list) else []
            matrix.append(tuple(_aggregate_field(records, field) for field in selected_fields))
        view = VectorizedMarketDataView(
            fields=tuple(selected_fields),
            symbols=tuple(selected_symbols),
            matrix=tuple(matrix),
            source=str(payload.get("source") or "market_data_cache"),
        )
        return view.to_dict()


def build_vectorized_market_data(storage_dir: str | Path = "data", *, fields: list[str] | None = None, limit_symbols: int = 200) -> dict[str, Any]:
    return VectorizedMarketDataStore(storage_dir).build_view(fields=fields, limit_symbols=limit_symbols)


def _select_fields(symbols_payload: dict[str, Any], fields: list[str] | None) -> list[str]:
    requested = [str(field).strip() for field in fields or [] if str(field).strip()]
    if requested:
        return requested
    discovered: set[str] = set()
    for records in symbols_payload.values():
        for record in records if isinstance(records, list) else []:
            values = record.get("values") if isinstance(record, dict) and isinstance(record.get("values"), dict) else {}
            discovered.update(str(key) for key in values)
    return sorted(discovered)[:50]


def _aggregate_field(records: list[Any], field: str) -> float:
    values: list[float] = []
    for record in records:
        row_values = record.get("values") if isinstance(record, dict) and isinstance(record.get("values"), dict) else {}
        value = row_values.get(field)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return round(mean(values), 6) if values else 0.0

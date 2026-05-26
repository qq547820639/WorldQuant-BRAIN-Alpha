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
    missing_counts: tuple[int, ...] = ()
    normalized: bool = False

    def to_dict(self) -> dict[str, Any]:
        missing_total = sum(self.missing_counts)
        cell_count = max(1, len(self.fields) * len(self.symbols))
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
            "normalized": self.normalized,
            "missing_value_count": missing_total,
            "missing_value_ratio": round(missing_total / cell_count, 6),
            "row_stats": self.row_stats(),
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
                    "missing_count": self.missing_counts[column] if column < len(self.missing_counts) else 0,
                }
            )
        return stats

    def row_stats(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, symbol in enumerate(self.symbols):
            values = list(self.matrix[index]) if index < len(self.matrix) else []
            rows.append(
                {
                    "symbol": symbol,
                    "field_count": len(values),
                    "non_zero_count": sum(1 for value in values if value != 0.0),
                    "mean": round(mean(values), 6) if values else 0.0,
                }
            )
        return rows


class VectorizedMarketDataStore:
    """Build deterministic symbol x feature matrices from the local cache."""

    def __init__(self, storage_dir: str | Path = "data") -> None:
        self.cache = MarketDataCache(storage_dir)

    def build_view(
        self,
        *,
        fields: list[str] | None = None,
        limit_symbols: int = 200,
        min_field_coverage: float = 0.0,
        normalize: bool = False,
    ) -> dict[str, Any]:
        payload = self.cache.load()
        if not payload.get("ok"):
            return payload
        symbols_payload = payload.get("symbols") if isinstance(payload.get("symbols"), dict) else {}
        selected_symbols = sorted(symbols_payload)[: max(1, int(limit_symbols or 1))]
        selected_fields = _select_fields(symbols_payload, fields, min_field_coverage=min_field_coverage)
        rows: list[list[float]] = []
        missing_counts = [0 for _field in selected_fields]
        for symbol in selected_symbols:
            records = symbols_payload.get(symbol) if isinstance(symbols_payload.get(symbol), list) else []
            row: list[float] = []
            for field_index, field in enumerate(selected_fields):
                value, missing = _aggregate_field(records, field)
                if missing:
                    missing_counts[field_index] += 1
                row.append(value)
            rows.append(row)
        matrix = _normalize_matrix(rows) if normalize else rows
        view = VectorizedMarketDataView(
            fields=tuple(selected_fields),
            symbols=tuple(selected_symbols),
            matrix=tuple(tuple(row) for row in matrix),
            source=str(payload.get("source") or "market_data_cache"),
            missing_counts=tuple(missing_counts),
            normalized=bool(normalize),
        )
        result = view.to_dict()
        result["cache_health"] = dict(payload.get("cache_health") or {})
        return result


def build_vectorized_market_data(
    storage_dir: str | Path = "data",
    *,
    fields: list[str] | None = None,
    limit_symbols: int = 200,
    min_field_coverage: float = 0.0,
    normalize: bool = False,
) -> dict[str, Any]:
    return VectorizedMarketDataStore(storage_dir).build_view(
        fields=fields,
        limit_symbols=limit_symbols,
        min_field_coverage=min_field_coverage,
        normalize=normalize,
    )


def _select_fields(symbols_payload: dict[str, Any], fields: list[str] | None, *, min_field_coverage: float = 0.0) -> list[str]:
    requested = [str(field).strip() for field in fields or [] if str(field).strip()]
    if requested:
        return requested
    discovered: dict[str, set[str]] = {}
    total_symbols = max(1, len(symbols_payload))
    safe_min = min(max(float(min_field_coverage or 0.0), 0.0), 1.0)
    for symbol, records in symbols_payload.items():
        for record in records if isinstance(records, list) else []:
            values = record.get("values") if isinstance(record, dict) and isinstance(record.get("values"), dict) else {}
            for key in values:
                discovered.setdefault(str(key), set()).add(str(symbol))
    return [
        field
        for field, symbols in sorted(discovered.items())
        if len(symbols) / total_symbols >= safe_min
    ][:50]


def _aggregate_field(records: list[Any], field: str) -> tuple[float, bool]:
    values: list[float] = []
    for record in records:
        row_values = record.get("values") if isinstance(record, dict) and isinstance(record.get("values"), dict) else {}
        value = row_values.get(field)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return (round(mean(values), 6), False) if values else (0.0, True)


def _normalize_matrix(rows: list[list[float]]) -> list[list[float]]:
    if not rows:
        return []
    column_count = max((len(row) for row in rows), default=0)
    columns: list[list[float]] = []
    for column in range(column_count):
        values = [row[column] if column < len(row) else 0.0 for row in rows]
        min_value = min(values)
        max_value = max(values)
        span = max_value - min_value
        if span == 0:
            columns.append([0.0 for _value in values])
        else:
            columns.append([round((value - min_value) / span, 6) for value in values])
    return [
        [columns[column][row_index] for column in range(column_count)]
        for row_index in range(len(rows))
    ]

"""Lightweight market-data cache helpers for local research workflows.

The cache is intentionally simple: JSON/JSONL records are normalized into
symbol-level series and compact lookup statistics. It is not a full market
warehouse, but it gives the local stack a reusable data-access layer for
screening, search, and observability.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

from brain_alpha_ops.jsonl import read_jsonl_records


DEFAULT_MARKET_CACHE_FILENAME = "market_data_cache.json"
DEFAULT_MARKET_CACHE_SOURCE = "local_market_cache"


@dataclass
class MarketDataRecord:
    symbol: str
    timestamp: str
    values: dict[str, float] = field(default_factory=dict)
    source: str = DEFAULT_MARKET_CACHE_SOURCE

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "values": dict(self.values),
            "source": self.source,
        }


class MarketDataCache:
    """Best-effort market-data cache backed by JSON or JSONL files."""

    def __init__(self, storage_dir: str | Path = "data") -> None:
        self.storage_dir = Path(storage_dir)
        self.cache_path = self.storage_dir / DEFAULT_MARKET_CACHE_FILENAME
        self.jsonl_sources = (
            self.storage_dir / "official_fields.json",
            self.storage_dir / "official_operators.json",
            self.storage_dir / "official_datasets.json",
        )

    def refresh_from_records(self, records: list[dict[str, Any]], *, source: str = DEFAULT_MARKET_CACHE_SOURCE) -> dict[str, Any]:
        safe_records = [dict(row) for row in records if isinstance(row, dict)]
        grouped = self._group_records(safe_records, source=source)
        ingested_count = sum(len(items) for items in grouped.values())
        payload = {
            "ok": True,
            "schema_version": "market_data_cache.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "record_count": len(safe_records),
            "ingested_count": ingested_count,
            "dropped_count": max(0, len(records) - ingested_count),
            "symbol_count": len(grouped),
            "symbols": {symbol: [record.to_dict() for record in items] for symbol, items in grouped.items()},
            "symbol_stats": self._symbol_stats(grouped),
            "field_stats": self._field_stats(grouped),
            "time_range": self._time_range(grouped),
            "cache_health": self._cache_health(grouped),
        }
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def load(self) -> dict[str, Any]:
        if not self.cache_path.is_file():
            return {
                "ok": False,
                "schema_version": "market_data_cache.v1",
                "source": DEFAULT_MARKET_CACHE_SOURCE,
                "record_count": 0,
                "symbol_count": 0,
                "symbols": {},
                "symbol_stats": [],
                "error_code": "CACHE_NOT_BUILT",
                "error": "market data cache has not been refreshed",
            }
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "schema_version": "market_data_cache.v1",
                "source": DEFAULT_MARKET_CACHE_SOURCE,
                "record_count": 0,
                "symbol_count": 0,
                "symbols": {},
                "symbol_stats": [],
                "error_code": "CACHE_READ_FAILED",
                "error": str(exc),
            }
        if not isinstance(payload, dict):
            return {
                "ok": False,
                "schema_version": "market_data_cache.v1",
                "source": DEFAULT_MARKET_CACHE_SOURCE,
                "record_count": 0,
                "symbol_count": 0,
                "symbols": {},
                "symbol_stats": [],
                "error_code": "CACHE_INVALID",
                "error": "market data cache payload is not a mapping",
            }
        return payload

    def refresh_from_jsonl(self, source_file: str = "cloud_alphas.jsonl", *, limit: int = 5000) -> dict[str, Any]:
        path = self.storage_dir / source_file
        rows = read_jsonl_records(path, limit=limit) if path.is_file() else []
        records = [self._record_from_json_row(row) for row in rows if isinstance(row, dict)]
        return self.refresh_from_records(records, source=source_file)

    def refresh_from_path(self, path: str | Path, *, source: str | None = None, limit: int = 5000) -> dict[str, Any]:
        source_path = Path(path)
        rows = _read_records_from_path(source_path, limit=limit)
        records = [self._record_from_json_row(row) for row in rows if isinstance(row, dict)]
        payload = self.refresh_from_records(records, source=source or source_path.name)
        payload["source_files"] = [
            {
                "path": str(source_path),
                "exists": source_path.is_file(),
                "record_count": len(rows),
            }
        ]
        return payload

    def refresh_from_paths(self, paths: list[str | Path], *, limit_per_source: int = 5000) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        source_files: list[dict[str, Any]] = []
        for item in paths:
            source_path = Path(item)
            rows = _read_records_from_path(source_path, limit=limit_per_source)
            source_files.append(
                {
                    "path": str(source_path),
                    "exists": source_path.is_file(),
                    "record_count": len(rows),
                }
            )
            records.extend(self._record_from_json_row(row) for row in rows if isinstance(row, dict))
        payload = self.refresh_from_records(records, source=";".join(path.name for path in map(Path, paths) if str(path).strip()) or "multi_source")
        payload["source_files"] = source_files
        payload["limit_per_source"] = max(1, int(limit_per_source or 1))
        return payload

    def summary(self) -> dict[str, Any]:
        payload = self.load()
        if not payload.get("ok"):
            return payload
        symbols = payload.get("symbols") if isinstance(payload.get("symbols"), dict) else {}
        return {
            "ok": True,
            "schema_version": "market_data_cache.summary.v1",
            "source": payload.get("source", DEFAULT_MARKET_CACHE_SOURCE),
            "record_count": int(payload.get("record_count") or 0),
            "ingested_count": int(payload.get("ingested_count") or 0),
            "symbol_count": int(payload.get("symbol_count") or len(symbols)),
            "symbol_stats": list(payload.get("symbol_stats") or [])[:10],
            "top_symbols": list(payload.get("symbol_stats") or [])[:10],
            "field_stats": list(payload.get("field_stats") or [])[:20],
            "top_fields": list(payload.get("field_stats") or [])[:10],
            "time_range": dict(payload.get("time_range") or {}),
            "cache_health": dict(payload.get("cache_health") or {}),
            "cache_path": str(self.cache_path),
        }

    def _group_records(self, records: list[dict[str, Any]], *, source: str) -> dict[str, list[MarketDataRecord]]:
        grouped: dict[str, list[MarketDataRecord]] = defaultdict(list)
        for row in records:
            symbol = _text(row.get("symbol") or row.get("id") or row.get("alpha_id") or row.get("official_alpha_id"))
            if not symbol:
                continue
            timestamp = _text(row.get("timestamp") or row.get("updated_at") or row.get("saved_at") or row.get("loaded_at"))
            values = _numeric_values(row)
            grouped[symbol].append(
                MarketDataRecord(
                    symbol=symbol,
                    timestamp=timestamp,
                    values=values,
                    source=source,
                )
            )
        return dict(grouped)

    def _symbol_stats(self, grouped: dict[str, list[MarketDataRecord]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for symbol, records in grouped.items():
            numeric_fields = Counter()
            latest_timestamp = ""
            for record in records:
                numeric_fields.update(record.values.keys())
                if record.timestamp >= latest_timestamp:
                    latest_timestamp = record.timestamp
            rows.append(
                {
                    "symbol": symbol,
                    "record_count": len(records),
                    "field_count": len(numeric_fields),
                    "latest_timestamp": latest_timestamp,
                }
            )
        rows.sort(key=lambda item: (-int(item["record_count"]), str(item["symbol"])))
        return rows

    def _field_stats(self, grouped: dict[str, list[MarketDataRecord]]) -> list[dict[str, Any]]:
        field_counts: Counter[str] = Counter()
        symbol_counts: dict[str, set[str]] = defaultdict(set)
        for symbol, records in grouped.items():
            for record in records:
                for field_name in record.values:
                    field_counts[field_name] += 1
                    symbol_counts[field_name].add(symbol)
        rows = [
            {
                "field": field_name,
                "record_count": count,
                "symbol_count": len(symbol_counts[field_name]),
                "coverage_ratio": round(len(symbol_counts[field_name]) / max(1, len(grouped)), 6),
            }
            for field_name, count in field_counts.items()
        ]
        rows.sort(key=lambda item: (-int(item["symbol_count"]), -int(item["record_count"]), str(item["field"])))
        return rows

    def _time_range(self, grouped: dict[str, list[MarketDataRecord]]) -> dict[str, str]:
        timestamps = sorted(
            record.timestamp
            for records in grouped.values()
            for record in records
            if record.timestamp
        )
        return {
            "start": timestamps[0] if timestamps else "",
            "end": timestamps[-1] if timestamps else "",
        }

    def _cache_health(self, grouped: dict[str, list[MarketDataRecord]]) -> dict[str, Any]:
        record_count = sum(len(records) for records in grouped.values())
        field_count = len({field_name for records in grouped.values() for record in records for field_name in record.values})
        empty_value_rows = sum(1 for records in grouped.values() for record in records if not record.values)
        return {
            "ready": bool(grouped),
            "symbol_count": len(grouped),
            "record_count": record_count,
            "field_count": field_count,
            "empty_value_rows": empty_value_rows,
            "empty_value_ratio": round(empty_value_rows / max(1, record_count), 6),
            "bounded_local_cache": True,
        }

    def _record_from_json_row(self, row: dict[str, Any]) -> dict[str, Any]:
        symbol = _text(row.get("symbol") or row.get("id") or row.get("alpha_id") or row.get("official_alpha_id"))
        values = _numeric_values(row)
        if "symbol" not in values and symbol:
            values["symbol_hash"] = float(len(symbol))
        return {
            "symbol": symbol,
            "timestamp": _text(row.get("timestamp") or row.get("updated_at") or row.get("saved_at")),
            **values,
        }


def build_market_data_cache(storage_dir: str | Path = "data") -> MarketDataCache:
    return MarketDataCache(storage_dir)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_records_from_path(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    safe_limit = max(1, int(limit or 1))
    if path.suffix.lower() == ".jsonl":
        return read_jsonl_records(path, limit=safe_limit)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return _records_from_json_payload(payload)[-safe_limit:]


def _records_from_json_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    symbols = payload.get("symbols")
    if isinstance(symbols, dict):
        rows: list[dict[str, Any]] = []
        for symbol, records in symbols.items():
            for record in records if isinstance(records, list) else []:
                if not isinstance(record, dict):
                    continue
                values = record.get("values") if isinstance(record.get("values"), dict) else {}
                rows.append(
                    {
                        "symbol": record.get("symbol") or symbol,
                        "timestamp": record.get("timestamp", ""),
                        **values,
                    }
                )
        return rows

    for key in ("records", "rows", "items", "results", "alphas", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _records_from_json_payload(value)
            if nested:
                return nested

    if _text(payload.get("symbol") or payload.get("id") or payload.get("alpha_id") or payload.get("official_alpha_id")):
        return [dict(payload)]
    return []


def _numeric_values(row: dict[str, Any]) -> dict[str, float]:
    ignored = {
        "symbol",
        "id",
        "alpha_id",
        "official_alpha_id",
        "timestamp",
        "updated_at",
        "saved_at",
        "loaded_at",
        "values",
        "metrics",
        "official_metrics",
    }
    values: dict[str, float] = {}
    for source in (row, row.get("values"), row.get("metrics"), row.get("official_metrics")):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key in ignored or not isinstance(value, (int, float)):
                continue
            values[str(key)] = _float(value)
    return values

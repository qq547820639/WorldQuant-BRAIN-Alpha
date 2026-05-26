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
        grouped = self._group_records(records, source=source)
        payload = {
            "ok": True,
            "schema_version": "market_data_cache.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "record_count": len(records),
            "symbol_count": len(grouped),
            "symbols": {symbol: [record.to_dict() for record in items] for symbol, items in grouped.items()},
            "symbol_stats": self._symbol_stats(grouped),
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
        rows = read_jsonl_records(source_path, limit=limit) if source_path.is_file() else []
        records = [self._record_from_json_row(row) for row in rows if isinstance(row, dict)]
        return self.refresh_from_records(records, source=source or source_path.name)

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
            "symbol_count": int(payload.get("symbol_count") or len(symbols)),
            "symbol_stats": list(payload.get("symbol_stats") or [])[:10],
            "top_symbols": list(payload.get("symbol_stats") or [])[:10],
            "cache_path": str(self.cache_path),
        }

    def _group_records(self, records: list[dict[str, Any]], *, source: str) -> dict[str, list[MarketDataRecord]]:
        grouped: dict[str, list[MarketDataRecord]] = defaultdict(list)
        for row in records:
            symbol = _text(row.get("symbol") or row.get("id") or row.get("alpha_id") or row.get("official_alpha_id"))
            if not symbol:
                continue
            timestamp = _text(row.get("timestamp") or row.get("updated_at") or row.get("saved_at") or row.get("loaded_at"))
            values = {
                key: _float(value)
                for key, value in row.items()
                if key not in {"symbol", "id", "alpha_id", "official_alpha_id", "timestamp"} and isinstance(value, (int, float))
            }
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

    def _record_from_json_row(self, row: dict[str, Any]) -> dict[str, Any]:
        symbol = _text(row.get("symbol") or row.get("id") or row.get("alpha_id") or row.get("official_alpha_id"))
        values = {
            key: value
            for key, value in row.items()
            if isinstance(value, (int, float))
        }
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

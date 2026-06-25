"""Parquet / CSV cache layer for the ashare_adapter package."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_error_message, redact_text

from ._state import logger, pa, pq, _pkg


class CacheStore:
    """Simple keyed cache with Parquet (preferred) or JSON (fallback)."""

    def __init__(self, cache_dir: str | Path = "data/ashare_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> list[dict[str, Any]] | None:
        """Load cached data by key.  Returns None on miss or corruption."""
        if _pkg()._PARQUET_AVAILABLE:
            path = self.cache_dir / f"{key}.parquet"
            if path.is_file():
                try:
                    table = pq.read_table(str(path))
                    return table.to_pylist()
                except Exception as exc:
                    logger.warning(
                        "Parquet read failed for %s: %s — re-fetching",
                        redact_text(key, max_length=120),
                        redact_error_message(exc),
                    )
                    return None
        # Fallback: JSON
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
        return None

    def put(self, key: str, rows: list[dict[str, Any]]) -> None:
        """Persist rows to cache under the given key."""
        if _pkg()._PARQUET_AVAILABLE:
            path = self.cache_dir / f"{key}.parquet"
            try:
                table = pa.Table.from_pylist(rows)
                pq.write_table(table, str(path))
                return
            except Exception as exc:
                logger.warning(
                    "Parquet write failed for %s: %s — using JSON fallback",
                    redact_text(key, max_length=120),
                    redact_error_message(exc),
                )
        # Fallback: JSON
        path = self.cache_dir / f"{key}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")

    def list_keys(self) -> list[str]:
        keys: set[str] = set()
        for suffix in (".parquet", ".json"):
            for f in self.cache_dir.glob(f"*{suffix}"):
                keys.add(f.stem)
        return sorted(keys)

    def clear(self) -> int:
        count = 0
        for f in self.cache_dir.glob("*"):
            if f.suffix in (".parquet", ".json"):
                f.unlink()
                count += 1
        return count

"""Manifest helpers for optional SQLite indexes over JSONL audit logs."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Iterable

from brain_alpha_ops.jsonl import count_jsonl_records


SQLITE_INDEX_MANIFEST_SCHEMA_VERSION = "sqlite_index_manifest.v1"


def build_sqlite_index_manifest(
    *,
    storage_dir: str | Path,
    db_path: str | Path,
    source_files: Iterable[str],
    indexed_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    storage = Path(storage_dir)
    db = Path(db_path)
    db_exists = db.is_file()
    db_mtime = db.stat().st_mtime if db_exists else 0.0
    sources: dict[str, dict[str, Any]] = {}
    indexed_counts = dict(indexed_counts or {})
    stale_sources: list[str] = []
    missing_sources: list[str] = []
    for source_file in source_files:
        path = storage / source_file
        exists = path.is_file()
        if not exists:
            missing_sources.append(source_file)
        mtime = path.stat().st_mtime if exists else 0.0
        record_count = count_jsonl_records(path) if exists else 0
        indexed_count = int(indexed_counts.get(source_file, 0) or 0)
        stale = bool(exists and (not db_exists or mtime > db_mtime + 1e-6 or (indexed_count and indexed_count < record_count)))
        if stale:
            stale_sources.append(source_file)
        sources[source_file] = {
            "exists": exists,
            "path": str(path),
            "record_count": record_count,
            "indexed_count": indexed_count,
            "missing_index_rows": max(0, record_count - indexed_count),
            "modified_at": _iso_from_epoch(mtime) if exists else "",
            "is_stale": stale,
        }
    return {
        "schema_version": SQLITE_INDEX_MANIFEST_SCHEMA_VERSION,
        "db_path": str(db),
        "db_exists": db_exists,
        "db_modified_at": _iso_from_epoch(db_mtime) if db_exists else "",
        "sources": sources,
        "missing_sources": missing_sources,
        "stale_sources": stale_sources,
        "is_stale": bool(stale_sources),
    }


def _iso_from_epoch(value: float) -> str:
    if not value:
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))

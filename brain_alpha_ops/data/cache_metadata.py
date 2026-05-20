"""Metadata helpers for persisted official context caches."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


CONTEXT_CACHE_METADATA_SCHEMA = "official_context_cache_metadata.v1"


def metadata_path_for(path: Path) -> Path:
    return path.with_name(f"{path.stem}.meta.json")


def build_context_cache_metadata(
    *,
    filename: str,
    items: list[dict[str, Any]],
    source: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    saved_at = datetime.now(timezone.utc)
    ttl = max(0, int(ttl_seconds or 0))
    completeness = _completeness(items)
    return {
        "schema_version": CONTEXT_CACHE_METADATA_SCHEMA,
        "filename": filename,
        "source": str(source or "unknown"),
        "saved_at": saved_at.isoformat(),
        "ttl_seconds": ttl,
        "expires_at": (saved_at + timedelta(seconds=ttl)).isoformat() if ttl else "",
        "sha256": _items_hash(items),
        "record_count": len(items),
        "complete": bool(items) and completeness["id_or_name_coverage"] >= 0.95,
        "completeness": completeness,
    }


def write_context_cache_metadata(
    target_path: Path,
    items: list[dict[str, Any]],
    *,
    source: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    metadata = build_context_cache_metadata(
        filename=target_path.name,
        items=items,
        source=source,
        ttl_seconds=ttl_seconds,
    )
    meta_path = metadata_path_for(target_path)
    tmp = meta_path.with_name(f".{meta_path.name}.tmp")
    tmp.write_text(json.dumps(metadata, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
    tmp.replace(meta_path)
    return metadata


def read_context_cache_metadata(target_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(metadata_path_for(target_path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _items_hash(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _completeness(items: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(items)
    if not count:
        return {
            "has_records": False,
            "id_or_name_count": 0,
            "id_or_name_coverage": 0.0,
        }
    id_or_name_count = sum(1 for item in items if str(item.get("id") or item.get("name") or "").strip())
    return {
        "has_records": True,
        "id_or_name_count": id_or_name_count,
        "id_or_name_coverage": round(id_or_name_count / count, 4),
    }

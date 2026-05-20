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


def build_cache_audit_snapshot(cache_dir: str | Path) -> dict[str, Any]:
    """Aggregate metadata for all cached context files.

    Used by fetch_official_context.py to detect staleness and by
    quality_gate.py to enforce context freshness policies.
    """
    root = Path(cache_dir)
    if not root.exists():
        return {"ok": True, "source": "empty", "files": [], "stale_count": 0, "valid_count": 0}

    now = datetime.now(timezone.utc)
    files: list[dict[str, Any]] = []
    for meta_path in sorted(root.glob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta, dict):
            continue

        data_file = root / meta.get("filename", meta_path.name.replace(".meta.json", ""))
        exists = data_file.is_file()
        expires_at = meta.get("expires_at", "")
        stale = False
        if expires_at:
            try:
                stale = datetime.fromisoformat(expires_at) <= now
            except (TypeError, ValueError):
                pass

        files.append({
            "filename": meta.get("filename", ""),
            "source": meta.get("source", "unknown"),
            "saved_at": meta.get("saved_at", ""),
            "expires_at": expires_at,
            "is_stale": not exists or stale,
            "is_available": exists,
            "record_count": meta.get("record_count", 0),
            "complete": meta.get("complete", False),
            "sha256": meta.get("sha256", "")[:12],
            "ttl_seconds": meta.get("ttl_seconds", 0),
        })

    stale_count = sum(1 for f in files if f["is_stale"])
    valid_count = sum(1 for f in files if not f["is_stale"])

    return {
        "ok": True,
        "schema_version": "cache_audit_snapshot.v1",
        "source": "local_cache_metadata",
        "cache_dir": str(root),
        "generated_at": now.isoformat(),
        "file_count": len(files),
        "stale_count": stale_count,
        "valid_count": valid_count,
        "files": files,
    }

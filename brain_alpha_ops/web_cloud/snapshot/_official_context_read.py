"""Official context file reading, cache metadata, and manifest helpers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.data.cache_metadata import read_context_cache_metadata
from brain_alpha_ops.redaction import redact_text

from ._constants import (
    CONTEXT_CACHE_MANIFEST_SCHEMA,
    OFFICIAL_CONTEXT_FILES,
    LoadConfig,
    RuntimeRoot,
    SafeErrorMessage,
    _safe_error_message,
)

logger = logging.getLogger(__name__)


def official_context_file_counts(
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for key, filename in OFFICIAL_CONTEXT_FILES:
        rows = read_official_context_json(
            filename,
            load_config=load_config,
            runtime_root=runtime_root,
            safe_error_message=safe_error_message,
        )
        counts[key] = len(rows) if isinstance(rows, list) else 0
        meta = read_official_context_metadata(
            filename,
            load_config=load_config,
            runtime_root=runtime_root,
            safe_error_message=safe_error_message,
        )
        if meta:
            metadata[filename] = enrich_context_cache_metadata(meta, rows=rows)
    if metadata:
        counts["context_cache_metadata"] = metadata
        counts["context_cache_manifest"] = context_cache_manifest(
            metadata,
            expected_files=[filename for _key, filename in OFFICIAL_CONTEXT_FILES],
        )
    return counts


def enrich_context_cache_metadata(
    metadata: dict[str, Any],
    *,
    rows: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    enriched = dict(metadata)
    current = now or datetime.now(timezone.utc)
    saved_at = parse_cache_timestamp(enriched.get("saved_at"))
    expires_at = parse_cache_timestamp(enriched.get("expires_at"))
    age_seconds = max(0, int((current - saved_at).total_seconds())) if saved_at else None
    expires_in_seconds = int((expires_at - current).total_seconds()) if expires_at else None
    is_expired = bool(expires_at and expires_at <= current)
    enriched["age_seconds"] = age_seconds
    enriched["expires_in_seconds"] = expires_in_seconds
    enriched["is_expired"] = is_expired
    enriched["is_stale"] = is_expired
    if rows is not None:
        actual_count = len(rows)
        declared_count = _metadata_int(enriched.get("record_count"))
        declared_sha = str(enriched.get("sha256") or "").strip()
        actual_sha = context_items_hash(rows) if actual_count else ""
        record_count_matches = declared_count == actual_count
        sha256_matches = bool(declared_sha) and declared_sha == actual_sha
        integrity_errors: list[str] = []
        if actual_count <= 0:
            integrity_errors.append("empty_context_file")
        if not record_count_matches:
            integrity_errors.append("record_count_mismatch")
        if not sha256_matches:
            integrity_errors.append("sha256_mismatch")
        if not bool(enriched.get("complete")):
            integrity_errors.append("metadata_incomplete")
        enriched["metadata_record_count"] = declared_count
        enriched["record_count"] = actual_count
        enriched["actual_sha256"] = actual_sha
        enriched["record_count_matches"] = record_count_matches
        enriched["sha256_matches"] = sha256_matches
        enriched["integrity_ok"] = not integrity_errors
        enriched["integrity_errors"] = integrity_errors
        # A cache is complete only when the metadata still describes the file
        # currently on disk. TTL staleness is reported separately as is_stale.
        enriched["complete"] = not integrity_errors
    return enriched


def context_items_hash(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _metadata_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def context_cache_manifest(
    metadata: dict[str, dict[str, Any]],
    *,
    expected_files: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    missing_files = [filename for filename in expected_files if filename not in metadata]
    stale_files = [
        filename
        for filename, meta in metadata.items()
        if bool(meta.get("is_stale") or meta.get("is_expired"))
    ]
    invalid_files = [
        filename
        for filename in expected_files
        if filename in metadata and not bool(metadata.get(filename, {}).get("complete"))
    ]
    record_counts = {
        filename: int(meta.get("record_count", 0) or 0)
        for filename, meta in metadata.items()
    }
    files_digest_payload = {
        filename: {
            "sha256": meta.get("sha256", ""),
            "record_count": meta.get("record_count", 0),
            "complete": bool(meta.get("complete")),
            "saved_at": meta.get("saved_at", ""),
            "expires_at": meta.get("expires_at", ""),
            "is_stale": bool(meta.get("is_stale")),
        }
        for filename, meta in sorted(metadata.items())
    }
    digest = sha256(
        json.dumps(files_digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": CONTEXT_CACHE_MANIFEST_SCHEMA,
        "generated_at": current.isoformat(),
        "expected_files": list(expected_files),
        "files": metadata,
        "file_count": len(metadata),
        "missing_files": missing_files,
        "stale_files": stale_files,
        "expired_files": stale_files,
        "invalid_files": invalid_files,
        "record_counts": record_counts,
        "record_count_total": sum(record_counts.values()),
        "complete": not missing_files and not invalid_files,
        "is_stale": bool(missing_files or stale_files or invalid_files),
        "sha256": digest,
    }


def parse_cache_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_official_context_metadata(
    filename: str,
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> dict[str, Any]:
    roots: list[Path] = []
    try:
        roots.append(Path(load_config().ops.storage_dir))
    except Exception as exc:
        logger.warning("failed to resolve configured storage dir for official context metadata: %s", safe_error_message(exc))
        roots.extend([
            runtime_root() / "data",
            Path(__file__).resolve().parents[2] / "data",
        ])
    seen: set[Path] = set()
    for root in roots:
        path = root / filename
        if path in seen:
            continue
        seen.add(path)
        metadata = read_context_cache_metadata(path)
        if metadata:
            return metadata
    return {}


def read_official_context_json(
    filename: str,
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> list[dict[str, Any]]:
    roots: list[Path] = []
    try:
        roots.append(Path(load_config().ops.storage_dir))
    except Exception as exc:
        logger.warning("failed to resolve configured storage dir for official context: %s", safe_error_message(exc))
    roots.extend([
        runtime_root() / "data",
        Path(__file__).resolve().parents[2] / "data",
    ])
    seen: set[Path] = set()
    for root in roots:
        path = root / filename
        if path in seen:
            continue
        seen.add(path)
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "failed to read official context file %s: %s",
                redact_text(path, max_length=180),
                safe_error_message(exc),
            )
            continue
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def datasets_from_fields(
    fields: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> list[dict[str, Any]]:
    datasets: dict[str, dict[str, Any]] = {}
    for field in fields or []:
        if not isinstance(field, dict):
            continue
        raw_dataset = field.get("dataset")
        if isinstance(raw_dataset, dict):
            dataset_id = str(raw_dataset.get("id") or "").strip()
            dataset_name = str(raw_dataset.get("name") or dataset_id).strip()
        else:
            dataset_id = str(field.get("dataset_id") or raw_dataset or "").strip()
            dataset_name = dataset_id
        if not dataset_id:
            continue
        row = datasets.setdefault(dataset_id, {"id": dataset_id, "name": dataset_name or dataset_id, "field_count": 0})
        row["field_count"] = int(row.get("field_count", 0) or 0) + 1
        if dataset_name and row.get("name") == dataset_id:
            row["name"] = dataset_name
    if not datasets:
        return read_official_context_json(
            "official_datasets.json",
            load_config=load_config,
            runtime_root=runtime_root,
            safe_error_message=safe_error_message,
        )
    return sorted(datasets.values(), key=lambda item: (-int(item.get("field_count", 0) or 0), str(item.get("id", ""))))

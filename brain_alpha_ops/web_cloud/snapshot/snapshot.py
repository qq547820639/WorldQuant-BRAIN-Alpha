"""Cloud alpha snapshot: constants, storage, cached alphas, and cloud alpha helpers.

Consolidates the former ``_constants.py``, ``_storage.py``,
``_cached_alphas.py``, and ``_cloud_alpha.py`` modules.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from brain_alpha_ops.brain_api.official_helpers import looks_non_production_alpha_id
from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.jsonl import (
    find_jsonl_record_reverse,
    iter_jsonl_records,
    read_jsonl_records,
    read_jsonl_tail_with_stats,
)
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.runtime_constants import CloudDefaults

logger = logging.getLogger(__name__)

# ── Centralized constants (source of truth: runtime_constants.py) ──
CLOUD_SYNC_STALE_SECONDS = CloudDefaults.CLOUD_SYNC_STALE_SECONDS
CONTEXT_CACHE_MANIFEST_SCHEMA = CloudDefaults.CONTEXT_CACHE_MANIFEST_SCHEMA
OFFICIAL_CONTEXT_FILES = (
    ("fields_count", "official_fields.json"),
    ("operators_count", "official_operators.json"),
    ("datasets_count", "official_datasets.json"),
)

LoadConfig = Callable[[], Any]
RuntimeRoot = Callable[[], Path]
SafeErrorMessage = Callable[[Exception], str]


def _safe_error_message(exc: Exception) -> str:
    return redact_error_message(exc)


# ---------------------------------------------------------------------------
# Storage helpers (formerly _storage.py)
# ---------------------------------------------------------------------------


def storage_jsonl_path(filename: str, *, load_config: LoadConfig = load_run_config) -> Path:
    config = load_config()
    return Path(config.ops.storage_dir) / filename


def read_storage_jsonl(filename: str, *, limit: int | None = 500, load_config: LoadConfig = load_run_config) -> list[dict[str, Any]]:
    # When limit=None the caller explicitly wants ALL records — pass max_rows=None
    # to read_jsonl_records to remove the safety cap. The caller (e.g. cloud
    # alpha snapshot) is expected to have enough memory for the full dataset.
    max_rows: int | None = None if limit is None else limit or 10_000
    return read_jsonl_records(storage_jsonl_path(filename, load_config=load_config), limit=limit, max_rows=max_rows)


def read_storage_jsonl_stats(filename: str, *, limit: int = 500, load_config: LoadConfig = load_run_config) -> dict[str, Any]:
    return read_jsonl_tail_with_stats(storage_jsonl_path(filename, load_config=load_config), limit=limit).to_dict()


def path_modified_at(path: Path | None) -> tuple[str, int | None]:
    if not path:
        return "", None
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        return "", None
    return datetime.fromtimestamp(modified_at, timezone.utc).isoformat(), max(0, int(time.time() - modified_at))


def extract_alpha_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("results", "alphas", "data", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


# ---------------------------------------------------------------------------
# Cached user-alpha helpers (formerly _cached_alphas.py)
# ---------------------------------------------------------------------------


def latest_cached_user_alphas(
    limit: int | None = None,
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> list[dict[str, Any]]:
    for path in cached_user_alpha_paths(load_config=load_config, max_files=max_files):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("failed to read cached user alpha file %s", redact_text(path, max_length=180))
            continue
        rows = extract_alpha_rows(data)
        if rows:
            return rows if limit is None else rows[-max(1, int(limit or 1)):]
    return []


def latest_cached_user_alpha_path(
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> Path | None:
    for path in cached_user_alpha_paths(load_config=load_config, max_files=max_files):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("failed to read cached user alpha file %s", redact_text(path, max_length=180))
            continue
        if extract_alpha_rows(data):
            return path
    return None


def cached_user_alpha_paths(
    *,
    load_config: LoadConfig = load_run_config,
    max_files: int | None = None,
) -> list[Path]:
    config = load_config()
    cache_dir = Path(config.ops.official_api.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = Path.cwd() / cache_dir
    try:
        candidates = []
        for path in cache_dir.glob("user_alphas_*.json"):
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                continue
        ordered = [path for _mtime, path in sorted(candidates, reverse=True)]
        if max_files is None:
            return ordered
        return ordered[: max(1, int(max_files or 1))]
    except OSError:
        logger.warning("failed to list cached user alpha files from %s", redact_text(cache_dir, max_length=180))
        return []


# ---------------------------------------------------------------------------
# Cloud alpha snapshot, dedup, summary, and cache probe (formerly _cloud_alpha.py)
# ---------------------------------------------------------------------------


def cloud_alpha_snapshot(
    limit: int | None = None,
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
    stale_seconds: int = CLOUD_SYNC_STALE_SECONDS,
) -> dict[str, Any]:
    cache_path: Any | None = storage_jsonl_path("cloud_alphas.jsonl", load_config=load_config)
    all_rows = dedupe_cloud_alpha_rows(iter_jsonl_records(cache_path))
    rows = _bounded_rows(all_rows, limit)
    source = "storage"
    if not all_rows:
        cache_path = latest_cached_user_alpha_path(load_config=load_config)
        all_rows = dedupe_cloud_alpha_rows(latest_cached_user_alphas(limit=None, load_config=load_config))
        rows = _bounded_rows(all_rows, limit)
        source = "api_cache" if all_rows else "empty"
    summary = cloud_alpha_summary(
        all_rows,
        load_config=load_config,
        runtime_root=runtime_root,
        safe_error_message=safe_error_message,
    )
    summary["source"] = source
    summary["returned_count"] = len(rows)
    summary["display_limit"] = limit
    loaded_at, age_seconds = path_modified_at(cache_path if rows else None)
    summary["loaded_at"] = loaded_at
    summary["age_seconds"] = age_seconds
    summary["is_stale"] = bool(age_seconds is not None and age_seconds > stale_seconds)
    return {"alphas": rows, "summary": summary}


def cloud_alpha_cache_probe(
    *,
    load_config: LoadConfig = load_run_config,
    stale_seconds: int = CLOUD_SYNC_STALE_SECONDS,
) -> dict[str, Any]:
    """Return a lightweight cloud Alpha cache readiness summary.

    This intentionally avoids the full snapshot path, which parses, dedupes,
    sorts, and summarizes the entire JSONL file. Phase readiness only needs to
    know whether a usable production Alpha cache exists; exact counts remain
    owned by ``cloud_alpha_snapshot``.
    """
    cache_path = storage_jsonl_path("cloud_alphas.jsonl", load_config=load_config)
    row = find_jsonl_record_reverse(cache_path, predicate=is_production_cloud_alpha_row)
    if row is not None:
        loaded_at, age_seconds = path_modified_at(cache_path)
        return {
            "ok": True,
            "source": "storage",
            "loaded_at": loaded_at,
            "age_seconds": int(age_seconds or 0),
            "is_stale": bool(age_seconds is not None and age_seconds > stale_seconds),
        }

    api_cache_path = latest_cached_user_alpha_path(load_config=load_config)
    api_rows = dedupe_cloud_alpha_rows(latest_cached_user_alphas(limit=None, load_config=load_config))
    api_count = len(api_rows)
    loaded_at, age_seconds = path_modified_at(api_cache_path if api_count else None)
    return {
        "ok": api_count > 0,
        "count": api_count,
        "total": api_count,
        "source": "api_cache" if api_count else "empty",
        "loaded_at": loaded_at,
        "age_seconds": int(age_seconds or 0),
        "is_stale": bool(age_seconds is not None and age_seconds > stale_seconds),
    }


def _bounded_rows(rows: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if limit is None:
        return rows
    return rows[: max(1, int(limit or 1))]


def dedupe_cloud_alpha_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    no_id: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        alpha_id = cloud_alpha_id(row)
        if not alpha_id:
            no_id.append(row)
            continue
        if looks_non_production_alpha_id(alpha_id):
            continue
        latest[alpha_id] = row
    deduped = list(latest.values()) + no_id
    deduped.sort(key=cloud_row_sort_key, reverse=True)
    return deduped


def is_production_cloud_alpha_row(row: dict[str, Any]) -> bool:
    alpha_id = cloud_alpha_id(row)
    return bool(alpha_id and not looks_non_production_alpha_id(alpha_id))


def cloud_alpha_summary(
    rows: list[dict[str, Any]],
    *,
    load_config: LoadConfig = load_run_config,
    runtime_root: RuntimeRoot = runtime_project_root,
    safe_error_message: SafeErrorMessage = _safe_error_message,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    submitted = 0
    passed_unsubmitted = 0
    failed_unsubmitted = 0
    for row in rows:
        status = str(row.get("status", "")).strip().upper()
        metrics = row.get("metrics") or {}
        pass_fail = str(metrics.get("pass_fail", "")).strip().upper()
        status_counts[status or "UNKNOWN"] = status_counts.get(status or "UNKNOWN", 0) + 1
        if status in {"ACTIVE", "SUBMITTED", "PRODUCTION", "CONDUCTED"}:
            submitted += 1
        elif status == "UNSUBMITTED" and pass_fail == "PASS":
            passed_unsubmitted += 1
        elif status == "UNSUBMITTED" and (pass_fail == "FAIL" or metrics.get("failure_reason")):
            failed_unsubmitted += 1
    # Lazy import to avoid circular dependency at module load time.
    from .snapshot_context import official_context_file_counts

    return {
        "status": "loaded" if rows else "empty",
        "status_code": "CLOUD_CACHE_LOADED" if rows else "CLOUD_CACHE_EMPTY",
        "range": "local-cache",
        "count": len(rows),
        "scanned": len(rows),
        "total": len(rows),
        "added": 0,
        "skipped": 0,
        "failed": 0,
        "submitted_count": submitted,
        "passed_unsubmitted_count": passed_unsubmitted,
        "failed_unsubmitted_count": failed_unsubmitted,
        "status_counts": status_counts,
        **official_context_file_counts(
            load_config=load_config,
            runtime_root=runtime_root,
            safe_error_message=safe_error_message,
        ),
    }


def cloud_alpha_id(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("alpha_id") or "")


def cloud_row_sort_key(row: dict[str, Any]) -> str:
    return str(row.get("timestamp") or row.get("updated_at") or row.get("created_at") or "")

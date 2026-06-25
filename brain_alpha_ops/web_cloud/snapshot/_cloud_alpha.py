"""Cloud alpha snapshot, dedup, summary, and cache probe helpers."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from brain_alpha_ops.brain_api.official_helpers import looks_non_production_alpha_id
from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.jsonl import find_jsonl_record_reverse, iter_jsonl_records

from ._cached_alphas import (
    cached_user_alpha_paths,
    latest_cached_user_alpha_path,
    latest_cached_user_alphas,
)
from ._constants import (
    CLOUD_SYNC_STALE_SECONDS,
    LoadConfig,
    RuntimeRoot,
    SafeErrorMessage,
    _safe_error_message,
)
from ._storage import path_modified_at, storage_jsonl_path

logger = logging.getLogger(__name__)


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
    from ._official_context_read import official_context_file_counts

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

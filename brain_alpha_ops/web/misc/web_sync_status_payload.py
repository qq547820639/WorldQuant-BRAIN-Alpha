"""Sync-status payload helpers for the local web console."""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.redaction import redact_text

logger = logging.getLogger(__name__)


def with_sync_history(payload: dict[str, Any], ctx: Any, *, limit: int) -> dict[str, Any]:
    if limit <= 0:
        return {**payload, "sync_history": []}
    try:
        rows = ctx.sync_jobs.all(limit=limit)
    except Exception as exc:
        logger.warning("failed to read sync job history", exc_info=True)
        return {**payload, "sync_history": [], "sync_history_error": redact_text(str(exc))}
    return {
        **payload,
        "sync_history": [
            sync_history_item(job_id, row, ctx)
            for job_id, row in rows
            if isinstance(row, dict)
        ],
    }


def sync_history_item(job_id: str, row: dict[str, Any], ctx: Any) -> dict[str, Any]:
    progress = ctx.enrich_progress(dict(row.get("progress") or {}))
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    status = str(row.get("status") or progress.get("status") or "unknown")
    updated_at = _float_value(row.get("updated_at"))
    updated_at_ms = int(updated_at * 1000) if updated_at > 0 else _int_value(progress.get("updated_at_ms"))
    message = str(progress.get("status_message") or progress.get("message") or row.get("error") or "").strip()
    return {
        "job_id": job_id,
        "task_id": job_id,
        "status": status,
        "phase": str(progress.get("phase") or row.get("phase") or ""),
        "status_message": redact_text(message),
        "updated_at": updated_at,
        "updated_at_ms": updated_at_ms,
        "context_only": bool(progress.get("context_only") or result.get("context_only")),
        "scanned": _first_int(progress, result, "scanned"),
        "total": _first_int(progress, result, "total", "total_count"),
        "api_reported_total": _first_int(progress, result, "api_reported_total"),
        "filter_window_count": _first_int(progress, result, "filter_window_count"),
        "added": _first_int(progress, result, "added"),
        "updated": _first_int(progress, result, "updated"),
        "skipped": _first_int(progress, result, "skipped"),
        "failed": _first_int(progress, result, "failed"),
    }


def with_official_context_cache(payload: dict[str, Any], ctx: Any) -> dict[str, Any]:
    try:
        counts = ctx.official_context_file_counts()
    except Exception as exc:
        logger.warning("failed to read official context cache summary for sync status", exc_info=True)
        return {**payload, "official_context_cache": {"ok": False, "error": redact_text(str(exc))}}
    cache = {
        "ok": True,
        "fields_count": int(counts.get("fields_count", 0) or 0),
        "operators_count": int(counts.get("operators_count", 0) or 0),
        "datasets_count": int(counts.get("datasets_count", 0) or 0),
    }
    manifest = counts.get("context_cache_manifest")
    if isinstance(manifest, dict):
        cache["manifest"] = {
            "complete": bool(manifest.get("complete")),
            "is_stale": bool(manifest.get("is_stale")),
            "missing_files": list(manifest.get("missing_files") or []),
            "stale_files": list(manifest.get("stale_files") or manifest.get("expired_files") or []),
            "invalid_files": list(manifest.get("invalid_files") or []),
            "record_counts": dict(manifest.get("record_counts") or {}),
        }
    return {**payload, "official_context_cache": cache}


def _first_int(progress: dict[str, Any], result: dict[str, Any], *keys: str) -> int:
    for source in (progress, result):
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = _int_value(source.get(key))
            if value > 0:
                return value
    return 0


def _int_value(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _float_value(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 else 0.0

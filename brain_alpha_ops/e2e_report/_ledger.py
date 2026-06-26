"""Job ledger helpers for E2E report."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.e2e_report._constants import (
    LIST_PREVIEW_LIMIT,
    RESULT_SUMMARY_KEYWORDS,
    SKIPPED_RESULT_KEYS,
    _display_path,
    _numeric,
    _resolve_under_root,
)

def _compact_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _summarize_leaf(value)
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, item in value.items():
            if str(key) == "remaining_observations" and isinstance(item, list):
                compact["remaining_observations_count"] = len(item)
                continue
            if len(compact) >= 32:
                compact["truncated_keys"] = max(0, len(value) - len(compact))
                break
            compact[str(key)] = _compact_value(item, depth=depth + 1)
        return compact
    if isinstance(value, list):
        if len(value) > LIST_PREVIEW_LIMIT:
            return {
                "items_count": len(value),
                "items_preview": [_compact_value(item, depth=depth + 1) for item in value[:LIST_PREVIEW_LIMIT]],
            }
        return [_compact_value(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return redact_text(value, max_length=500)
    return value


def _summarize_leaf(value: Any) -> Any:
    if isinstance(value, dict):
        return {"keys_count": len(value), "keys_preview": [str(key) for key in list(value)[:LIST_PREVIEW_LIMIT]]}
    if isinstance(value, list):
        return {"items_count": len(value)}
    if isinstance(value, str):
        return redact_text(value, max_length=240)
    return value


def _is_result_summary_key(normalized_key: str) -> bool:
    return any(keyword in normalized_key for keyword in RESULT_SUMMARY_KEYWORDS)


def _summarize_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    summary: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        normalized = key_text.lower()
        if normalized in SKIPPED_RESULT_KEYS or normalized.endswith("_preview"):
            continue
        if isinstance(item, list):
            summary[f"{key_text}_count"] = len(item)
            continue
        if isinstance(item, dict):
            if normalized.endswith("_stats") or normalized.endswith("_counts"):
                summary[key_text] = _compact_value(item, depth=2)
            continue
        if _is_result_summary_key(normalized):
            summary[key_text] = _compact_value(item, depth=2)
        if len(summary) >= 48:
            summary["truncated_keys"] = max(0, len(value) - len(summary))
            break
    return summary


def _summarize_job(job_id: str, row: dict[str, Any]) -> dict[str, Any]:
    progress = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    return {
        "job_id": job_id,
        "status": row.get("status"),
        "cancel": bool(row.get("cancel")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "error": redact_text(row.get("error") or "", max_length=240),
        "progress": _compact_value(
            {
                "phase": progress.get("phase"),
                "percent": progress.get("percent"),
                "message": progress.get("message"),
                "status_code": progress.get("status_code"),
                "current": progress.get("current"),
                "total": progress.get("total"),
                "scanned": progress.get("scanned"),
                "failed": progress.get("failed"),
            }
        ),
        "result_summary": _summarize_result(summary or result),
    }


def _read_job_ledger(root: Path, path: str | Path, *, limit: int) -> dict[str, Any]:
    ledger_path = _resolve_under_root(root, path)
    if not ledger_path.is_file():
        return {
            "path": _display_path(ledger_path, root),
            "exists": False,
            "job_count": 0,
            "status_counts": {},
            "latest_job": None,
            "jobs_preview": [],
        }

    try:
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": _display_path(ledger_path, root),
            "exists": True,
            "ok": False,
            "error": redact_text(exc, max_length=240),
            "job_count": 0,
            "status_counts": {},
            "latest_job": None,
            "jobs_preview": [],
        }

    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else {}
    if not isinstance(raw_jobs, dict):
        raw_jobs = {}
    jobs = sorted(
        ((str(job_id), row) for job_id, row in raw_jobs.items() if isinstance(row, dict)),
        key=lambda item: _numeric(item[1].get("updated_at")),
        reverse=True,
    )
    status_counts = Counter(str(row.get("status") or "unknown") for _, row in jobs)
    preview = [_summarize_job(job_id, row) for job_id, row in jobs[:limit]]
    return {
        "path": _display_path(ledger_path, root),
        "exists": True,
        "ok": True,
        "version": payload.get("version") if isinstance(payload, dict) else None,
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "job_count": len(jobs),
        "status_counts": dict(sorted(status_counts.items())),
        "latest_job": preview[0] if preview else None,
        "jobs_preview": preview,
    }

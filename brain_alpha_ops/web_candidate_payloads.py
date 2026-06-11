"""Shared candidate payload helpers for Web route surfaces."""

from __future__ import annotations

from typing import Any


def candidate_payload(
    rows: list[dict[str, Any]],
    *,
    source: str,
    total: int | None = None,
    path: str = "",
    summary_only: bool = False,
    partial: bool = False,
    warning: str = "",
) -> dict[str, Any]:
    total_count = len(rows) if total is None else int(total)
    summary = candidate_summary(rows, total=total_count)
    returned_rows = [] if summary_only else rows
    return {
        "ok": True,
        "source": source,
        "path": path,
        "summary_only": summary_only,
        "candidates": returned_rows,
        "items": returned_rows,
        "count": len(returned_rows),
        "returned_count": len(returned_rows),
        "total_count": total_count,
        "total": total_count,
        "partial": partial,
        "warning": warning,
        **summary,
    }


def candidate_summary(rows: list[dict[str, Any]], *, total: int | None = None) -> dict[str, Any]:
    return candidate_summary_from_iter(rows, total=total)


def candidate_summary_from_iter(rows: Any, *, total: int | None = None) -> dict[str, Any]:
    counted = 0
    ready_count = 0
    blocked_count = 0
    running_backtest_count = 0
    pending_backtest_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        counted += 1
        if candidate_submission_ready(row):
            ready_count += 1
        if candidate_blocked(row):
            blocked_count += 1
        status = candidate_status(row)
        if status in {"running_backtest", "running"}:
            running_backtest_count += 1
        if status == "pending_backtest":
            pending_backtest_count += 1
    return {
        "candidate_count": int(total if total is not None else counted),
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "running_backtest_count": running_backtest_count,
        "pending_backtest_count": pending_backtest_count,
    }


def candidate_submission_ready(row: dict[str, Any]) -> bool:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return bool(
        str(row.get("lifecycle_status") or "").lower() == "submission_ready"
        or diagnosis.get("submission_ready") is True
        or gate.get("submission_ready") is True
    )


def candidate_blocked(row: dict[str, Any]) -> bool:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    return bool(
        candidate_status(row) in {"failed", "rejected", "blocked"}
        or diagnosis.get("primary_reason")
        or diagnosis.get("blocking_reasons")
        or gate.get("failed_reasons")
        or local_quality.get("passed") is False
        or local_quality.get("reasons")
    )


def candidate_status(row: dict[str, Any]) -> str:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return str(row.get("lifecycle_status") or diagnosis.get("status") or gate.get("status") or "").lower()


def has_candidate_like_rows(rows: list[Any]) -> bool:
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else row
        if candidate.get("alpha_id") or candidate.get("official_alpha_id") or candidate.get("expression"):
            return True
    return False


def candidate_result_total(result: dict[str, Any], fallback: int) -> int:
    for key in ("candidates_count", "candidate_count", "count", "total", "total_count"):
        value = result.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return max(number, fallback)
    return fallback


def compact_job_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload
    compact_result = dict(result)
    for key in ("alphas", "cloud_alphas"):
        rows = compact_result.get(key)
        if isinstance(rows, list):
            compact_result[key + "_count"] = len(rows)
            compact_result.pop(key, None)
    return {**payload, "result": compact_result}

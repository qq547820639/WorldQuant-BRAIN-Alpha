"""Helper functions for the parallel backtest planner/executor.

Split from the former ``parallel_backtest.py`` monolith (Workstream F3.9).
Logger name is hardcoded to ``brain_alpha_ops.research.parallel_backtest``
per project convention so log attribution remains stable after the split.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("brain_alpha_ops.research.parallel_backtest")

BacktestJobRunner = Callable[[dict[str, Any]], dict[str, Any]]
ProgressCallback = Callable[[dict[str, Any]], None]


def _job_batches(jobs: list[dict[str, Any]], batch_size: int) -> list[dict[str, Any]]:
    safe_size = max(1, int(batch_size or 1))
    batches: list[dict[str, Any]] = []
    for start in range(0, len(jobs), safe_size):
        chunk = jobs[start : start + safe_size]
        batches.append(
            {
                "batch_index": len(batches),
                "job_count": len(chunk),
                "first_job_index": chunk[0]["job_index"] if chunk else 0,
                "last_job_index": chunk[-1]["job_index"] if chunk else 0,
            }
        )
    return batches


def _unique_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        text = str(value or "").strip()
        marker = text.lower()
        if not text or marker in seen:
            continue
        seen.add(marker)
        rows.append(text)
    return rows


def _duplicate_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    duplicate_markers: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        marker = text.lower()
        if not text:
            continue
        if marker in seen and marker not in duplicate_markers:
            duplicates.append(text)
            duplicate_markers.add(marker)
        seen.add(marker)
    return duplicates


def _failure_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        if result.get("ok"):
            continue
        code = str(result.get("error_code") or result.get("status") or "UNKNOWN_FAILURE").strip() or "UNKNOWN_FAILURE"
        counts[code] = counts.get(code, 0) + 1
    return counts


def _emit_event(events: list[dict[str, Any]], callback: ProgressCallback | None, event: str, **data: Any) -> None:
    payload = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    events.append(payload)
    if callback is None:
        return
    try:
        callback(dict(payload))
    except Exception:
        logger.warning("parallel backtest progress callback failed; continuing execution", exc_info=True)
        return

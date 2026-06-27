"""Store-accessor helpers extracted from web_async_jobs.py to satisfy the
project's 350-line module budget. Kept private to the web.business package.

These functions abstract over the optional methods/attributes of a
``JobStoreLike`` store (``heartbeat``, ``get``, ``rows``, ``jobs``,
``is_cancelled``). They are intentionally typed with ``Any`` to avoid a
circular import with :mod:`brain_alpha_ops.web.business.web_async_jobs` and
to mirror the established helper-extraction convention (see
``brain_alpha_ops/web/handlers/_phase_helpers.py``)."""

from __future__ import annotations

from typing import Any


def _store_heartbeat(
    store: Any,
    job_id: str,
    *,
    operation: str,
    heartbeat_count: int,
) -> bool | None:
    heartbeat = getattr(store, "heartbeat", None)
    if not callable(heartbeat):
        return None
    return bool(
        heartbeat(
            job_id,
            operation=operation,
            heartbeat_count=heartbeat_count,
            source="web_async_jobs",
        )
    )


def _store_get(store: Any, job_id: str) -> dict[str, Any]:
    getter = getattr(store, "get", None)
    if callable(getter):
        row = getter(job_id)
        return row if isinstance(row, dict) else {}
    rows = getattr(store, "rows", None)
    if isinstance(rows, dict):
        row = rows.get(job_id)
        return row if isinstance(row, dict) else {}
    jobs = getattr(store, "jobs", None)
    if isinstance(jobs, dict):
        row = jobs.get(job_id)
        return row if isinstance(row, dict) else {}
    return {}


def _store_is_cancelled(store: Any, job_id: str) -> bool:
    checker = getattr(store, "is_cancelled", None)
    if callable(checker):
        return bool(checker(job_id))
    return bool(_store_get(store, job_id).get("cancel"))

"""Candidate GET route helpers for the local Web handler."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

from brain_alpha_ops.web_candidates.payloads import (
    candidate_payload,
    candidate_result_total,
    has_candidate_like_rows,
)

logger = logging.getLogger(__name__)


def get_candidates(handler: Any, parsed: Any, ctx: Any) -> None:
    query = parse_qs(parsed.query)
    summary_only = ctx.payload_truthy((query.get("summary") or ["false"])[0])
    job_id = (query.get("job_id") or [""])[0]
    if summary_only and not job_id:
        ledger_summary = candidate_ledger_summary()
        if ledger_summary is not None:
            handler._json(ledger_summary)
            return

    if job_id:
        lifecycle = ctx.lifecycle_payload(ctx.jobs, job_id, ctx.lifecycle_from_job)
        rows = lifecycle.get("records") if isinstance(lifecycle.get("records"), list) else []
        if has_candidate_like_rows(rows):
            handler._json(candidate_payload(
                rows,
                source="lifecycle",
                summary_only=summary_only,
                lifecycle_rows=candidate_lifecycle_rows(),
            ))
            return

    ledger_rows, ledger_total, ledger_path = candidate_ledger_rows()
    if ledger_rows:
        handler._json(candidate_payload(
            ledger_rows,
            source="candidates_jsonl",
            total=ledger_total,
            path=ledger_path,
            summary_only=summary_only,
            target_pool_size=candidate_target_pool_size(),
            lifecycle_rows=candidate_lifecycle_rows(),
        ))
        return

    rows, meta = latest_async_candidates(ctx.async_jobs)
    handler._json(candidate_payload(
        rows,
        source=str(meta.get("source") or "latest_async_result"),
        total=meta.get("total"),
        summary_only=summary_only,
        partial=bool(meta.get("partial")),
        warning=str(meta.get("warning") or ""),
        target_pool_size=candidate_target_pool_size(),
        lifecycle_rows=candidate_lifecycle_rows(),
    ))


def candidate_ledger_summary() -> dict[str, Any] | None:
    try:
        from brain_alpha_ops.jsonl import iter_jsonl_records
        from brain_alpha_ops.web_routes import _storage_file

        path = _storage_file("candidates.jsonl")
        if not path.is_file():
            return None
        rows = list(iter_jsonl_records(path))
        return candidate_payload(
            rows,
            source="candidates_jsonl",
            total=len(rows),
            path=str(path),
            summary_only=True,
            target_pool_size=candidate_target_pool_size(),
            lifecycle_rows=candidate_lifecycle_rows(),
        )
    except Exception:
        logger.warning("candidate ledger summary read failed; falling back to latest async result", exc_info=True)
        return None


def candidate_ledger_rows() -> tuple[list[dict[str, Any]], int, str]:
    try:
        from brain_alpha_ops.web_routes import _read_jsonl_records

        return _read_jsonl_records("candidates.jsonl")
    except Exception:
        logger.warning("candidate ledger read failed; falling back to latest async result", exc_info=True)
        return [], 0, ""


def candidate_lifecycle_rows() -> list[dict[str, Any]]:
    try:
        from brain_alpha_ops.web_routes import _read_jsonl_records

        rows, _total, _path = _read_jsonl_records("lifecycle.jsonl")
        return rows
    except Exception:
        logger.warning("candidate lifecycle history read failed; continuing without historical risk", exc_info=True)
        return []


def candidate_target_pool_size() -> int:
    try:
        # Use ``import ... as`` so the lookup hits the real module that
        # monkeypatch.setattr("brain_alpha_ops.web_routes.load_run_config", ...)
        # patches. ``from ... import`` would bind to the bridge module's
        # attribute and miss the patch.
        import brain_alpha_ops.web_routes as _wr

        return max(1, int(_wr.load_run_config().ops.budget.retained_alpha_pool_size or 10))
    except Exception:
        return 10


def latest_async_candidates(async_jobs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_jobs = getattr(async_jobs, "all", None)
    if callable(all_jobs):
        try:
            rows = all_jobs(limit=None)
        except TypeError:
            rows = all_jobs()
    else:
        rows = []
    if not rows:
        latest = getattr(async_jobs, "latest_any", None)
        if callable(latest):
            item = latest()
            rows = [item] if item else []
    for _job_id, job in rows:
        result = job.get("result") if isinstance(job, dict) else {}
        if not isinstance(result, dict):
            continue
        candidates = result.get("candidates")
        if isinstance(candidates, list) and candidates:
            return [row for row in candidates if isinstance(row, dict)], {"source": "latest_async_result"}
        preview = result.get("candidates_preview")
        if isinstance(preview, list) and preview:
            preview_rows = [row for row in preview if isinstance(row, dict)]
            total = candidate_result_total(result, len(preview_rows))
            return preview_rows, {
                "source": "latest_async_result_preview",
                "total": total,
                "partial": True,
                "warning": "candidate ledger is unavailable; showing async preview only",
            }
    return [], {"source": "latest_async_result"}

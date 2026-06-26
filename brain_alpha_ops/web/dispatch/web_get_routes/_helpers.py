"""Shared helpers for GET route handlers.

Provides query-parameter parsing and job-store lookup utilities consumed by
the route handler sub-modules.
"""
from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from ..web_handler_dispatch import (
    _error_response,
    _job_response,
)

logger = logging.getLogger("brain_alpha_ops.web.dispatch.web_get_routes")


def _positive_query_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, parsed)


def _active_job_from_any_store(
    ctx: WebHandlerDispatchContext,
) -> dict[str, Any]:
    for store, job_type in (
        (ctx.jobs, "run"),
        (ctx.sync_jobs, "sync"),
        (ctx.check_jobs, "check"),
        (ctx.async_jobs, "async"),
    ):
        payload = ctx.active_job_payload(store, ctx.enrich_progress)
        if payload.get("job_id"):
            return _job_response(
                {**payload, "job_type": job_type}, job_type=job_type
            )
    return _job_response(
        ctx.active_job_payload(ctx.jobs, ctx.enrich_progress)
    )


def _job_status_from_any_store(
    ctx: WebHandlerDispatchContext, job_id: str
) -> tuple[dict[str, Any], int]:
    for store, job_type, error in (
        (ctx.jobs, "run", "\u672a\u77e5\u4efb\u52a1"),
        (ctx.sync_jobs, "sync", "\u672a\u77e5\u540c\u6b65\u4efb\u52a1"),
        (ctx.check_jobs, "check", "\u672a\u77e5\u68c0\u67e5\u4efb\u52a1"),
        (ctx.async_jobs, "async", "\u672a\u77e5\u5f02\u6b65\u4efb\u52a1"),
    ):
        payload, status = ctx.job_status_payload(
            store, job_id, ctx.enrich_progress, error=error
        )
        if status == 200:
            return (
                _job_response(
                    {**payload, "job_type": job_type}, job_type=job_type
                ),
                status,
            )
    return (
        _error_response(
            {
                "ok": False,
                "error_code": "JOB_NOT_FOUND",
                "error": "\u672a\u627e\u5230",
            },
            fallback_kind="job_not_found",
        ),
        404,
    )

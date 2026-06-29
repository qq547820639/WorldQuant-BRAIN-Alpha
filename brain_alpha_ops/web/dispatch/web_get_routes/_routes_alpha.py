"""Alpha-related GET route handlers.

Handlers for alpha lifecycle, cloud alphas, anti-overfit, rolling validation,
backtest slots, and submit readiness.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from ..web_handler_dispatch import (
    DEFAULT_ALPHA_LIFECYCLE_LIMIT,
    MAX_ALPHA_LIFECYCLE_LIMIT,
)
from ._helpers import _positive_query_int

logger = logging.getLogger("brain_alpha_ops.web.dispatch.web_get_routes")


def _get_alpha_lifecycle(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_ALPHA_LIFECYCLE_LIMIT)])[0],
        1,
        MAX_ALPHA_LIFECYCLE_LIMIT,
    )
    handler._json(
        ctx.alpha_lifecycle_history(
            alpha_id=(query.get("alpha_id") or [""])[0],
            query=(query.get("query") or [""])[0],
            stage=(query.get("stage") or [""])[0],
            status=(query.get("status") or [""])[0],
            status_category_filter=(query.get("status_category") or [""])[0],
            limit=limit,
        )
    )


def _get_cloud_alphas(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = _positive_query_int((query.get("limit") or [None])[0])
    handler._json({"ok": True, **ctx.cloud_alpha_snapshot(limit=limit)})


def _get_lifecycle(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    job_id = (parse_qs(parsed.query).get("job_id") or [""])[0]
    handler._json(
        ctx.lifecycle_payload(ctx.jobs, job_id, ctx.lifecycle_from_job)
    )


def _get_latest_result(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(ctx.latest_result_snapshot())


def _get_anti_overfit(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    candidate_id = (
        parse_qs(parsed.query).get("candidate_id") or [""]
    )[0]
    handler._json(
        ctx.anti_overfit_snapshot(candidate_id=candidate_id)
    )


def _get_rolling_validation(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    candidate_id = (query.get("candidate_id") or [""])[0]
    windows = ctx.bounded_query_int(
        (query.get("windows") or ["4"])[0], 2, 50
    )
    handler._json(
        ctx.rolling_validation_snapshot(
            candidate_id=candidate_id, windows=windows
        )
    )


def _get_backtest_slots(
    handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web.dispatch.web_routes import _backtest_slots_payload

    handler._json(_backtest_slots_payload())


def _get_submit_readiness(
    handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web.dispatch.web_routes import _submit_readiness_payload

    handler._json(_submit_readiness_payload())

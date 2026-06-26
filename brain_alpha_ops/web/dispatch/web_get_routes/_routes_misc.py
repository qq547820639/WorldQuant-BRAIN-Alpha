"""Miscellaneous GET route handlers.

Handlers for root, config, capabilities, health, research memory/knowledge/
observability, prompt runs, sqlite lookups, assistant context/guidance/request,
profile, presets, redline scoring, checkpoint, and trends.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from ..web_handler_dispatch import (
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_LEDGER_LIMIT,
    MAX_HISTORY_LIMIT,
    MAX_LEDGER_LIMIT,
    MAX_RECORD_LOOKUP_LIMIT,
    _error_response,
)

logger = logging.getLogger("brain_alpha_ops.web.dispatch.web_get_routes")


def _get_root(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    if ctx.remote_admin_required() and not ctx.has_valid_admin_token(
        getattr(handler, "headers", {})
    ):
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "ADMIN_AUTH_REQUIRED",
                    "error": "\u8fdc\u7a0b Web \u8bbf\u95ee\u9700\u8981\u7ba1\u7406\u5458\u8ba4\u8bc1",
                }
            ),
            status=401,
        )
        return
    session_id, csrf_token = ctx.get_or_create_session(
        handler._session_id_from_cookie()
    )
    stream_token = ctx.stream_token_for_session(session_id)
    handler._html(
        ctx.render_html(csrf_token, stream_token),
        extra_headers=[
            ("Set-Cookie", ctx.session_cookie_header(session_id))
        ],
    )


def _get_config(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    # P3-3: include is_default flag so the frontend can distinguish a
    # user-saved run_config.json from the application defaults.
    from brain_alpha_ops.config._loader import (
        default_run_config_path as _default_run_config_path,
    )

    config_path = _default_run_config_path()
    is_default = not config_path.is_file()
    handler._json(
        {
            "ok": True,
            "config": ctx.public_run_config(),
            "is_default": is_default,
        }
    )


def _get_config_schema(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json({"ok": True, "schema": ctx.public_config_schema()})


def _get_capabilities(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_capability_registry import (
        build_capability_registry,
    )

    handler._json(
        build_capability_registry(
            public_config_schema=ctx.public_config_schema,
            official_context_file_counts=ctx.official_context_file_counts,
        )
    )


def _get_health(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(ctx.health_payload())


def _get_research_memory(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0],
        1,
        MAX_HISTORY_LIMIT,
    )
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 50
    )
    handler._json(
        ctx.research_memory_snapshot(limit=limit, top_n=top_n)
    )


def _get_research_knowledge(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0],
        1,
        MAX_LEDGER_LIMIT,
    )
    min_confidence = ctx.bounded_query_float(
        (query.get("min_confidence") or ["0.0"])[0], 0.0, 1.0
    )
    handler._json(
        ctx.research_knowledge_snapshot(
            limit=limit, min_confidence=min_confidence
        )
    )


def _get_research_observability(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0],
        1,
        MAX_HISTORY_LIMIT,
    )
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 50
    )
    include_cloud = ctx.payload_truthy(
        (query.get("include_cloud") or ["true"])[0]
    )
    handler._json(
        ctx.research_observability_snapshot(
            limit=limit, top_n=top_n, include_cloud=include_cloud
        )
    )


def _get_prompt_runs(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0],
        1,
        MAX_LEDGER_LIMIT,
    )
    handler._json(ctx.prompt_run_ledger_snapshot(limit=limit))


def _get_sqlite_indexes(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 100
    )
    handler._json(ctx.sqlite_index_snapshot(top_n=top_n))


def _get_sqlite_expression_lookup(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    expression = (query.get("expression") or [""])[0]
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 100
    )
    min_similarity = ctx.bounded_query_float(
        (query.get("min_similarity") or ["0.75"])[0], 0.0, 1.0
    )
    max_scan_rows = ctx.bounded_query_int(
        (query.get("max_scan_rows") or ["2000"])[0], 1, 10000
    )
    handler._json(
        ctx.sqlite_expression_lookup_payload(
            expression=expression,
            top_n=top_n,
            min_similarity=min_similarity,
            max_scan_rows=max_scan_rows,
        )
    )


def _get_sqlite_record_lookup(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    alpha_id = (query.get("alpha_id") or [""])[0]
    limit = ctx.bounded_query_int(
        (query.get("limit") or ["50"])[0], 1, MAX_RECORD_LOOKUP_LIMIT
    )
    handler._json(
        ctx.sqlite_record_lookup_payload(alpha_id=alpha_id, limit=limit)
    )


def _get_assistant_context(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0],
        1,
        MAX_HISTORY_LIMIT,
    )
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 50
    )
    include_prompt = ctx.payload_truthy(
        (query.get("include_prompt") or ["true"])[0]
    )
    include_sensitive = ctx.payload_truthy(
        (query.get("include_sensitive") or ["false"])[0]
    )
    handler._json(
        ctx.assistant_context_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
        )
    )


def _get_assistant_guidance(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_LEDGER_LIMIT)])[0],
        1,
        MAX_LEDGER_LIMIT,
    )
    raw_min_confidence = (query.get("min_confidence") or [None])[0]
    min_confidence: float | None = (
        None
        if raw_min_confidence in (None, "")
        else ctx.bounded_query_float(raw_min_confidence, 0.0, 1.0)
    )
    handler._json(
        ctx.assistant_guidance_snapshot(
            limit=limit, min_confidence=min_confidence
        )
    )


def _get_assistant_request(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    query = parse_qs(parsed.query)
    limit = ctx.bounded_query_int(
        (query.get("limit") or [str(DEFAULT_HISTORY_LIMIT)])[0],
        1,
        MAX_HISTORY_LIMIT,
    )
    top_n = ctx.bounded_query_int(
        (query.get("top_n") or ["10"])[0], 1, 50
    )
    include_prompt = ctx.payload_truthy(
        (query.get("include_prompt") or ["true"])[0]
    )
    include_draft = ctx.payload_truthy(
        (query.get("include_draft") or ["true"])[0]
    )
    include_sensitive = ctx.payload_truthy(
        (query.get("include_sensitive") or ["false"])[0]
    )
    handler._json(
        ctx.assistant_request_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_offline_draft=include_draft,
            include_sensitive=include_sensitive,
        )
    )


def _get_profile(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(ctx.profile_payload(ctx.user_profile_snapshot))


def _get_presets(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    handler._json(ctx.presets_payload(ctx.load_presets))


def _get_redline_report(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_redline_scoring import (
        handle_redline_report,
    )

    handler._json(handle_redline_report(parse_qs(parsed.query)))


def _get_scoring_health(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_redline_scoring import (
        handle_scoring_health,
    )

    handler._json(handle_scoring_health(parse_qs(parsed.query)))


def _get_checkpoint_status(
    handler: Any, parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    from brain_alpha_ops.web_redline_scoring import (
        handle_checkpoint_status,
    )

    handler._json(handle_checkpoint_status(parse_qs(parsed.query)))

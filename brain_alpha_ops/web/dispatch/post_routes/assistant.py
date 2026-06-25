from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_payload_validation import (
    validate_assistant_cross_review_payload,
    validate_assistant_guidance_save_payload,
    validate_assistant_text_payload,
)

from ..web_handler_dispatch import _validated_post_route


@_validated_post_route(
    validate_assistant_text_payload,
    "ASSISTANT_RESPONSE_PARSE_ERROR",
    assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR",
)
def _post_assistant_response_parse(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        ctx.assistant_response_parse_post_payload(
            payload, ctx.assistant_response_parse_payload
        )
    )


@_validated_post_route(
    validate_assistant_text_payload,
    "ASSISTANT_RESPONSE_GUIDANCE_ERROR",
    assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR",
)
def _post_assistant_response_guidance(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        ctx.assistant_response_guidance_post_payload(
            payload, ctx.assistant_response_guidance_payload
        )
    )


@_validated_post_route(
    validate_assistant_cross_review_payload,
    "ASSISTANT_CROSS_REVIEW_ERROR",
    assistant_error_code="ASSISTANT_CROSS_REVIEW_PARSE_ERROR",
)
def _post_assistant_cross_review(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(ctx.assistant_cross_review_payload(payload))


@_validated_post_route(
    validate_assistant_guidance_save_payload,
    "ASSISTANT_GUIDANCE_SAVE_ERROR",
    assistant_error_code="ASSISTANT_RESPONSE_PARSE_ERROR",
)
def _post_assistant_guidance(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        ctx.save_assistant_guidance_post_payload(
            payload, ctx.save_assistant_guidance_payload
        )
    )

"""POST route handlers for the structured scoring interpreter (Workstream D4.1).

Thin wrappers around ``web.misc.web_scoring_interpreter`` so the dispatch
layer can route ``/api/scoring/gate_decision`` and
``/api/scoring/multi_attribution`` through the standard validated-post
pipeline.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_payload_validation import (
    validate_alpha_action_payload,
    validate_json_object_payload,
)

from ..web_handler_dispatch import _validated_post_route


@_validated_post_route(validate_alpha_action_payload, "GATE_DECISION_ERROR")
def _post_scoring_gate_decision(
    handler: Any,
    _parsed: Any,
    _ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    from brain_alpha_ops.web_scoring_interpreter import (
        handle_scoring_gate_decision,
    )

    handler._json(handle_scoring_gate_decision(payload))


@_validated_post_route(
    validate_json_object_payload, "MULTI_ATTRIBUTION_ERROR"
)
def _post_scoring_multi_attribution(
    handler: Any,
    _parsed: Any,
    _ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    from brain_alpha_ops.web_scoring_interpreter import (
        handle_scoring_multi_attribution,
    )

    handler._json(handle_scoring_multi_attribution(payload))


__all__: list[str] = []

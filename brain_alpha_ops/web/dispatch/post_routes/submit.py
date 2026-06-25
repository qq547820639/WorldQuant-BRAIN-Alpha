from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_payload_validation import (
    validate_alpha_action_payload,
    validate_submit_batch_payload,
)

from ..web_handler_dispatch import (
    _error_response,
    _validated_post_route,
)


@_validated_post_route(validate_alpha_action_payload, "SUBMIT_ERROR")
def _post_submit(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        _error_response(
            {
                "ok": False,
                "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW",
                "error": "Web \u6d41\u7a0b\u9700\u663e\u5f0f\u5c31\u7eea\u590d\u6838\u540e\u624d\u5141\u8bb8\u771f\u5b9e\u63d0\u4ea4\u3002",
                "submitted": False,
                "state_navigation": {
                    "exit_paths": [
                        {
                            "label": "\u524d\u5f80 BRAIN \u5e73\u53f0\u624b\u52a8\u63d0\u4ea4",
                            "url": "https://platform.worldquantbrain.com/alphas",
                            "type": "external",
                        }
                    ],
                    "all_gates_passed": True,
                },
            }
        ),
        status=403,
    )


@_validated_post_route(
    validate_submit_batch_payload, "SUBMIT_BATCH_ERROR"
)
def _post_submit_batch(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(
        _error_response(
            {
                "ok": False,
                "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW",
                "error": "Web \u6d41\u7a0b\u9700\u663e\u5f0f\u5c31\u7eea\u590d\u6838\u540e\u624d\u5141\u8bb8\u771f\u5b9e\u63d0\u4ea4\u3002",
                "submitted": False,
                "state_navigation": {
                    "exit_paths": [
                        {
                            "label": "\u524d\u5f80 BRAIN \u5e73\u53f0\u624b\u52a8\u63d0\u4ea4",
                            "url": "https://platform.worldquantbrain.com/alphas",
                            "type": "external",
                        }
                    ],
                    "all_gates_passed": True,
                },
            }
        ),
        status=403,
    )

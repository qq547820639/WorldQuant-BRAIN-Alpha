from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_dispatch_context import WebHandlerDispatchContext
from brain_alpha_ops.web_payload_validation import (
    validate_json_object_payload,
)

from ..web_handler_dispatch import (
    _error_response,
    _validated_post_route,
    _with_session_credentials,
)


@_validated_post_route(validate_json_object_payload, "CONNECTION_ERROR")
def _post_test_connection(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    payload = _with_session_credentials(handler, ctx, payload)
    result = ctx.connection_test_post_payload(
        payload, ctx.test_connection
    )
    session_id = handler._session_id_from_cookie()
    if isinstance(result, dict) and result.get("ok"):
        session = ctx.mark_brain_connection_verified(
            session_id, result, payload
        )
    else:
        session = ctx.clear_brain_connection_verified(session_id)
    response = (
        result
        if isinstance(result, dict)
        else {
            "ok": False,
            "error_code": "CONNECTION_ERROR",
            "error": "\u8fde\u63a5\u6d4b\u8bd5\u5931\u8d25",
        }
    )
    if not response.get("ok"):
        response = _error_response(response)
    handler._json({**response, "session": session})


@_validated_post_route(validate_json_object_payload, "CONFIG_SAVE_ERROR")
def _post_config_save(
    handler: Any,
    _parsed: Any,
    ctx: WebHandlerDispatchContext,
    payload: dict[str, Any],
) -> None:
    handler._json(ctx.save_run_config_payload(payload))


def _post_session(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    """Create a new web session and return a usable CSRF token."""
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
    session = ctx.session_status(session_id)
    ttl = int(session.get("ttl_seconds") or 43200)
    handler._json(
        {
            "ok": True,
            "session_id": session_id[:8],
            "csrf_token": csrf_token,
            "stream_token": stream_token,
            "ttl_seconds": ttl,
            "connected": bool(session.get("connected")),
            "brain_connection_verified": bool(
                session.get("brain_connection_verified")
            ),
            "session": session,
        },
        extra_headers=[
            ("Set-Cookie", ctx.session_cookie_header(session_id))
        ],
    )


def _post_logout(
    handler: Any, _parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    response, headers = ctx.session_end_payload(
        handler._session_id_from_cookie(),
        ctx.expire_session,
        ctx.expired_session_cookie_header,
    )
    handler._json(response, extra_headers=headers)


def _post_shutdown(
    handler: Any, parsed: Any, ctx: WebHandlerDispatchContext
) -> None:
    _post_logout(handler, parsed, ctx)
    ctx.start_shutdown()


_TRENDS_FIELD_LIMITS: tuple[tuple[str, int], ...] = (
    ("candidates", 10000),
    ("submissions", 10000),
    ("cycles", 1000),
)


def _post_trends(
    handler: Any, _parsed: Any, _ctx: WebHandlerDispatchContext
) -> None:
    """POST /api/trends — \u8ffd\u52a0\u4e00\u6761\u8d8b\u52bf\u8bb0\u5f55\u3002

    \u8bf7\u6c42\u4f53\u5e94\u5305\u542b ``candidates`` (int)\u3001``submissions`` (int) \u548c\u53ef\u9009\u7684 ``cycles`` (int)\u3002
    \u6bcf\u4e2a\u53c2\u6570\u5fc5\u987b\u662f\u975e\u8d1f\u6574\u6570\u4e14\u4e0d\u8d85\u8fc7\u5404\u81ea\u4e0a\u9650
    \uff08candidates/submissions \u2264 10000\uff0ccycles \u2264 1000\uff09\u3002\u6821\u9a8c\u5931\u8d25\u8fd4\u56de 400
    \u5e76\u9644\u5e26 ``{"error": ..., "details": {field: reason}}``\u3002
    """
    from brain_alpha_ops.web.api.trends import (
        record_trend as _record_trend_to_store,
    )

    payload = handler._read_json()
    if not isinstance(payload, dict):
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "VALIDATION_ERROR",
                    "error": "\u8bf7\u6c42\u4f53\u5fc5\u987b\u662f JSON \u5bf9\u8c61",
                }
            ),
            status=400,
        )
        return

    details: dict[str, str] = {}
    values: dict[str, int] = {}
    for field, upper in _TRENDS_FIELD_LIMITS:
        raw = payload.get(field, 0)
        # \u7c7b\u578b\u6821\u9a8c\uff1a\u62d2\u7edd bool/float/str/None/list \u7b49\u975e int \u7c7b\u578b
        # \uff08bool \u662f int \u5b50\u7c7b\u9700\u5355\u72ec\u6392\u9664\uff0c\u5426\u5219 True/False \u4f1a\u88ab\u5f53\u4f5c 1/0\uff09
        if isinstance(raw, bool) or not isinstance(raw, int):
            details[field] = f"{field} \u5fc5\u987b\u662f\u6574\u6570"
            continue
        if raw < 0:
            details[field] = f"{field} \u5fc5\u987b\u662f\u975e\u8d1f\u6574\u6570"
            continue
        if raw > upper:
            details[field] = f"{field} \u8d85\u8fc7\u4e0a\u9650 {upper}"
            continue
        values[field] = raw

    if details:
        handler._json(
            _error_response(
                {
                    "ok": False,
                    "error_code": "VALIDATION_ERROR",
                    "error": "\u8d8b\u52bf\u53c2\u6570\u6821\u9a8c\u5931\u8d25",
                    "details": details,
                }
            ),
            status=400,
        )
        return

    _record_trend_to_store(
        candidates=values["candidates"],
        submissions=values["submissions"],
        completed_cycles=values["cycles"],
    )
    handler._json({"ok": True})

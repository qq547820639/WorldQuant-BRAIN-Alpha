"""Utility helpers for the HTTP handler factory.

Subpackage split (deep-optimization-phase13, Task A4) of the former
``web_http_handler.py`` monolith. This module collects the small
standalone helpers that the ``create_handler_class`` factory closes over:

  - ``_json_default``: safe JSON default for datetime/date/Decimal
  - CORS origin allowlist helpers (``_is_origin_allowed`` et al.)
  - SSE status classification helpers (``_is_terminal_status`` /
    ``_sse_event_type``)

The logger name is hardcoded to the original module path so that
``caplog``-based tests and ``monkeypatch`` of ``web_http_handler.logger``
continue to work after the split.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("brain_alpha_ops.web.dispatch.web_http_handler")


def _json_default(obj: Any) -> str:
    """Safe JSON default: handles datetime/date/Decimal, warns on unknowns."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    logger.warning(
        "JSON fallback: %s of type %s", repr(obj)[:100], type(obj).__name__
    )
    return repr(obj)


# F-05: CORS origin 白名单 — 防止反射未授权 origin
_CORS_ALLOWED_ORIGINS_CACHE: str | None = None


def _get_cors_allowed_origins() -> str:
    """Cache the CORS allowed origins env var to avoid per-request OS calls."""
    global _CORS_ALLOWED_ORIGINS_CACHE
    if _CORS_ALLOWED_ORIGINS_CACHE is None:
        _CORS_ALLOWED_ORIGINS_CACHE = os.environ.get(
            "BRAIN_ALPHA_OPS_CORS_ALLOWED_ORIGINS", ""
        )
    return _CORS_ALLOWED_ORIGINS_CACHE


def _is_origin_allowed(origin: str) -> bool:
    """Check whether the given CORS origin is in the configured allowlist.

    Default allowlist covers localhost variants.  When ``web.allow_remote=true``,
    remote origins must be explicitly listed via ``BRAIN_ALPHA_OPS_CORS_ALLOWED_ORIGINS``
    (comma-separated), e.g. ``https://brain-alpha-ops.example.com``.
    """
    if not origin:
        return False
    parsed = urlparse(origin)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    # Always allow loopback variants for local development
    if host in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return True
    # Check explicit allowlist from env
    raw = _get_cors_allowed_origins()
    if not raw:
        return False
    allowed = {entry.strip().lower() for entry in raw.split(",") if entry.strip()}
    if host in allowed:
        return True
    # Match full origin (e.g. "https://brain-alpha-ops.example.com")
    for entry in allowed:
        if entry.startswith("http://") or entry.startswith("https://"):
            try:
                if (urlparse(entry).hostname or "").lower() == host:
                    return True
            except ValueError:
                continue
    return False


def set_cors_headers(request_headers: Any, response_headers: dict[str, str]) -> None:
    """统一设置 CORS 响应头。无 Origin 时不设置 ACAO（不回退 Host 头）。

    当且仅当请求携带的 Origin 通过 ``_is_origin_allowed`` 校验时，回显该
    Origin 并附带凭据/方法/头白名单。无 Origin 或 Origin 不在白名单内时，
    仅设置 ``Vary: Origin``，不回退 Host 头构造 ACAO（避免反射未授权 origin）。
    """
    origin = request_headers.get("Origin", "")
    response_headers["Vary"] = "Origin"
    if origin and _is_origin_allowed(origin):
        response_headers["Access-Control-Allow-Origin"] = origin
        response_headers["Access-Control-Allow-Credentials"] = "true"
        response_headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response_headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Brain-Alpha-CSRF, "
            "X-Brain-Alpha-Request-ID, X-Brain-Alpha-Request-Timestamp"
        )
    # 无 Origin 或白名单外 → 不设置 ACAO（不回退 Host 头）


def _is_terminal_status(status: str) -> bool:
    return str(status or "").lower() in {
        "completed",
        "completed_with_warnings",
        "stopped",
        "failed",
        "cancelled",
        "canceled",
    }


def _sse_event_type(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized == "stream_timeout":
        return "stream_timeout"
    if normalized == "failed":
        return "error"
    if _is_terminal_status(normalized):
        return "complete"
    return "progress"

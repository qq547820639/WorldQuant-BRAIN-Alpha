"""Error-shaping, rate-limiting, and HTML rendering helpers for the local web console.

Consolidated from the former ``web_errors.py`` (error-shaping helpers),
``web_rate_limit.py`` (sliding-window rate limiter), and ``web_html.py``
(HTML loading/rendering helpers). The error-shaping helpers translate
exceptions into user-facing Chinese error payloads; ``RateLimitPolicy`` /
``RequestRateLimiter`` enforce per-client sliding-window quotas; and the HTML
helpers load/render the web console template with CSRF/stream-token injection.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict
from urllib.parse import unquote

from brain_alpha_ops.error_catalog import build_actionable_error, classify_exception
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.web_check_availability import (
    build_cloud_self_correlation_explanation,
)
from brain_alpha_ops.web_csp import (
    content_security_policy_for_html as _content_security_policy_for_html,
)
from brain_alpha_ops.web_state_contract import enrich_error_payload

_logger = logging.getLogger(__name__)

AUTH_ERROR_MARKERS = (
    "authorization",
    "cookie",
    "token",
    "password",
    "credential",
    "unauthorized",
    "forbidden",
    "incorrect authentication credentials",
)

# P0-1: BRAIN error code → Chinese translation table.
# Used by safe_error_message() to produce human-readable messages
# for end users who don't know what raw BRAIN error codes mean.
_BRAIN_ERROR_TRANSLATIONS: Dict[str, str] = {
    "AUTH_INVALID": "认证失败，用户名或密码不正确。",
    "AUTH_BEARER_INVALID": "Bearer Token 无效，请重新连接。",
    "AUTH_TOKEN_EXPIRED": "登录已过期，请重新输入凭据。",
    "RATE_LIMITED": "BRAIN 平台限流，系统将自动重试，请稍候。",
    "NETWORK_TIMEOUT": "连接 BRAIN 平台超时，请检查网络后重试。",
    "BRAIN_SERVER_ERROR": "BRAIN 平台服务异常，请稍后重试。",
    "CONNECTION_REFUSED": "无法连接到 BRAIN 平台，请确认网络正常。",
    "CONCURRENT_SIMULATION_LIMIT_EXCEEDED": "BRAIN 回测并发槽位已满，系统将等待释放后自动重试。",
}


# ═══════════════════════ Error-shaping helpers ════════════════════════
def safe_error_message(exc: Exception, *, error_code: str = "") -> str:
    """Translate an exception into a user-facing Chinese error message.

    Priority:
    1. Exact BRAIN error_code match from the translation table.
    2. Known message patterns (production mode, auth).
    3. Fallback: redacted exception text.
    """
    # P0-1: check the translation table first using the error_code.
    if error_code and error_code in _BRAIN_ERROR_TRANSLATIONS:
        return _BRAIN_ERROR_TRANSLATIONS[error_code]
    message = redact_error_message(exc)
    lowered = message.lower()
    # Also check if the redacted message contains a known error_code
    for code, translation in _BRAIN_ERROR_TRANSLATIONS.items():
        if code in message:
            return translation
    if "production mode requires" in lowered:
        return "生产模式需要：请设置 BRAIN_USERNAME 和 BRAIN_PASSWORD 环境变量"
    status_code = getattr(exc, "status_code", None)
    if status_code in (401, 403) or "http 401" in lowered or "http 403" in lowered or any(marker in lowered for marker in AUTH_ERROR_MARKERS):
        return "认证失败，请检查凭据或连接设置。"
    return message


def safe_error_payload(exc: Exception, *, error_code: str = "UNHANDLED_ERROR") -> dict:
    payload = user_error_payload(exc, error_code=error_code)
    payload["error"] = safe_error_message(exc, error_code=error_code)
    enriched = enrich_error_payload(payload)
    # E3: attach the actionable error payload (additive; existing keys kept).
    enriched["actionable"] = _build_actionable_for(exc, enriched)
    return enriched


def _build_actionable_for(exc: Exception, payload: dict) -> dict:
    """Build the actionable error payload for an exception.

    Honors any existing ``kind`` set by upstream callers (e.g. when a
    handler has already classified the error); otherwise classifies the
    exception via the catalog.  Includes retry_after when available so
    the frontend can render "expected X seconds".
    """
    context: dict[str, object] = {}
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is not None:
        try:
            context["retry_after"] = float(retry_after)
        except (TypeError, ValueError):
            pass
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        context["status_code"] = status_code
    err_code = getattr(exc, "error_code", "") or payload.get("error_code", "")
    if err_code:
        context["error_code"] = str(err_code)
    # Prefer the catalog's own classification of the exception — it
    # already maps BRAIN error_code / status_code / known strings to
    # the 11 ErrorKind values.  The web_state_contract's
    # ``user_error_kind`` uses a different taxonomy (e.g. ``session_expired``)
    # and is not directly compatible; we surface it via context instead.
    kind = classify_exception(exc)
    return build_actionable_error(kind, context=context)


def web_error_payload(exc: Exception, error_code: str) -> dict:
    payload = safe_error_payload(exc, error_code=error_code)
    text = f"{payload.get('error_code', '')} {payload.get('error', '')}".lower()
    if "cloud_self_correlation" in text:
        explanation = build_cloud_self_correlation_explanation(
            {},
            {"level": "high", "max_similarity": 0.90, "matched_alpha_id": "", "matched_status": ""},
        )
        payload["risk_explanation"] = explanation
        payload["risk_explanations"] = [explanation]
        payload["state_navigation"] = explanation.get("navigation")
    return payload


# ═══════════════════════ Request rate limiter ═════════════════════════
@dataclass(frozen=True)
class RateLimitPolicy:
    """Separate sliding-window quotas for read, write, and submit routes."""

    window_seconds: float = 1.0
    read_requests: int = 60
    write_requests: int = 20
    submit_requests: int = 5


class RequestRateLimiter:
    """Thread-safe sliding-window rate limiter with per-client buckets."""

    def __init__(
        self,
        policy: RateLimitPolicy | None = None,
        *,
        window_seconds: float | None = None,
        max_requests: int | None = None,
    ) -> None:
        if policy is None:
            limit = int(max_requests if max_requests is not None else 10)
            policy = RateLimitPolicy(
                window_seconds=float(window_seconds if window_seconds is not None else 1.0),
                read_requests=limit,
                write_requests=limit,
                submit_requests=limit,
            )
        self.policy = policy
        self._timestamps: dict[tuple[str, str], Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(
        self,
        *,
        key: str = "",
        client_addr: str = "",
        method: str = "",
        path: str = "",
        now: float | None = None,
    ) -> dict[str, object]:
        """Return a structured allow/deny decision for a request."""
        current = time.monotonic() if now is None else float(now)
        bucket = self._bucket_for(method, path)
        limit = self._limit_for(bucket)
        identity = str(key or "").strip() or f"client:{str(client_addr or '').strip() or 'anonymous'}"
        cache_key = (identity, bucket)
        window = max(0.001, float(self.policy.window_seconds))

        with self._lock:
            timestamps = self._timestamps[cache_key]
            cutoff = current - window
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(0.001, window - (current - timestamps[0]))
                return {
                    "ok": False,
                    "error_code": "RATE_LIMITED",
                    "error": f"Too many {bucket} requests; retry after {retry_after:.2f}s.",
                    "bucket": bucket,
                    "limit": limit,
                    "window_seconds": window,
                    "retry_after": retry_after,
                }
            timestamps.append(current)
            return {
                "ok": True,
                "bucket": bucket,
                "limit": limit,
                "window_seconds": window,
                "retry_after": 0.0,
            }

    @staticmethod
    def _bucket_for(method: str, path: str) -> str:
        method_upper = str(method or "GET").upper()
        path_value = str(path or "")
        if method_upper == "POST" and "submit" in path_value:
            return "submit"
        if method_upper in {"GET", "HEAD", "OPTIONS"}:
            return "read"
        return "write"

    def _limit_for(self, bucket: str) -> int:
        if bucket == "submit":
            return max(1, int(self.policy.submit_requests))
        if bucket == "write":
            return max(1, int(self.policy.write_requests))
        return max(1, int(self.policy.read_requests))


# ═══════════════════════ HTML loading and rendering ═══════════════════
CSRF_TOKEN_PLACEHOLDER = "__BRAIN_ALPHA_OPS_CSRF_TOKEN__"
STREAM_TOKEN_PLACEHOLDER = "__BRAIN_ALPHA_OPS_STREAM_TOKEN__"
MISSING_TEMPLATE_HTML = "<!doctype html><html><body><h1>Template not found</h1></body></html>"
WEB_FRONTEND_ENV = "BRAIN_ALPHA_OPS_WEB_FRONTEND"
INLINE_FRONTEND = "inline"
REACT_FRONTEND = "react"

_HTML_CACHE = ""
_HTML_CACHE_PATH: Path | None = None
_HTML_CACHE_SIGNATURE: tuple[int, int] | None = None
_HTML_LOCK = threading.RLock()


def selected_frontend(value: str | None = None) -> str:
    frontend = str(value if value is not None else os.getenv(WEB_FRONTEND_ENV, REACT_FRONTEND)).strip().lower()
    if frontend not in {INLINE_FRONTEND, REACT_FRONTEND}:
        raise ValueError(f"{WEB_FRONTEND_ENV} must be '{INLINE_FRONTEND}' or '{REACT_FRONTEND}'")
    # Graceful fallback: when React is selected but the build artifact is missing,
    # fall back to the inline frontend so the web console still loads.
    if frontend == REACT_FRONTEND:
        react_index = react_dist_path() / "index.html"
        if not react_index.is_file():
            _logger.warning(
                "React build artifact not found at %s; falling back to inline frontend.",
                react_index,
            )
            frontend = INLINE_FRONTEND
    return frontend


def safe_selected_frontend(value: str | None = None) -> str:
    """Safe version of selected_frontend that falls back to inline on invalid values.

    Used in error handling paths and other contexts where we must not raise
    (to avoid infinite error loops), but still want a sensible default.
    """
    try:
        return selected_frontend(value)
    except (ValueError, TypeError):
        return INLINE_FRONTEND


def inline_html_path() -> Path:
    """Return the path to the inline (non-React) HTML shell."""
    # __file__ is web/misc/web_errors.py, so parent.parent = web/.
    return Path(__file__).resolve().parent.parent / "index.html"


def react_dist_path() -> Path:
    return Path(__file__).resolve().parent.parent / "react_app" / "dist"


def default_html_path(frontend: str | None = None) -> Path:
    """Return the primary HTML template path.

    Priority:
      1. Explicit React selection when the build artifact exists.
      2. web/index.html as the canonical production SPA and safe fallback.
      3. React build artifact when the inline SPA is absent.
    """
    inline_path = inline_html_path()
    react_path = react_dist_path() / "index.html"
    if selected_frontend(frontend) == REACT_FRONTEND and react_path.is_file():
        return react_path
    if inline_path.is_file():
        return inline_path
    if react_path.is_file():
        return react_path
    return inline_path


def resolve_react_asset(request_path: str, frontend: str | None = None) -> tuple[bytes, str] | None:
    inline_missing_react_available = not inline_html_path().is_file() and (react_dist_path() / "index.html").is_file()
    if selected_frontend(frontend) != REACT_FRONTEND and not inline_missing_react_available:
        return None
    decoded_path = unquote(str(request_path or ""))
    if not decoded_path.startswith("/assets/"):
        return None
    assets_root = (react_dist_path() / "assets").resolve()
    candidate = (assets_root / decoded_path.removeprefix("/assets/")).resolve()
    try:
        candidate.relative_to(assets_root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return candidate.read_bytes(), content_type


def load_html(path: Path | None = None) -> str:
    global _HTML_CACHE, _HTML_CACHE_PATH, _HTML_CACHE_SIGNATURE
    if path is None:
        with _HTML_LOCK:
            template_path = default_html_path()
            signature = _html_cache_signature(template_path)
            if _HTML_CACHE and _HTML_CACHE_PATH == template_path and _HTML_CACHE_SIGNATURE == signature:
                return _HTML_CACHE
            html = template_path.read_text(encoding="utf-8") if template_path.is_file() else MISSING_TEMPLATE_HTML
            _HTML_CACHE = html
            _HTML_CACHE_PATH = template_path
            _HTML_CACHE_SIGNATURE = signature
            return html
    template_path = path
    with _HTML_LOCK:
        return template_path.read_text(encoding="utf-8") if template_path.is_file() else MISSING_TEMPLATE_HTML


def reset_html_cache() -> None:
    global _HTML_CACHE, _HTML_CACHE_PATH, _HTML_CACHE_SIGNATURE
    with _HTML_LOCK:
        _HTML_CACHE = ""
        _HTML_CACHE_PATH = None
        _HTML_CACHE_SIGNATURE = None


def _html_cache_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def render_html(csrf_token: str, stream_token: str, html: str | None = None) -> str:
    source = html if html is not None else load_html()
    source = _replace_placeholder_value(source, CSRF_TOKEN_PLACEHOLDER, csrf_token)
    return _replace_placeholder_value(source, STREAM_TOKEN_PLACEHOLDER, stream_token)


def _replace_placeholder_value(source: str, placeholder: str, value: str) -> str:
    pattern = rf"(?<![.\w$]){re.escape(placeholder)}(?![\w$])"
    return re.sub(pattern, value, source)


def content_security_policy_for_html(html: str | None = None) -> str:
    return _content_security_policy_for_html(html if html is not None else load_html())


script_hash_sources = None  # backward-compat: removed during Phase 3.x refactoring

style_hash_sources = None  # backward-compat: removed during Phase 3.x refactoring


__all__ = [
    "AUTH_ERROR_MARKERS",
    "CSRF_TOKEN_PLACEHOLDER",
    "INLINE_FRONTEND",
    "MISSING_TEMPLATE_HTML",
    "REACT_FRONTEND",
    "RateLimitPolicy",
    "RequestRateLimiter",
    "STREAM_TOKEN_PLACEHOLDER",
    "WEB_FRONTEND_ENV",
    "content_security_policy_for_html",
    "default_html_path",
    "inline_html_path",
    "load_html",
    "react_dist_path",
    "render_html",
    "reset_html_cache",
    "resolve_react_asset",
    "safe_error_message",
    "safe_error_payload",
    "safe_selected_frontend",
    "script_hash_sources",
    "selected_frontend",
    "style_hash_sources",
    "web_error_payload",
]

"""Helpers for complete user-alpha sync calls."""

from __future__ import annotations

import http.client
import urllib.error
from inspect import Parameter, signature
from typing import Any, Callable

from brain_alpha_ops.runtime_constants import ContextRefreshDefaults

# ── User-alpha transient retry constants (P2-4 centralisation) ──
# Previously duplicated verbatim across ``brain_api/official_alphas.py`` and
# ``brain_api/official_context.py``.  Now defined once here and re-exported
# from those modules for backwards compatibility.
USER_ALPHA_TRANSIENT_RETRY_STATUSES: frozenset[int] = frozenset({408, 500, 502, 503, 504})
USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS = (
    http.client.IncompleteRead,
    http.client.RemoteDisconnected,
    TimeoutError,
    urllib.error.URLError,
)
USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS: int = 3
USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS: float = 5.0

# P0-3 fix (2026-06-13): was a local duplicate of the canonical set in
# ``runtime_constants.ContextRefreshDefaults.ALLOWED_SYNC_RANGES``. The 5-element
# subset here intentionally omits ``1d`` because the BRAIN ``/users/self/alphas``
# endpoint does not accept a 1-day window. We re-export the canonical set
# under a domain-specific name to preserve the existing import surface and
# to keep the 1d guard at one location.
USER_ALPHA_SYNC_RANGES: frozenset[str] = frozenset(
    ContextRefreshDefaults.ALLOWED_SYNC_RANGES - {"1d"}
)


def list_user_alphas_for_sync(
    api: Any,
    sync_range: str = "all",
    *,
    progress_callback: Callable[[dict[str, Any]], Any] | None = None,
) -> list[dict[str, Any]]:
    """Fetch user alphas for an explicit sync, bypassing cache when supported."""

    method = api.list_user_alphas
    params, accepts_var_kw = _call_signature(method)
    kwargs: dict[str, Any] = {}
    if accepts_var_kw or "force_refresh" in params:
        kwargs["force_refresh"] = True
    if progress_callback is not None and (accepts_var_kw or "progress_callback" in params):
        kwargs["progress_callback"] = progress_callback
    if kwargs:
        return method(sync_range, **kwargs)
    if progress_callback is not None and _accepts_second_positional(params):
        return method(sync_range, progress_callback)
    return method(sync_range)


def normalize_user_alpha_sync_range(value: Any, *, default: str = "all") -> str:
    """Normalize user-alpha sync range without inventing a short default."""

    sync_range = str(value or default or "all")
    return sync_range if sync_range in USER_ALPHA_SYNC_RANGES else "all"


def sync_range_from_payload(payload: dict[str, Any] | None, *, default: str = "all") -> str:
    """Return explicit payload sync range, falling back to complete sync."""

    if not isinstance(payload, dict):
        return normalize_user_alpha_sync_range(None, default=default)
    if payload.get("syncRange") not in ("", None):
        return normalize_user_alpha_sync_range(payload.get("syncRange"), default=default)
    if payload.get("range") not in ("", None):
        return normalize_user_alpha_sync_range(payload.get("range"), default=default)
    return normalize_user_alpha_sync_range(None, default=default)


def _call_signature(method: Callable[..., Any]) -> tuple[dict[str, Parameter], bool]:
    try:
        params = signature(method).parameters
    except (TypeError, ValueError):
        return {}, False
    accepts_var_kw = any(param.kind == Parameter.VAR_KEYWORD for param in params.values())
    return dict(params), accepts_var_kw


def _accepts_second_positional(params: dict[str, Parameter]) -> bool:
    positional = [
        param
        for param in params.values()
        if param.kind in {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}
    ]
    return len(positional) >= 2

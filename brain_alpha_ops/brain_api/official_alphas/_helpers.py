"""Module-level helpers and constants for the alpha query mixins."""

from __future__ import annotations

from typing import Any

from ..official_filtering import (
    resolve_compat_alias,
)
from ..user_alpha_sync import (
    USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS as _USER_ALPHA_TRANSIENT_PAGE_RETRY_ATTEMPTS,
)
from ..user_alpha_sync import (
    USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS as _USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS,
)
from ..user_alpha_sync import (
    USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS as _USER_ALPHA_TRANSIENT_PAGE_RETRY_SECONDS,
)
from ..user_alpha_sync import (
    USER_ALPHA_TRANSIENT_RETRY_STATUSES as _USER_ALPHA_TRANSIENT_RETRY_STATUSES,
)

_DISCOVERY_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay", "dataset"})
_ALPHA_FILTER_OPTION_KEYS = frozenset({"instrument_type", "region", "universe", "delay"})


def _is_user_alpha_transient_page_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in _USER_ALPHA_TRANSIENT_RETRY_STATUSES:
        return True
    if isinstance(exc, _USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS):
        return True
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, _USER_ALPHA_TRANSIENT_PAGE_RETRY_EXCEPTIONS):
        return True
    if status_code is not None:
        return False
    text = str(exc).lower()
    return text.startswith("network error:") and any(
        marker in text
        for marker in (
            "urlopen error",
            "ssl",
            "eof",
            "timed out",
            "connection reset",
            "connection aborted",
            "remote end closed",
            "temporarily unavailable",
        )
    )


def _pop_compat_alias(filters: dict[str, Any], canonical: str, *aliases: str) -> Any:
    value = filters.pop(canonical, "")
    for alias in aliases:
        value = resolve_compat_alias(canonical, value, filters.pop(alias, ""), alias_name=alias)
    return value


def _compat_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())

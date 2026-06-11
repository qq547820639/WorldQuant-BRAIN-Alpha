"""Shared pagination limits for official BRAIN API collection endpoints."""

from __future__ import annotations


MAX_FIELDS_PAGES = None
MAX_DATASETS_PAGES = None
MAX_OPERATORS_PAGES = None
# Cloud and official capability inventories must stay complete by default.
# Safety is enforced by repeated-page detection, empty/short-page stops,
# explicit cancellation, and BRAIN offset recovery instead of arbitrary caps.
MAX_USER_ALPHAS_PAGES = None
MAX_FIELDS_ITEMS = None
MAX_DATASETS_ITEMS = None
MAX_OPERATORS_ITEMS = None


def coerce_limit(value: int | str | None, *, safety_default: int | None = None) -> int | None:
    """Coerce a pagination limit, using *safety_default* when *value* is ``None``."""
    if value is None:
        return safety_default
    return int(value)

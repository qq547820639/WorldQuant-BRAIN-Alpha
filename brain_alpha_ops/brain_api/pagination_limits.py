"""Shared pagination limits for official BRAIN API collection endpoints."""

from __future__ import annotations


MAX_FIELDS_PAGES = 200
MAX_DATASETS_PAGES = 20
MAX_OPERATORS_PAGES = 20
# User alpha inventory must stay complete by default. Safety is enforced by
# repeated-page detection, unique-item stall telemetry, explicit cancellation,
# and BRAIN offset recovery instead of an arbitrary page ceiling.
MAX_USER_ALPHAS_PAGES = None
MAX_FIELDS_ITEMS = 20_000
MAX_DATASETS_ITEMS = 2_000
MAX_OPERATORS_ITEMS = 2_000


def coerce_limit(value: int | str | None, *, safety_default: int | None = None) -> int | None:
    """Coerce a pagination limit, using *safety_default* when *value* is ``None``."""
    if value is None:
        return safety_default
    return int(value)

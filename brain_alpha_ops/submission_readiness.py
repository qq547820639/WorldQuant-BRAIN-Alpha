"""Shared production submission evidence checks."""

from __future__ import annotations

from typing import Any


REQUIRED_OFFICIAL_METRIC_FIELDS = (
    ("sharpe",),
    ("fitness",),
    ("turnover",),
    ("self_correlation", "correlation"),
    ("prod_correlation", "correlation"),
    ("weight_concentration",),
)


def missing_official_metric_fields(metrics: dict[str, Any]) -> list[str]:
    """Return canonical metric field groups missing from official evidence."""
    missing: list[str] = []
    for aliases in REQUIRED_OFFICIAL_METRIC_FIELDS:
        if not any(metrics.get(alias) not in ("", None) for alias in aliases):
            missing.append("/".join(aliases))
    return missing

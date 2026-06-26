"""Shared helpers and module-level logger for the ``candidate_pool_service_`` subpackage.

Extracted from the original ``candidate_pool_service_.py`` monolith. Holds the
module-level logger (with the original name hard-coded so log filters and
caplog assertions keep working) plus the two private free functions used by
the local-prefilter mixin.
"""

from __future__ import annotations

import logging

# Preserve the original ``brain_alpha_ops.research.candidate_pool_service_``
# logger name so downstream log filters and test caplog assertions keep
# working after the monolith was split into submodules.
logger = logging.getLogger("brain_alpha_ops.research.candidate_pool_service_")


def _local_backtest_failure_category(result: dict) -> str:
    turnover = _safe_float(result.get("turnover"))
    if turnover is not None and turnover > 0.70:
        return "high_turnover"
    reasons = " ".join(str(reason).lower() for reason in (result.get("pass_reasons") or []))
    if "turnover" in reasons and "(fail)" in reasons and ("70%" in reasons or "0.70" in reasons):
        return "high_turnover"
    return "low_signal"


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

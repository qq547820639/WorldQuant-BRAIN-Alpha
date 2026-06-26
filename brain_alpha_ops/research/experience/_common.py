"""Common helpers and constants for the experience learning subpackage.

Re-exported via ``brain_alpha_ops.research.experience``.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from brain_alpha_ops.jsonl import read_jsonl_records

# P0-4 fix (2026-06-13): all four _ratio() variants across
# research/{scoring,experience,safety,diagnostics}.py now share a single
# implementation in ``research._ratio``. The local definition below is kept
# for backward-compat with the previous module-level symbol.
from brain_alpha_ops.research._ratio import normalize_brain_ratio  # noqa: F401

if TYPE_CHECKING:
    from brain_alpha_ops.models import Candidate

logger = logging.getLogger("brain_alpha_ops.research.experience")

DEFAULT_HISTORY_LIMIT = 5000


def _num(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ratio(value: Any) -> float:
    """Backwards-compatible wrapper for the canonical BRAIN ratio normalizer.

    See :func:`brain_alpha_ops.research._ratio.normalize_brain_ratio` for the
    full rule (percentage-scale when ``abs(value) >= 2.0``).
    """
    return normalize_brain_ratio(value, bounded=False)


def _load_records(path: str, *, limit: int | None = DEFAULT_HISTORY_LIMIT) -> list[dict[str, Any]]:
    return read_jsonl_records(path, limit=limit)


def _empty_patterns(reason: str) -> dict[str, Any]:
    return {
        "sample_size": 0,
        "total_records": 0,
        "avg_sharpe": 0.0,
        "avg_fitness": 0.0,
        "field_combinations": [],
        "top_operators": [],
        "preferred_windows": [],
        "top_categories": [],
        "source": "BRAIN_official_simulation_results",
        "summary": reason,
    }

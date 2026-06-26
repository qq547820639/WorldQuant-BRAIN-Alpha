"""Constants and helpers for the official scoring system."""
from __future__ import annotations

SCORING_VERSION = "scoring-v2.4"

_MAX_SCORE_HISTORY_PER_ALPHA = 100
_MAX_SCORE_HISTORY_TOTAL_ENTRIES = 10_000

# Named thresholds extracted from hardcoded values
_SOFT_GATE_TOLERANCE = 2  # max allowed soft-gate failures (line ~404)
_TREND_DELTA_IMPROVING = 5  # score delta for "improving" trend
_TREND_DELTA_DECLINING = -5  # score delta for "declining" trend


def _gate_item_value(row: dict, key: str, default: str = "-") -> str:
    value = row.get(key, default)
    return str(value if value not in (None, "") else default)


def _format_gate_failure(row: dict) -> str:
    return (
        f"{_gate_item_value(row, 'name')} "
        f"(actual={row.get('actual', '-')} "
        f"{_gate_item_value(row, 'direction')} "
        f"{row.get('target', '-')})"
    )

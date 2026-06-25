"""Module-level constants for Alpha quality diagnostics."""

from __future__ import annotations

_REQUIRED_ALPHA_FIELDS = (
    "alpha_id",
    "expression",
    "family",
    "hypothesis",
    "data_fields",
    "operators",
)
_REQUIRED_SETTINGS_FIELDS = (
    "instrumentType",
    "region",
    "universe",
    "dataset",
    "delay",
    "decay",
    "neutralization",
    "truncation",
    "pasteurization",
    "unitHandling",
    "nanHandling",
    "language",
    "type",
)
_REQUIRED_OFFICIAL_METRICS = (
    "sharpe",
    "fitness",
    "turnover",
    "returns",
    "drawdown",
    "correlation",
)
_RESERVED_WORDS = {
    "if",
    "else",
    "and",
    "or",
    "not",
    "true",
    "false",
    "none",
}

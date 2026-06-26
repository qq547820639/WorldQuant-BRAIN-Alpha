"""Operator registry and field/node helper functions.

Extracted from the original ``hypothesis_expression_support.py`` monolith
(deep-optimization-phase13). Holds the module-level constants
(``GROUP_KEYS``, ``_OFFICIAL_OPERATOR_FALLBACK``, ``KNOWN_BRAIN_OPERATORS``),
the cached ``_current_official_operator_names`` loader, and the small AST /
window helpers (``format_window``, ``is_group_key_node``,
``first_number_literal``) used by the normalization and field-resolution
mixins.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from brain_alpha_ops.research.expression_ast import ExprNode
from brain_alpha_ops.research.fallback_generation import DEFAULT_WINDOWS

GROUP_KEYS = {"market", "sector", "industry", "subindustry"}
_OFFICIAL_OPERATOR_FALLBACK = frozenset(
    {
        "abs", "add", "and", "bucket", "days_from_last_change", "densify",
        "divide", "equal", "greater", "greater_equal", "group_backfill",
        "group_mean", "group_neutralize", "group_rank", "group_scale",
        "group_zscore", "hump", "if_else", "inverse", "is_nan",
        "kth_element", "last_diff_value", "less", "less_equal", "log",
        "max", "min", "multiply", "normalize", "not", "not_equal", "or",
        "power", "quantile", "rank", "reverse", "scale", "sign",
        "signed_power", "sqrt", "subtract", "trade_when", "ts_arg_max",
        "ts_arg_min", "ts_av_diff", "ts_backfill", "ts_corr",
        "ts_count_nans", "ts_covariance", "ts_decay_linear", "ts_delay",
        "ts_delta", "ts_mean", "ts_product", "ts_quantile", "ts_rank",
        "ts_regression", "ts_scale", "ts_std_dev", "ts_step", "ts_sum",
        "ts_zscore", "vec_avg", "vec_sum", "winsorize", "zscore",
    }
)


@lru_cache(maxsize=1)
def _current_official_operator_names() -> frozenset[str]:
    # NOTE: ``parents[3]`` (not ``parents[2]``) because this module now lives
    # one directory deeper (``research/hypothesis_expression_support/_operators.py``)
    # than the original ``research/hypothesis_expression_support.py`` monolith.
    # The resolved path remains ``<project_root>/data/official_operators.json``.
    path = Path(__file__).resolve().parents[3] / "data" / "official_operators.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _OFFICIAL_OPERATOR_FALLBACK
    names = {
        str(item.get("name", "")).lower()
        for item in payload
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }
    return frozenset(names or _OFFICIAL_OPERATOR_FALLBACK)


KNOWN_BRAIN_OPERATORS = _current_official_operator_names()


def format_window(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = float(DEFAULT_WINDOWS[0])
    if numeric.is_integer():
        return str(int(numeric))
    return str(numeric).rstrip("0").rstrip(".")


def is_group_key_node(node: ExprNode) -> bool:
    return node.kind == "identifier" and node.value in GROUP_KEYS


def first_number_literal(nodes: tuple[ExprNode, ...]) -> str:
    for node in nodes:
        if node.kind == "number":
            return node.value
        if node.children:
            value = first_number_literal(node.children)
            if value:
                return value
    return ""

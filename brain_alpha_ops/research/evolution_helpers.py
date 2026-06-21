"""Shared helpers for expression evolution modules."""

from __future__ import annotations

import hashlib
import logging
import re

logger = logging.getLogger(__name__)

# BRAIN FASTEXPR operator categories (canonical, aligned with official context snapshots).
_UNARY_OPERATORS = {
    "rank", "log", "sqrt", "abs", "sign", "inverse", "scale",
    "normalize", "zscore", "reverse",
    "ts_delta", "ts_sum", "ts_mean", "ts_std_dev", "ts_zscore",
    "ts_decay_linear", "ts_arg_max", "ts_arg_min", "ts_rank",
    "ts_av_diff", "ts_backfill", "ts_delay",
}

_BINARY_OPERATORS = {
    "add", "subtract", "multiply", "divide", "min", "max",
    "ts_corr", "ts_covariance", "ts_regression",
}

_GROUP_OPERATORS = {
    "group_neutralize", "group_rank", "group_zscore",
    "group_scale", "group_backfill",
}

_MUTABLE_OPERATORS = _UNARY_OPERATORS | _BINARY_OPERATORS | _GROUP_OPERATORS

_WINDOW_OPERATORS = {
    "ts_delta", "ts_sum", "ts_mean", "ts_std_dev", "ts_zscore",
    "ts_decay_linear", "ts_arg_max", "ts_arg_min",
    "ts_rank", "ts_av_diff", "ts_backfill", "ts_delay",
    "ts_covariance", "ts_regression", "ts_corr",
}

_WINDOW_RANGES = {
    "short": [5, 10, 20],
    "medium": [30, 60, 90, 120],
    "long": [180, 252],
}

_COMMON_FIELDS = {
    "open", "close", "high", "low", "volume", "vwap",
    "returns", "market_cap", "adv20",
}

_MAX_EXPRESSION_LENGTH = 2000
_MAX_NESTING_DEPTH = 8
_MAX_MUTATION_ATTEMPTS = 10
_MIN_EXPRESSION_LENGTH = 3


def _official_operator_names() -> set[str]:
    """Return current official operator names; empty means mutations fail closed."""
    try:
        from brain_alpha_ops.brain_api.context_defaults import get_default_operators

        rows = get_default_operators()
        return {
            str(row.get("name") or "").strip().lower()
            for row in rows
            if isinstance(row, dict) and row.get("name")
        }
    except Exception:
        logger.exception("evolution_helpers: unexpected error")
        logger.warning("official operator metadata unavailable for evolution operator filter", exc_info=True)
        return set()


def _official_field_ids() -> set[str]:
    """Return current official field identifiers; empty means field mutations fail closed."""
    try:
        from brain_alpha_ops.brain_api.context_defaults import get_default_fields

        rows = get_default_fields()
        return {
            str(row.get("id") or row.get("name") or "").strip().lower()
            for row in rows
            if isinstance(row, dict) and (row.get("id") or row.get("name"))
        }
    except Exception:
        logger.warning("official field metadata unavailable for evolution field filter", exc_info=True)
        return set()


def _operators_in_expression(expression: str) -> set[str]:
    return {
        match.group(1).lower()
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", str(expression or ""))
    }


def _expression_operators_are_official(expression: str, official_operators: set[str]) -> bool:
    if not official_operators:
        return False
    return _operators_in_expression(expression) <= official_operators


def _is_valid_expression(expr: str) -> bool:
    """Quick validity check: balanced parens, reasonable length."""
    if not expr or len(expr) > _MAX_EXPRESSION_LENGTH:
        return False
    if len(expr) < _MIN_EXPRESSION_LENGTH:
        return False
    if expr.count("(") != expr.count(")"):
        return False
    if "()" in expr:
        return False
    depth = 0
    max_depth = 0
    for ch in expr:
        if ch == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and max_depth <= _MAX_NESTING_DEPTH


def _extract_inner(expr: str) -> str:
    """Extract content inside outermost parentheses."""
    if expr.startswith("(") and expr.endswith(")"):
        depth = 0
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i == len(expr) - 1:
                    return expr[1:-1]
    for op in sorted(_MUTABLE_OPERATORS, key=lambda x: -len(x)):
        if expr.startswith(op + "(") and expr.endswith(")"):
            return expr[len(op) + 1:-1]
    return ""


def _split_args(expr: str) -> tuple[str, str]:
    """Split expression into first argument and remaining text."""
    depth = 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return expr[:i], expr[i + 1:]
    return expr, ""


def _split_top_level(expr: str, separator: str) -> list[str]:
    """Split expression at top-level separator, respecting parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    sep_len = len(separator)
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif depth == 0 and expr[i:i + sep_len] == separator:
            parts.append("".join(current).strip())
            current = []
            i += sep_len
            continue
        else:
            current.append(ch)
        i += 1
    if current:
        parts.append("".join(current).strip())
    return parts


def _tokenize(expr: str) -> list[str]:
    """Simple tokenizer for operator/sub-expression splitting."""
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in expr:
        if ch == "(":
            if current:
                tokens.append("".join(current).strip())
                current = []
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
            if depth == 0:
                tokens.append("".join(current).strip())
                current = []
        elif ch in (" ", ",", "+", "-") and depth == 0:
            if current:
                tokens.append("".join(current).strip())
                current = []
            if ch.strip():
                tokens.append(ch)
        else:
            current.append(ch)
    if current:
        tokens.append("".join(current).strip())
    return [token for token in tokens if token]


def _mutation_hash(expression: str, strategy: str) -> str:
    return hashlib.sha256(f"{expression}:{strategy}".encode()).hexdigest()[:12]

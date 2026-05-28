"""Shared argument-bounding helpers used across agent tools and web payload parsers.

This module eliminates the duplicate _bounded_int / _bounded_float / _truthy /
_candidate_argument / _expression_batch_argument definitions that previously
existed in both agent_tools.py and agent_research_tools.py.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.expression_ast import expression_key


def bounded_int(value: Any, lower: int, upper: int, *, default: int | None = None) -> int:
    """Clamp an integer value into [lower, upper].

    Args:
        value: The raw input (int, float, str, or None).
        lower: Minimum allowed value.
        upper: Maximum allowed value.
        default: Value to use when parsing fails (defaults to *lower*).

    Returns:
        Clamped integer value.
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default if default is not None else lower
    return min(max(parsed, lower), upper)


def bounded_float(value: Any, lower: float, upper: float, *, default: float | None = None) -> float:
    """Clamp a float value into [lower, upper].

    Args:
        value: The raw input (int, float, str, or None).
        lower: Minimum allowed value.
        upper: Maximum allowed value.
        default: Value to use when parsing fails (defaults to *lower*).

    Returns:
        Clamped float value.
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default if default is not None else lower
    return min(max(parsed, lower), upper)


def truthy(value: Any) -> bool:
    """Interpret a value as a boolean, accepting common string representations.

    Accepts True/true/1/yes/on; rejects False/false/0/no/off/None/empty-string.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", ""}
    if value is None:
        return False
    return bool(value)


def required_text(args: dict[str, Any], key: str) -> str:
    """Extract a non-empty string argument, raising ValueError on missing/empty."""
    value = str(args.get(key, "") or "").strip()
    if not value:
        raise ValueError(f"missing required argument: {key}")
    return value


def candidate_argument(args: dict[str, Any]) -> dict[str, Any]:
    """Build a candidate dict from tool arguments.

    Accepts either an explicit ``candidate`` dict or individual expression fields.
    """
    candidate = args.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    expression = str(args.get("expression", "") or "").strip()
    if not expression:
        raise ValueError("missing required argument: expression")
    return {
        "alpha_id": str(args.get("alpha_id", "agent_candidate") or "agent_candidate"),
        "expression": expression,
        "family": str(args.get("family", "Agent") or "Agent"),
        "hypothesis": str(args.get("hypothesis", "Agent supplied expression") or "Agent supplied expression"),
        "official_metrics": dict(args.get("official_metrics") or {}),
        "submission": dict(args.get("submission") or {}),
    }


def expression_batch_argument(args: dict[str, Any]) -> list[str]:
    """Extract a deduplicated list of expressions from tool arguments."""
    raw = args.get("expressions")
    if raw is None:
        single = str(args.get("expression", "") or "").strip()
        return [single] if single else []
    values = raw if isinstance(raw, list) else [raw]
    expressions: list[str] = []
    seen: set[str] = set()
    for item in values:
        expression = str(item or "").strip()
        if not expression:
            continue
        marker = expression_key(expression)
        if marker in seen:
            continue
        seen.add(marker)
        expressions.append(expression)
    return expressions


def list_text(value: Any) -> list[str]:
    """Extract a deduplicated list of case-insensitive unique strings."""
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    rows: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        rows.append(text)
    return rows

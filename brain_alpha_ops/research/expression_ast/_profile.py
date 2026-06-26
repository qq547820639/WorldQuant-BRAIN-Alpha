"""Expression profile and high-level convenience accessors.

Re-exported via ``brain_alpha_ops.research.expression_ast``.
"""
from __future__ import annotations

from functools import lru_cache

from brain_alpha_ops.research.expression_ast._parser import (
    _collect,
    _collect_operators,
    _fields_from_text,
    _fingerprint,
    _max_depth,
    _node_count,
    _operators_from_text,
    _paren_depth_simple,
    _windows_from_text,
    canonicalize,
    lexical_normalize,
    parse_expression,
)
from brain_alpha_ops.research.expression_ast._types import (
    ExpressionParseError,
    ExpressionProfile,
)


@lru_cache(maxsize=1024)
def profile_expression(expression: str) -> ExpressionProfile:
    text = str(expression or "")
    try:
        root = parse_expression(text)
    except ExpressionParseError as exc:
        canonical = lexical_normalize(text)
        return ExpressionProfile(
            expression=text,
            parsed=False,
            canonical=canonical,
            fingerprint=_fingerprint(canonical),
            operators=tuple(_operators_from_text(canonical)),
            fields=tuple(_fields_from_text(canonical)),
            windows=tuple(_windows_from_text(canonical)),
            max_depth=_paren_depth_simple(text),
            node_count=max(0, len(canonical.split())),
            parse_error=str(exc),
        )

    canonical = canonicalize(root)
    operators: list[str] = []
    fields: list[str] = []
    windows: list[int] = []
    _collect(root, operators, fields, windows, 64)
    return ExpressionProfile(
        expression=text,
        parsed=True,
        canonical=canonical,
        fingerprint=_fingerprint(canonical),
        operators=tuple(dict.fromkeys(operators)),
        fields=tuple(dict.fromkeys(fields)),
        windows=tuple(windows),
        max_depth=_max_depth(root, 64),
        node_count=_node_count(root, 512),
    )


def expression_profile_summary(expression: str) -> dict:
    profile = profile_expression(expression)
    summary = {
        "expression_canonical": profile.canonical,
        "expression_fingerprint": profile.fingerprint,
        "expression_profile": {
            "schema_version": "expression-profile.v1",
            "parsed": profile.parsed,
            "operators": list(profile.operators),
            "fields": list(profile.fields),
            "windows": list(profile.windows),
            "max_depth": profile.max_depth,
            "node_count": profile.node_count,
        },
    }
    if profile.parse_error:
        summary["expression_profile"]["parse_error"] = profile.parse_error
    return summary


def canonical_expression(expression: str) -> str:
    return profile_expression(expression).canonical


def expression_key(expression: str) -> str:
    return canonical_expression(expression)


def expression_fingerprint(expression: str) -> str:
    return profile_expression(expression).fingerprint


def ordered_operators(expression: str) -> list[str]:
    try:
        root = parse_expression(expression)
    except ExpressionParseError:
        return _operators_from_text(lexical_normalize(expression))
    operators: list[str] = []
    _collect_operators(root, operators, 64)
    return operators

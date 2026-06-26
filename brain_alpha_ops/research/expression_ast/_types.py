"""Types and constants for the expression AST subpackage.

Re-exported via ``brain_alpha_ops.research.expression_ast``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_TOKEN_RE = re.compile(r"\s*(>=|<=|==|!=|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[(),+\-*/?:<>=])")
_LEXICAL_TOKEN_RE = re.compile(r">=|<=|==|!=|[a-zA-Z_][a-zA-Z0-9_]*|\d+(?:\.\d+)?|[-+*/(),?:<>=]")


class ExpressionParseError(ValueError):
    """Raised when a FASTEXPR string cannot be parsed by the local parser."""


@dataclass(frozen=True)
class ExprNode:
    kind: str
    value: str = ""
    children: tuple["ExprNode", ...] = ()


@dataclass(frozen=True)
class ExpressionProfile:
    expression: str
    parsed: bool
    canonical: str
    fingerprint: str
    operators: tuple[str, ...]
    fields: tuple[str, ...]
    windows: tuple[int, ...]
    max_depth: int
    node_count: int
    parse_error: str = ""

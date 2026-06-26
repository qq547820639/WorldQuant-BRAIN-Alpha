"""Expression shape normalization and field-function rewriting mixin.

Extracted from the original ``hypothesis_expression_support.py`` monolith
(deep-optimization-phase13). The methods here convert resolved semantic
shorthands into operator-based FASTEXPR and rewrite accidental
field-as-function calls into supported operators. They are mixed into
``HypothesisExpressionSupport`` in ``_support`` to keep the main class file
under the per-submodule line budget while preserving the public class API.
"""

from __future__ import annotations

import re
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    ExpressionParseError,
    ExprNode,
    canonicalize,
    parse_expression,
    profile_expression,
)
from brain_alpha_ops.research.fallback_generation import (
    DEFAULT_WINDOWS,
    normalize_operator_aliases,
)

from brain_alpha_ops.research.hypothesis_expression_support._operators import (
    KNOWN_BRAIN_OPERATORS,
    first_number_literal,
    format_window,
    is_group_key_node,
)


class _ExpressionNormalizationMixin:
    """Expression shape normalization and field-function rewriting."""

    def normalize_wq_expression_shape(self, expr: str, window: int | None = None) -> str:
        """Convert resolved semantic shorthands into operator-based FASTEXPR."""
        expr = normalize_operator_aliases(str(expr or "").strip())
        if not expr:
            return expr

        field_call = re.fullmatch(r"([A-Za-z_]\w*)\s*\(\s*(\d+(?:\.\d+)?)\s*\)", expr)
        if field_call:
            field_name = field_call.group(1)
            if field_name.lower() in {field.lower() for field in self._fields}:
                lookback = format_window(field_call.group(2) or window or DEFAULT_WINDOWS[0])
                if self.operator_available("rank") and self.operator_available("ts_delta"):
                    return f"rank(ts_delta({field_name}, {lookback}))"
                if self.operator_available("ts_delta"):
                    return f"ts_delta({field_name}, {lookback})"
                if self.operator_available("rank"):
                    return f"rank({field_name})"

        expr = self.normalize_field_function_calls(expr, window)
        profile = profile_expression(expr)
        if profile.parsed and profile.fields and not profile.operators and self.operator_available("rank"):
            return f"rank({expr})"
        return expr

    def operator_available(self, name: str) -> bool:
        return name.lower() in self._operators

    def normalize_field_function_calls(self, expr: str, window: int | None = None) -> str:
        """Rewrite accidental field-as-function calls into supported operators."""
        if not self._fields:
            return expr
        try:
            root = parse_expression(expr)
        except ExpressionParseError:
            return expr
        rewritten = self.rewrite_field_function_node(root, window)
        if rewritten == root:
            return expr
        return canonicalize(rewritten)

    def rewrite_field_function_node(self, node: ExprNode, window: int | None = None) -> ExprNode:
        if node.kind == "call":
            rewritten_children = tuple(
                self.rewrite_field_function_node(child, window) for child in node.children
            )
            if self.is_field_function_name(node.value):
                return self.replacement_for_field_function(node.value, rewritten_children, window)
            if rewritten_children != node.children:
                return ExprNode(node.kind, node.value, rewritten_children)
            return node
        if not node.children:
            return node
        rewritten_children = tuple(
            self.rewrite_field_function_node(child, window) for child in node.children
        )
        if rewritten_children == node.children:
            return node
        return ExprNode(node.kind, node.value, rewritten_children)

    def is_field_function_name(self, name: str) -> bool:
        value = str(name or "").lower()
        if value not in {field.lower() for field in self._fields}:
            return False
        operator_pool = self._operators or KNOWN_BRAIN_OPERATORS
        return value not in operator_pool

    def replacement_for_field_function(
        self,
        field_name: str,
        args: tuple[ExprNode, ...],
        window: int | None = None,
    ) -> ExprNode:
        field = ExprNode("identifier", field_name.lower())
        group_arg = next((arg for arg in args if is_group_key_node(arg)), None)
        if group_arg is not None and self.operator_available("group_rank"):
            return ExprNode("call", "group_rank", (field, group_arg))

        lookback = first_number_literal(args) or format_window(window or DEFAULT_WINDOWS[0])
        expression: ExprNode = field
        if self.operator_available("ts_delta"):
            expression = ExprNode("call", "ts_delta", (field, ExprNode("number", lookback)))
        if self.operator_available("rank"):
            expression = ExprNode("call", "rank", (expression,))
        return expression

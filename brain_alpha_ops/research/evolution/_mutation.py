"""Expression evolution engine — ``MutationEngine``.

Applies 8 directed mutation strategies to alpha expressions.  All mutations
preserve BRAIN FASTEXPR syntax validity.
"""
from __future__ import annotations

import logging
import random
import re
import sys

from brain_alpha_ops.research.evolution_helpers import (
    _BINARY_OPERATORS,
    _COMMON_FIELDS,
    _GROUP_OPERATORS,
    _MAX_MUTATION_ATTEMPTS,
    _MIN_EXPRESSION_LENGTH,
    _UNARY_OPERATORS,
    _WINDOW_OPERATORS,
    _WINDOW_RANGES,
    _expression_operators_are_official,
    _extract_inner,
    _is_valid_expression,
    _mutation_hash,
    _split_args,
    _split_top_level,
)
from brain_alpha_ops.research.generator_metadata import (
    expression_windows_within_constraints,
)
from brain_alpha_ops.research.evolution._types import MutationResult

logger = logging.getLogger(__name__)


def _pkg():
    """Access the package object so monkeypatch on package level takes effect.

    Tests like ``test_no_official_context_fails_closed`` monkeypatch
    ``brain_alpha_ops.research.evolution._official_operator_names`` and
    ``_official_field_ids``.  Looking these up through the package at call
    time (instead of binding them at import time) ensures the monkeypatch
    is observed.
    """
    return sys.modules["brain_alpha_ops.research.evolution"]


class MutationEngine:
    """Applies 8 directed mutation strategies to alpha expressions.

    All mutations preserve BRAIN FASTEXPR syntax validity.
    """

    STRATEGIES = [
        "add_operator",       # Wrap sub-expression with a unary operator
        "remove_operator",    # Remove outermost operator if safe
        "swap_operator",      # Replace operator with similar alternative
        "adjust_window",      # Change window parameter
        "add_field",          # Add a new field term (+ field)
        "remove_field",       # Remove a field term
        "swap_field",         # Replace one field with another
        "simplify",           # Remove the least impactful sub-expression
    ]

    def __init__(self, seed: int | None = None, *, known_fields: set[str] | None = None):
        self.rng = random.Random(seed)
        # Look up ``_official_operator_names`` / ``_official_field_ids`` through
        # the package so test monkeypatches on
        # ``brain_alpha_ops.research.evolution._official_operator_names`` are
        # observed (see ``test_no_official_context_fails_closed``).
        pkg = _pkg()
        self._official_operators = pkg._official_operator_names()
        self._unary_operators = _UNARY_OPERATORS & self._official_operators
        self._binary_operators = _BINARY_OPERATORS & self._official_operators
        self._group_operators = _GROUP_OPERATORS & self._official_operators
        self._mutable_operators = self._unary_operators | self._binary_operators | self._group_operators
        self._window_operators = _WINDOW_OPERATORS & self._official_operators

        base_fields = {str(field).lower() for field in (known_fields if known_fields is not None else _COMMON_FIELDS)}
        official_fields = pkg._official_field_ids()
        self._known_fields = base_fields & official_fields

    def mutate(
        self,
        expression: str,
        *,
        strategy: str | None = None,
        parent_score: float = 0.0,
        generation: int = 0,
    ) -> MutationResult:
        """Apply a single mutation strategy.

        Args:
            expression: source FASTEXPR expression
            strategy: optional override; picks randomly if None
            parent_score: score of parent for tracking
            generation: evolution generation number
        """
        if not isinstance(expression, str) or len(expression) < _MIN_EXPRESSION_LENGTH:
            return MutationResult(
                expression=expression,
                strategy="none",
                parent_score=parent_score,
                generation=generation,
                mutation_id=_mutation_hash(expression, "none"),
            )

        strategy = strategy or self.rng.choice(self.STRATEGIES)
        mutated = expression

        for _ in range(_MAX_MUTATION_ATTEMPTS):
            try:
                if strategy == "add_operator":
                    mutated = self._add_operator(expression)
                elif strategy == "remove_operator":
                    mutated = self._remove_operator(expression)
                elif strategy == "swap_operator":
                    mutated = self._swap_operator(expression)
                elif strategy == "adjust_window":
                    mutated = self._adjust_window(expression)
                elif strategy == "add_field":
                    mutated = self._add_field(expression)
                elif strategy == "remove_field":
                    mutated = self._remove_field(expression)
                elif strategy == "swap_field":
                    mutated = self._swap_field(expression)
                elif strategy == "simplify":
                    mutated = self._simplify(expression)

                if (
                    mutated != expression
                    and _is_valid_expression(mutated)
                    and _expression_operators_are_official(mutated, self._official_operators)
                    and expression_windows_within_constraints(mutated)
                ):
                    break
                mutated = expression
            except Exception as exc:
                mutated = expression

        return MutationResult(
            expression=mutated,
            strategy=strategy,
            parent_expression=expression,
            parent_score=parent_score,
            generation=generation,
            mutation_id=_mutation_hash(mutated, strategy),
        )

    def mutate_population(
        self,
        expressions: list[str],
        *,
        scores: dict[str, float] | None = None,
        generation: int = 0,
        mutations_per_expression: int = 2,
    ) -> list[MutationResult]:
        """Apply mutation to a population, biased toward high-scoring parents."""
        scores = scores or {}
        results: list[MutationResult] = []

        for expr in expressions:
            score = scores.get(expr, 0.0)
            strategies = self._select_strategies(score, count=mutations_per_expression)
            for strategy in strategies:
                result = self.mutate(expr, strategy=strategy, parent_score=score, generation=generation)
                if result.expression != expr:
                    results.append(result)

        return results

    # ── Strategy Implementations ──

    def _add_operator(self, expr: str) -> str:
        """Wrap expression with a unary operator."""
        if not self._unary_operators:
            return expr
        op = self.rng.choice(sorted(self._unary_operators))
        if op in self._window_operators:
            window = self.rng.choice([5, 10, 20, 30, 60, 90, 120, 252])
            return f"{op}({expr}, {window})"
        return f"{op}({expr})"

    def _remove_operator(self, expr: str) -> str:
        """Remove outermost operator if it's a unary wrapper."""
        depth = 0
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth == 0 and i + 1 < len(expr) and expr[i + 1] == "(":
                op_end = expr.index("(", i + 1)
                op_name = expr[i + 1:op_end].strip()
                if op_name in self._mutable_operators:
                    inner = expr[op_end + 1:expr.rfind(")")]
                    if inner.strip():
                        return inner
                break

        # Fallback: try to find any removable operator
        paren_count = expr.count("(")
        if paren_count >= 2 and expr.endswith(")"):
            return _extract_inner(expr)
        return expr

    def _swap_operator(self, expr: str) -> str:
        """Replace one operator with a similar alternative."""
        for op in sorted(self._mutable_operators, key=lambda x: -len(x)):
            idx = expr.find(op + "(")
            if idx >= 0:
                candidates = self._replacement_operator_pool(op)
                if not candidates:
                    return expr
                new_op = self.rng.choice(sorted(candidates))
                remaining = expr[idx + len(op) + 1:]
                inner, rest = _split_args(remaining)
                new_expr = expr[:idx] + self._render_call(new_op, inner) + rest
                if new_expr.count("(") == new_expr.count(")"):
                    return new_expr
        return expr

    def _replacement_operator_pool(self, op: str) -> set[str]:
        """Return same-shape official alternatives for *op*."""
        if op in self._unary_operators:
            return self._unary_operators - {op}
        if op in self._binary_operators:
            return self._binary_operators - {op}
        if op in self._group_operators:
            return self._group_operators - {op}
        return set()

    def _render_call(self, op: str, inner: str) -> str:
        """Render a call while replacing existing trailing window args safely."""
        if op not in self._window_operators:
            return f"{op}({inner})"
        parts = _split_top_level(inner, ",")
        args = list(parts)
        if args:
            try:
                int(args[-1].strip())
                args = args[:-1]
            except ValueError:
                pass
        window = self.rng.choice(_WINDOW_RANGES["medium"])
        args.append(str(window))
        return f"{op}({', '.join(arg.strip() for arg in args if arg.strip())})"

    def _adjust_window(self, expr: str) -> str:
        """Adjust window parameter on ts_* operators."""
        for op in sorted(self._window_operators, key=lambda x: -len(x)):
            idx = expr.find(f"{op}(")
            if idx >= 0:
                after_op = expr[idx + len(op) + 1:]
                inner, rest = _split_args(after_op)
                # Check if there's a window argument
                inner_parts = _split_top_level(inner, ",")
                if len(inner_parts) >= 2:
                    try:
                        current_window = int(inner_parts[-1].strip())
                    except ValueError:
                        continue
                    new_window = self.rng.choice([w for w in [5, 10, 20, 30, 60, 90, 120, 252] if w != current_window])
                    new_inner = ",".join(inner_parts[:-1]) + f", {new_window}"
                    return expr[:idx] + f"{op}({new_inner})" + rest
        return expr

    def _add_field(self, expr: str) -> str:
        """Add a field via the official add() operator."""
        if not self._known_fields or "add" not in self._binary_operators:
            return expr
        field = self.rng.choice(sorted(self._known_fields))
        return f"add({expr}, {field})"

    def _remove_field(self, expr: str) -> str:
        """Remove a simple field addition term."""
        if expr.startswith("add(") and expr.endswith(")"):
            parts = _split_top_level(_extract_inner(expr), ",")
            if len(parts) >= 2:
                return parts[0].strip()
        # Try pattern: (expr + field) → expr
        if expr.startswith("(") and " + " in expr:
            parts = _split_top_level(expr[1:-1], "+")
            if len(parts) >= 2:
                keep_parts = parts[:-1]  # remove last part
                if len(keep_parts) == 1:
                    return keep_parts[0].strip()
                return "(" + " + ".join(p.strip() for p in keep_parts) + ")"
        return expr

    def _swap_field(self, expr: str) -> str:
        """Replace one field reference with another."""
        if len(self._known_fields) < 2:
            return expr
        for field in sorted(self._known_fields, key=lambda x: -len(x)):
            pattern = r"\b" + re.escape(field) + r"\b"
            if re.search(pattern, expr):
                alternatives = sorted(self._known_fields - {field})
                if not alternatives:
                    return expr
                new_field = self.rng.choice(alternatives)
                return re.sub(pattern, new_field, expr, count=1)
        return expr

    def _simplify(self, expr: str) -> str:
        """Remove the least impactful sub-expression."""
        if expr.count("(") <= 1:
            # Already simple — try to keep inner only
            inner = _extract_inner(expr)
            if inner and len(inner) >= _MIN_EXPRESSION_LENGTH:
                return inner
            return expr
        # Try removing one level of nesting
        inner = _extract_inner(expr)
        if inner and _is_valid_expression(inner):
            return inner
        return expr

    def _select_strategies(self, score: float, count: int) -> list[str]:
        """Select mutation strategies biased by parent score.

        High score → prefer EXPLOIT (adjust_window, swap_field)
        Low score  → prefer EXPLORE (add_operator, add_field, swap_operator)
        """
        if score >= 80:
            weights = {"adjust_window": 4, "swap_field": 3, "simplify": 2, "swap_operator": 1}
        elif score >= 60:
            weights = {"adjust_window": 2, "swap_operator": 3, "swap_field": 2, "add_operator": 2, "simplify": 1}
        else:
            weights = {"add_operator": 4, "add_field": 3, "swap_operator": 2, "swap_field": 1}

        strategies = list(weights.keys())
        probs = [weights[s] / sum(weights.values()) for s in strategies]
        return self.rng.choices(strategies, weights=probs, k=min(count, len(strategies)))

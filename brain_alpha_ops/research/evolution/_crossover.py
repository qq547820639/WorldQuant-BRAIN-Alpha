"""Expression evolution engine — ``CrossoverEngine``.

Recombines high-scoring factor expressions via crossover.
"""
from __future__ import annotations

import logging
import random

from brain_alpha_ops.research.evolution_helpers import (
    _expression_operators_are_official,
    _is_valid_expression,
    _official_operator_names,
    _tokenize,
)
from brain_alpha_ops.research.evolution._types import CrossoverResult

logger = logging.getLogger(__name__)


class CrossoverEngine:
    """Recombines high-scoring factor expressions via crossover."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self._official_operators = _official_operator_names()

    def crossover(
        self,
        expr_a: str,
        expr_b: str,
        *,
        generation: int = 0,
    ) -> CrossoverResult | None:
        """Attempt crossover between two expressions.

        Tries to combine sub-expressions at compatible break points.
        Returns None if no valid crossover point found.
        """
        if not expr_a or not expr_b or expr_a == expr_b:
            return None

        # Find matching operator patterns
        tokens_a = _tokenize(expr_a)
        tokens_b = _tokenize(expr_b)

        if not tokens_a or not tokens_b:
            return None

        # Simple crossover: take first N tokens from A, rest from B.
        # This deliberately produces many syntactically invalid expressions by
        # cutting at arbitrary token boundaries. The high rejection rate is
        # acceptable because it maximises exploration diversity — each valid
        # offspring discovers novel sub-expression combinations that
        # structure-aware crossover would never generate.
        crossover_point = self.rng.randint(1, min(len(tokens_a), len(tokens_b)) - 1)

        combined = " ".join(tokens_a[:crossover_point] + tokens_b[crossover_point:])

        if (
            not _is_valid_expression(combined)
            or not _expression_operators_are_official(combined, self._official_operators)
            or combined in (expr_a, expr_b)
        ):
            return None

        return CrossoverResult(
            expression=combined,
            parent_a=expr_a,
            parent_b=expr_b,
            crossover_point=crossover_point,
            generation=generation,
        )

    def crossover_population(
        self,
        expressions: list[str],
        *,
        scores: dict[str, float] | None = None,
        generation: int = 0,
        pair_count: int = 5,
    ) -> list[CrossoverResult]:
        """Apply crossover to high-scoring pairs in the population."""
        scores = scores or {}
        # Sort by score descending
        ranked = sorted(expressions, key=lambda e: scores.get(e, 0.0), reverse=True)
        top_half = ranked[:max(2, len(ranked) // 2)]

        results: list[CrossoverResult] = []
        for _ in range(pair_count):
            if len(top_half) < 2:
                break
            a, b = self.rng.sample(top_half, 2)
            result = self.crossover(a, b, generation=generation)
            if result:
                results.append(result)
        return results

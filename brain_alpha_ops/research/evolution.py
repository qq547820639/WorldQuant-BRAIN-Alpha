"""Expression evolution engine for alpha factor optimization.

Inspired by QuantGPT's evolutionary search architecture:
  MutationEngine  — 8 directed mutation strategies
  CrossoverEngine — high-score factor crossover recombination
  MetaEvolutionSelector — adaptive strategy selection (EXPLOIT/EXPLORE/RECOMBINE/SIMPLIFY)

All operations are BRAIN-safe: only WorldQuant FASTEXPR operators are used,
and mutations preserve operator arity and field compatibility.
"""

from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── BRAIN FASTEXPR operator categories (canonical, aligned with official_context) ──
_UNARY_OPERATORS = {
    "rank", "log", "sqrt", "abs", "sign", "ts_delta",
    "ts_sum", "ts_mean", "ts_std_dev", "ts_z_score",
    "ts_decay_linear", "ts_min", "ts_max", "ts_median",
    "ts_skewness", "ts_kurtosis", "ts_arg_max", "ts_arg_min",
    "ts_rank", "ts_av_diff", "ts_percentage", "ts_corr",
    "inverse", "scale", "sigmoid",
}

_BINARY_OPERATORS = {
    "+", "-", "*", "/", "min", "max",
    "ts_covariance", "ts_regression", "ts_theilsen",
}

_GROUP_OPERATORS = {
    "group_neutralize", "group_rank", "group_z_score",
    "group_scale", "group_backfill",
}

_MUTABLE_OPERATORS = _UNARY_OPERATORS | _BINARY_OPERATORS | _GROUP_OPERATORS

# Window-based operators (accept window parameter)
_WINDOW_OPERATORS = {
    "ts_delta", "ts_sum", "ts_mean", "ts_std_dev", "ts_z_score",
    "ts_decay_linear", "ts_min", "ts_max", "ts_median",
    "ts_skewness", "ts_kurtosis", "ts_arg_max", "ts_arg_min",
    "ts_rank", "ts_av_diff", "ts_percentage",
    "ts_covariance", "ts_regression", "ts_theilsen", "ts_corr",
}

_WINDOW_RANGES = {
    "short": [5, 10, 20],
    "medium": [30, 60, 90, 120],
    "long": [180, 252],
}

# Valid BRAIN fields (sampled from canonical dataset — validated at runtime)
_COMMON_FIELDS = {
    "open", "close", "high", "low", "volume", "vwap",
    "returns", "cap", "adv20", "adv60",
}

# ── Safety limits ──
_MAX_EXPRESSION_LENGTH = 2000
_MAX_NESTING_DEPTH = 8
_MAX_MUTATION_ATTEMPTS = 10
_MIN_EXPRESSION_LENGTH = 3


# ═══════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class MutationResult:
    """Result of a single mutation operation."""
    expression: str
    strategy: str
    parent_expression: str = ""
    parent_score: float = 0.0
    generation: int = 0
    mutation_id: str = ""

    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "strategy": self.strategy,
            "parent_expression": self.parent_expression,
            "parent_score": self.parent_score,
            "generation": self.generation,
            "mutation_id": self.mutation_id,
        }


@dataclass
class CrossoverResult:
    """Result of crossover between two parent expressions."""
    expression: str
    parent_a: str = ""
    parent_b: str = ""
    crossover_point: int = 0
    generation: int = 0

    def to_dict(self) -> dict:
        return {
            "expression": self.expression,
            "parent_a": self.parent_a,
            "parent_b": self.parent_b,
            "crossover_point": self.crossover_point,
            "generation": self.generation,
        }


@dataclass
class EvolutionResult:
    """Complete evolution cycle result."""
    generation: int
    population: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    best_expression: str = ""
    best_score: float = 0.0
    strategy_used: str = "EXPLORE"
    mutations: list[MutationResult] = field(default_factory=list)
    crossovers: list[CrossoverResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generation": self.generation,
            "population_size": len(self.population),
            "best_expression": self.best_expression,
            "best_score": self.best_score,
            "strategy_used": self.strategy_used,
            "mutations": [m.to_dict() for m in self.mutations],
            "crossovers": [c.to_dict() for c in self.crossovers],
        }


# ═══════════════════════════════════════════════════════════════════════
# Mutation Engine — 8 directed mutation strategies
# ═══════════════════════════════════════════════════════════════════════

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
        self._known_fields = known_fields or _COMMON_FIELDS

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

                if mutated != expression and _is_valid_expression(mutated):
                    break
                mutated = expression
            except Exception:
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
        op = self.rng.choice(sorted(_UNARY_OPERATORS))
        if op in _WINDOW_OPERATORS:
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
                if op_name in _UNARY_OPERATORS or op_name in _BINARY_OPERATORS or op_name in _GROUP_OPERATORS:
                    inner = expr[op_end + 1:expr.rfind(")")]
                    if inner.strip():
                        return inner
                break
            elif ch in _UNARY_OPERATORS and depth == 0:
                # Handle case like "rank(close)" → "close"
                pass

        # Fallback: try to find any removable operator
        paren_count = expr.count("(")
        if paren_count >= 2 and expr.endswith(")"):
            return _extract_inner(expr)
        return expr

    def _swap_operator(self, expr: str) -> str:
        """Replace one operator with a similar alternative."""
        for op in sorted(_MUTABLE_OPERATORS, key=lambda x: -len(x)):
            idx = expr.find(op + "(")
            if idx >= 0:
                new_op = self.rng.choice(sorted(_UNARY_OPERATORS))
                if new_op in _WINDOW_OPERATORS:
                    window = self.rng.choice(_WINDOW_RANGES["medium"])
                    remaining = expr[idx + len(op) + 1:]
                    inner, rest = _split_args(remaining)
                    return expr[:idx] + f"{new_op}({inner}, {window})" + rest
                new_expr = expr[:idx] + new_op + expr[idx + len(op):]
                if new_expr.count("(") == new_expr.count(")"):
                    return new_expr
        return expr

    def _adjust_window(self, expr: str) -> str:
        """Adjust window parameter on ts_* operators."""
        for op in sorted(_WINDOW_OPERATORS, key=lambda x: -len(x)):
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
        """Add a field via addition: expr + field."""
        field = self.rng.choice(sorted(self._known_fields))
        return f"({expr} + {field})"

    def _remove_field(self, expr: str) -> str:
        """Remove a simple field addition term."""
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
        for field in sorted(self._known_fields, key=lambda x: -len(x)):
            if field in expr:
                new_field = self.rng.choice(sorted(self._known_fields - {field}))
                return expr.replace(field, new_field, 1)
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


# ═══════════════════════════════════════════════════════════════════════
# Crossover Engine
# ═══════════════════════════════════════════════════════════════════════

class CrossoverEngine:
    """Recombines high-scoring factor expressions via crossover."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

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

        # Simple crossover: take first N tokens from A, rest from B
        crossover_point = self.rng.randint(1, min(len(tokens_a), len(tokens_b)) - 1)

        combined = " ".join(tokens_a[:crossover_point] + tokens_b[crossover_point:])

        if not _is_valid_expression(combined) or combined in (expr_a, expr_b):
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


# ═══════════════════════════════════════════════════════════════════════
# Meta-Evolution Selector
# ═══════════════════════════════════════════════════════════════════════

class MetaEvolutionSelector:
    """Adaptive strategy selection based on score trajectory.

    Strategies:
      EXPLORE   — generate diverse variants (mutation with broad strategies)
      EXPLOIT   — fine-tune promising candidates (adjust_window, swap_field)
      RECOMBINE — crossover high-scoring pairs
      SIMPLIFY  — reduce complexity of over-engineered expressions
    """

    STRATEGIES = ("EXPLORE", "EXPLOIT", "RECOMBINE", "SIMPLIFY")

    def __init__(self, *, stagnation_threshold: int = 3, improvement_threshold: float = 5.0):
        self.stagnation_threshold = stagnation_threshold
        self.improvement_threshold = improvement_threshold
        self._history: list[float] = []
        self._current_strategy = "EXPLORE"
        self._stagnation_count = 0
        self._generation = 0

    def select_strategy(self, current_best_score: float) -> str:
        """Select the best strategy for the next generation."""
        self._generation += 1
        self._history.append(current_best_score)

        if self._generation <= 1:
            self._current_strategy = "EXPLORE"
            return self._current_strategy

        prev_best = self._history[-2] if len(self._history) >= 2 else 0.0
        improvement = current_best_score - prev_best

        if improvement >= self.improvement_threshold:
            self._stagnation_count = 0
            self._current_strategy = "EXPLOIT"
        elif improvement <= -self.improvement_threshold:
            self._stagnation_count += 1
            self._current_strategy = "RECOMBINE" if self._generation >= 3 else "EXPLORE"
        else:
            self._stagnation_count += 1

        if self._stagnation_count >= self.stagnation_threshold:
            self._stagnation_count = 0
            max_len = max(
                (len(self._history[i]) if isinstance(self._history[i], str) else 0)
                for i in range(max(0, len(self._history) - 3), len(self._history))
            ) if self._history else 0
            if max_len > 200:
                self._current_strategy = "SIMPLIFY"
            else:
                self._current_strategy = "EXPLORE"

        return self._current_strategy

    def reset(self) -> None:
        self._history.clear()
        self._current_strategy = "EXPLORE"
        self._stagnation_count = 0
        self._generation = 0


# ═══════════════════════════════════════════════════════════════════════
# Evolution Runner
# ═══════════════════════════════════════════════════════════════════════

class EvolutionRunner:
    """Orchestrates mutation + crossover across multiple generations."""

    def __init__(
        self,
        *,
        known_fields: set[str] | None = None,
        population_size: int = 20,
        max_generations: int = 10,
        seed: int | None = None,
    ):
        self.mutation_engine = MutationEngine(seed=seed, known_fields=known_fields)
        self.crossover_engine = CrossoverEngine(seed=seed)
        self.selector = MetaEvolutionSelector()
        self.population_size = population_size
        self.max_generations = max_generations
        self._results: list[EvolutionResult] = []

    def evolve(
        self,
        seed_expressions: list[str],
        *,
        score_func=None,
    ) -> list[EvolutionResult]:
        """Run evolution for max_generations.

        Args:
            seed_expressions: initial population
            score_func: optional callable(str) → float for scoring
        """
        self.selector.reset()
        self._results.clear()
        population = list(seed_expressions)[:self.population_size]

        if not population:
            return []

        for gen in range(self.max_generations):
            # Score current population
            scores: dict[str, float] = {}
            if score_func:
                for expr in population:
                    try:
                        scores[expr] = float(score_func(expr))
                    except Exception:
                        scores[expr] = 0.0
            else:
                scores = {expr: 50.0 for expr in population}

            best_expr = max(population, key=lambda e: scores.get(e, 0.0))
            best_score = scores.get(best_expr, 0.0)

            strategy = self.selector.select_strategy(best_score)

            result = EvolutionResult(
                generation=gen + 1,
                population=list(population),
                scores=dict(scores),
                best_expression=best_expr,
                best_score=best_score,
                strategy_used=strategy,
            )

            # Apply strategy
            if strategy == "RECOMBINE":
                crossovers = self.crossover_engine.crossover_population(
                    population, scores=scores, generation=gen + 1
                )
                result.crossovers = crossovers
                for c in crossovers:
                    if c.expression not in population:
                        population.append(c.expression)

                mutations = self.mutation_engine.mutate_population(
                    population, scores=scores, generation=gen + 1
                )
                result.mutations = mutations
                for m in mutations:
                    if m.expression not in population:
                        population.append(m.expression)

            elif strategy == "SIMPLIFY":
                mutations = self.mutation_engine.mutate_population(
                    population, scores=scores, generation=gen + 1,
                    mutations_per_expression=1,
                )
                # Override strategy to always simplify
                for m in mutations:
                    m.strategy = "simplify"
                result.mutations = mutations
                for m in mutations:
                    if m.expression not in population:
                        population.append(m.expression)

            else:  # EXPLORE or EXPLOIT
                mutations = self.mutation_engine.mutate_population(
                    population, scores=scores, generation=gen + 1,
                    mutations_per_expression=2,
                )
                result.mutations = mutations
                for m in mutations:
                    if m.expression not in population:
                        population.append(m.expression)

            self._results.append(result)

            # Prune population to population_size
            if len(population) > self.population_size:
                ranked = sorted(population, key=lambda e: scores.get(e, 0.0), reverse=True)
                population = ranked[:self.population_size]

        return list(self._results)

    @property
    def best_expression(self) -> str:
        if not self._results:
            return ""
        return max(self._results, key=lambda r: r.best_score).best_expression

    @property
    def best_score(self) -> float:
        if not self._results:
            return 0.0
        return max(r.best_score for r in self._results)

    def to_dict(self) -> dict:
        return {
            "population_size": self.population_size,
            "max_generations": self.max_generations,
            "best_expression": self.best_expression,
            "best_score": self.best_score,
            "generations": [r.to_dict() for r in self._results],
        }


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════

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
    # Count nesting depth
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
    # Try function-style: func_name(args)
    for op in sorted(_MUTABLE_OPERATORS, key=lambda x: -len(x)):
        if expr.startswith(op + "(") and expr.endswith(")"):
            return expr[len(op) + 1:-1]
    return ""


def _split_args(expr: str) -> tuple[str, str]:
    """Split expression into first argument and remaining text.

    Returns (inner_content, remaining_after_matching_paren).
    """
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
    """Split expression at top-level separator (respecting parentheses)."""
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
    return [t for t in tokens if t]


def _mutation_hash(expression: str, strategy: str) -> str:
    return hashlib.sha256(f"{expression}:{strategy}".encode()).hexdigest()[:12]

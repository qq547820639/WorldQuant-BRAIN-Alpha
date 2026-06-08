"""Expression evolution engine for alpha factor optimization.

Inspired by QuantGPT's evolutionary search architecture:
  MutationEngine  — 8 directed mutation strategies
  CrossoverEngine — high-score factor crossover recombination
  MetaEvolutionSelector — adaptive strategy selection (EXPLOIT/EXPLORE/RECOMBINE/SIMPLIFY)

All operations are BRAIN-safe: only WorldQuant FASTEXPR operators are used,
and mutations preserve operator arity and field compatibility.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from brain_alpha_ops.research.evolution_helpers import (
    _BINARY_OPERATORS,
    _COMMON_FIELDS,
    _GROUP_OPERATORS,
    _MAX_EXPRESSION_LENGTH,
    _MAX_MUTATION_ATTEMPTS,
    _MAX_NESTING_DEPTH,
    _MIN_EXPRESSION_LENGTH,
    _MUTABLE_OPERATORS,
    _UNARY_OPERATORS,
    _WINDOW_OPERATORS,
    _WINDOW_RANGES,
    _expression_operators_are_official,
    _extract_inner,
    _is_valid_expression,
    _mutation_hash,
    _official_field_ids,
    _official_operator_names,
    _split_args,
    _split_top_level,
    _tokenize,
)


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
        self._official_operators = _official_operator_names()
        self._unary_operators = _UNARY_OPERATORS & self._official_operators
        self._binary_operators = _BINARY_OPERATORS & self._official_operators
        self._group_operators = _GROUP_OPERATORS & self._official_operators
        self._mutable_operators = self._unary_operators | self._binary_operators | self._group_operators
        self._window_operators = _WINDOW_OPERATORS & self._official_operators

        base_fields = {str(field).lower() for field in (known_fields if known_fields is not None else _COMMON_FIELDS)}
        official_fields = _official_field_ids()
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
                ):
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


# ═══════════════════════════════════════════════════════════════════════
# Crossover Engine
# ═══════════════════════════════════════════════════════════════════════

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

        # Simple crossover: take first N tokens from A, rest from B
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
        self._expr_len_history: list[int] = []  # 跟踪最近几代表达式长度
        self._current_strategy = "EXPLORE"
        self._stagnation_count = 0
        self._generation = 0

    def select_strategy(self, current_best_score: float, *,
                        best_expression_len: int = 0) -> str:
        """Select the best strategy for the next generation.

        Args:
            current_best_score: 当前最优分数
            best_expression_len: 当前最优表达式的字符长度（用于 SIMPLIFY 判断）
        """
        self._generation += 1
        self._history.append(current_best_score)
        self._expr_len_history.append(best_expression_len)

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
            # 检查最近 3 代表达式最大长度，过长则触发 SIMPLIFY
            lookback = min(3, len(self._expr_len_history))
            max_len = max(self._expr_len_history[-lookback:]) if lookback > 0 else 0
            if max_len > 200:
                self._current_strategy = "SIMPLIFY"
            else:
                self._current_strategy = "EXPLORE"

        return self._current_strategy

    def reset(self) -> None:
        self._history.clear()
        self._expr_len_history.clear()
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

            strategy = self.selector.select_strategy(
                best_score, best_expression_len=len(best_expr),
            )

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

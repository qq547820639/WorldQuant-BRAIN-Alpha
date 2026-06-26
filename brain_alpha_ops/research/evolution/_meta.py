"""Expression evolution engine — ``MetaEvolutionSelector`` and ``EvolutionRunner``.

``MetaEvolutionSelector`` provides adaptive strategy selection based on score
trajectory. ``EvolutionRunner`` orchestrates mutation + crossover across
multiple generations.
"""
from __future__ import annotations

import logging

from brain_alpha_ops.research.evolution._crossover import CrossoverEngine
from brain_alpha_ops.research.evolution._mutation import MutationEngine
from brain_alpha_ops.research.evolution._types import EvolutionResult

logger = logging.getLogger(__name__)


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
                    except Exception as exc:
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

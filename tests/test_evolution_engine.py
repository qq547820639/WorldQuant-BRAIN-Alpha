"""Tests for expression evolution engine.

Covers: MutationEngine (8 strategies), CrossoverEngine, MetaEvolutionSelector,
EvolutionRunner, boundary conditions (empty, invalid, extreme, deterministic).
"""

from __future__ import annotations

import pytest

import brain_alpha_ops.research.evolution as evolution_module
from brain_alpha_ops.research.evolution import (
    MutationEngine,
    MutationResult,
    CrossoverEngine,
    CrossoverResult,
    MetaEvolutionSelector,
    EvolutionRunner,
    EvolutionResult,
    _is_valid_expression,
    _extract_inner,
    _split_top_level,
    _tokenize,
    _COMMON_FIELDS,
    _MUTABLE_OPERATORS,
    _MAX_EXPRESSION_LENGTH,
    _MAX_NESTING_DEPTH,
)


# ═══════════════════════ Validity Tests ═══════════════════════════

class TestIsValidExpression:
    def test_valid_simple(self):
        assert _is_valid_expression("close") is True
        assert _is_valid_expression("rank(close)") is True
        assert _is_valid_expression("ts_mean(close, 20)") is True

    def test_invalid_unbalanced(self):
        assert _is_valid_expression("rank(close") is False
        assert _is_valid_expression("rank(close))") is False

    def test_invalid_empty_parens(self):
        assert _is_valid_expression("rank()") is False

    def test_invalid_too_long(self):
        long_expr = "close" * (_MAX_EXPRESSION_LENGTH + 1)
        assert _is_valid_expression(long_expr) is False

    def test_invalid_too_short(self):
        assert _is_valid_expression("ab") is False
        assert _is_valid_expression("") is False

    def test_invalid_deep_nesting(self):
        nested = "rank(" * (_MAX_NESTING_DEPTH + 1) + "close" + ")" * (_MAX_NESTING_DEPTH + 1)
        assert _is_valid_expression(nested) is False

    def test_valid_nested(self):
        expr = "rank(ts_mean(close, 20))"
        assert _is_valid_expression(expr) is True


class TestExtractInner:
    def test_simple_parens(self):
        assert _extract_inner("(close + volume)") == "close + volume"

    def test_function_style(self):
        assert _extract_inner("rank(close)") == "close"

    def test_no_parens(self):
        assert _extract_inner("close") == ""


class TestSplitTopLevel:
    def test_simple_split(self):
        result = _split_top_level("a + b + c", "+")
        assert len(result) == 3
        assert "c" in result

    def test_nested_parens(self):
        result = _split_top_level("rank(close) + volume", "+")
        assert len(result) == 2
        assert "rank(close)" in result

    def test_no_separator(self):
        result = _split_top_level("close", "+")
        assert result == ["close"]


# ═══════════════════════ Mutation Engine Tests ═══════════════════════

class TestMutationEngine:
    def setup_method(self):
        self.engine = MutationEngine(seed=42)

    def test_strategies_list(self):
        assert len(MutationEngine.STRATEGIES) == 8
        assert "add_operator" in MutationEngine.STRATEGIES
        assert "simplify" in MutationEngine.STRATEGIES

    def test_mutate_returns_result(self):
        result = self.engine.mutate("rank(close)")
        assert isinstance(result, MutationResult)
        assert len(result.expression) > 0
        assert result.strategy in MutationEngine.STRATEGIES

    def test_mutate_produces_different(self):
        """Mutation should produce different expression."""
        original = "rank(close)"
        results = set()
        for _ in range(10):
            r = self.engine.mutate(original)
            results.add(r.expression)
        # At least some mutations should differ
        assert len(results) >= 2 or original not in results, f"All mutations returned same: {results}"

    def test_mutate_empty_expression(self):
        result = self.engine.mutate("")
        assert result.strategy == "none"

    def test_mutate_short_expression(self):
        result = self.engine.mutate("ab")
        assert result.strategy == "none"

    def test_mutate_valid_result(self):
        """All mutation results should pass basic validity."""
        for _ in range(20):
            result = self.engine.mutate("rank(close)")
            if result.expression != "rank(close)":
                assert _is_valid_expression(result.expression), f"Invalid: {result.expression}"

    def test_mutate_with_specific_strategy(self):
        result = self.engine.mutate("rank(close)", strategy="add_operator")
        assert result.strategy == "add_operator"

    def test_mutate_population(self):
        population = ["rank(close)", "ts_mean(volume, 20)", "close + open"]
        results = self.engine.mutate_population(
            population,
            scores={"rank(close)": 80.0, "ts_mean(volume, 20)": 60.0, "close + open": 40.0},
            generation=1,
        )
        assert len(results) > 0
        for r in results:
            assert isinstance(r, MutationResult)
            assert r.generation == 1

    def test_add_operator(self):
        result = self.engine._add_operator("close")
        assert "(" in result
        assert "close" in result

    def test_swap_operator(self):
        result = self.engine._swap_operator("rank(close)")
        # Should replace rank with another operator
        assert "(" in result

    def test_adjust_window(self):
        expr = "ts_mean(close, 20)"
        result = self.engine._adjust_window(expr)
        if result != expr:
            assert "ts_mean" in result

    def test_add_field(self):
        result = self.engine._add_field("close")
        assert result == "close" or result.startswith("add(")

    def test_swap_field(self):
        result = self.engine._swap_field("close + volume")
        if result != "close + volume":
            assert len(result) > 0

    def test_simplify(self):
        result = self.engine._simplify("rank(close)")
        # Should extract inner
        assert result == "close" or result == "rank(close)"

    def test_deterministic_with_seed(self):
        engine1 = MutationEngine(seed=123)
        engine2 = MutationEngine(seed=123)
        r1 = engine1.mutate("rank(close)", strategy="add_operator")
        r2 = engine2.mutate("rank(close)", strategy="add_operator")
        assert r1.expression == r2.expression

    def test_custom_fields_are_not_used_for_production_mutation(self):
        engine = MutationEngine(seed=1, known_fields={"custom_f1", "custom_f2"})
        result = engine._swap_field("custom_f1")
        assert result == "custom_f1"
        assert engine._add_field("rank(close)") == "rank(close)"

    def test_no_official_context_fails_closed(self, monkeypatch):
        monkeypatch.setattr(evolution_module, "_official_field_ids", lambda: set())
        monkeypatch.setattr(evolution_module, "_official_operator_names", lambda: set())

        engine = MutationEngine(seed=1, known_fields={"custom_f1", "custom_f2"})

        assert engine._add_field("close") == "close"
        assert engine._add_operator("close") == "close"
        assert engine.mutate("rank(close)", strategy="add_operator").expression == "rank(close)"

    def test_mutable_operators_are_current_official_names(self):
        forbidden = {
            "ts_z_score",
            "group_z_score",
            "ts_median",
            "ts_percentage",
            "ts_theilsen",
            "sigmoid",
        }

        assert forbidden.isdisjoint(_MUTABLE_OPERATORS)
        assert "ts_zscore" in _MUTABLE_OPERATORS
        assert "group_zscore" in _MUTABLE_OPERATORS
        assert "adv60" not in _COMMON_FIELDS


# ═══════════════════════ Crossover Engine Tests ═══════════════════════

class TestCrossoverEngine:
    def setup_method(self):
        self.engine = CrossoverEngine(seed=42)

    def test_crossover_different(self):
        result = self.engine.crossover("rank(close)", "ts_mean(volume, 20)")
        if result is not None:
            assert isinstance(result, CrossoverResult)
            assert len(result.expression) > 0
            assert result.parent_a == "rank(close)"
            assert result.parent_b == "ts_mean(volume, 20)"

    def test_crossover_identical(self):
        result = self.engine.crossover("rank(close)", "rank(close)")
        assert result is None

    def test_crossover_empty(self):
        result = self.engine.crossover("", "close")
        assert result is None

    def test_crossover_population(self):
        population = [
            "rank(close)",
            "ts_mean(volume, 20)",
            "log(high)",
            "close + open",
            "sqrt(low)",
        ]
        scores = {expr: float(100 - i * 10) for i, expr in enumerate(population)}
        results = self.engine.crossover_population(population, scores=scores, generation=1)
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, CrossoverResult)
            assert r.generation == 1

    def test_deterministic_with_seed(self):
        e1 = CrossoverEngine(seed=99)
        e2 = CrossoverEngine(seed=99)
        r1 = e1.crossover("rank(close)", "ts_mean(volume, 20)")
        r2 = e2.crossover("rank(close)", "ts_mean(volume, 20)")
        assert (r1 is None) == (r2 is None)
        if r1 and r2:
            assert r1.expression == r2.expression


# ═══════════════════════ Meta Evolution Selector Tests ═══════════════

class TestMetaEvolutionSelector:
    def setup_method(self):
        self.selector = MetaEvolutionSelector()

    def test_initial_strategy_explore(self):
        assert self.selector.select_strategy(50.0) == "EXPLORE"

    def test_improvement_triggers_exploit(self):
        self.selector.select_strategy(50.0)  # gen 1
        result = self.selector.select_strategy(60.0)  # gen 2, improvement=10
        assert result == "EXPLOIT"

    def test_decline_triggers_explore(self):
        self.selector.select_strategy(60.0)  # gen 1
        result = self.selector.select_strategy(50.0)  # gen 2, decline
        assert result == "EXPLORE"

    def test_stagnation_triggers_explore(self):
        for i in range(5):
            self.selector.select_strategy(50.0)
        # After 3+ stag, should switch
        assert self.selector._current_strategy in ("EXPLORE", "RECOMBINE", "SIMPLIFY")

    def test_reset(self):
        self.selector.select_strategy(50.0)
        self.selector.select_strategy(60.0)
        self.selector.reset()
        assert self.selector.select_strategy(55.0) == "EXPLORE"

    def test_strategies_list(self):
        assert "EXPLORE" in MetaEvolutionSelector.STRATEGIES
        assert "EXPLOIT" in MetaEvolutionSelector.STRATEGIES
        assert "RECOMBINE" in MetaEvolutionSelector.STRATEGIES
        assert "SIMPLIFY" in MetaEvolutionSelector.STRATEGIES


# ═══════════════════════ Evolution Runner Tests ═══════════════════════

class TestEvolutionRunner:
    def setup_method(self):
        self.runner = EvolutionRunner(
            population_size=10,
            max_generations=5,
            seed=42,
        )

    def test_evolve_basic(self):
        seeds = ["rank(close)", "ts_mean(volume, 20)", "close + open"]
        results = self.runner.evolve(seeds)
        assert len(results) > 0
        assert len(results) <= 5  # max_generations
        for r in results:
            assert isinstance(r, EvolutionResult)
            assert r.generation >= 1
            assert r.population
            assert r.best_expression

    def test_evolve_with_score_func(self):
        def score_func(expr: str) -> float:
            if "rank" in expr:
                return 80.0
            if "ts_mean" in expr:
                return 70.0
            return 50.0

        seeds = ["rank(close)", "ts_mean(volume, 20)", "close + open"]
        results = self.runner.evolve(seeds, score_func=score_func)
        assert len(results) > 0
        # Best should have high score
        assert self.runner.best_score >= 80.0

    def test_best_expression(self):
        seeds = ["rank(close)"]
        self.runner.evolve(seeds)
        assert len(self.runner.best_expression) > 0

    def test_to_dict(self):
        seeds = ["rank(close)", "ts_mean(volume, 20)"]
        self.runner.evolve(seeds)
        d = self.runner.to_dict()
        assert "best_expression" in d
        assert "generations" in d
        assert len(d["generations"]) > 0

    def test_empty_seeds(self):
        results = self.runner.evolve([])
        assert results == []

    def test_deterministic(self):
        seeds = ["rank(close)", "ts_mean(volume, 20)", "close + open"]
        r1 = EvolutionRunner(population_size=10, max_generations=3, seed=123)
        r2 = EvolutionRunner(population_size=10, max_generations=3, seed=123)
        results1 = r1.evolve(seeds)
        results2 = r2.evolve(seeds)
        assert len(results1) == len(results2)
        for gen1, gen2 in zip(results1, results2):
            assert gen1.best_score == gen2.best_score, f"Gen {gen1.generation}: {gen1.best_score} != {gen2.best_score}"


# ═══════════════════════ Boundary Tests ═══════════════════════════

class TestBoundaryConditions:
    def test_very_long_expression(self):
        expr = " + ".join(["close"] * 100)
        engine = MutationEngine(seed=1)
        result = engine.mutate(expr)
        assert isinstance(result, MutationResult)

    def test_unicode_expression(self):
        # Non-ASCII should not crash
        engine = MutationEngine(seed=1)
        result = engine.mutate("rank(clöse)")
        assert isinstance(result, MutationResult)

    def test_special_chars(self):
        engine = MutationEngine(seed=1)
        result = engine.mutate("close /* comment */")
        assert isinstance(result, MutationResult)

    def test_mutation_id_unique(self):
        engine = MutationEngine(seed=1)
        ids = set()
        for _ in range(50):
            r = engine.mutate("rank(close)")
            ids.add(r.mutation_id)
        # Most should be unique
        assert len(ids) >= 10

    def test_result_to_dict(self):
        mr = MutationResult("rank(close)", "add_operator", "close", 80.0, 1, "abc123")
        d = mr.to_dict()
        assert d["expression"] == "rank(close)"
        assert d["strategy"] == "add_operator"

        cr = CrossoverResult("close + volume", "close", "volume", 5, 1)
        d2 = cr.to_dict()
        assert d2["expression"] == "close + volume"

        er = EvolutionResult(1, ["close"], {"close": 80.0}, "close", 80.0)
        d3 = er.to_dict()
        assert d3["best_score"] == 80.0

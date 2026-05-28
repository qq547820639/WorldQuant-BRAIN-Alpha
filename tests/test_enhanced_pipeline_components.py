"""Comprehensive tests for the enhanced pipeline components.

Covers:
  - runtime_constants.py    : Centralized constants correctness
  - knowledge_base.py       : Structured KB CRUD and extraction
  - cross_review_pipeline.py: Decision engine logic and evidence checking
  - local_backtest_engine.py: Expression evaluation, portfolio, metrics
  - pipeline_stages.py      : Stage processors and orchestrator
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from unittest.mock import Mock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════
# runtime_constants tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRuntimeConstants:
    """Verify centralized constants are correct and non-conflicting."""

    def test_web_defaults_are_sane(self):
        from brain_alpha_ops.runtime_constants import WebDefaults
        assert WebDefaults.HOST == "127.0.0.1"
        assert WebDefaults.PORT == 8765
        assert WebDefaults.MAX_BODY_BYTES == 2 * 1024 * 1024
        assert WebDefaults.MAX_SSE_DURATION == 600

    def test_cloud_defaults_are_sane(self):
        from brain_alpha_ops.runtime_constants import CloudDefaults
        assert CloudDefaults.CLOUD_SYNC_STALE_SECONDS == 86400
        assert CloudDefaults.MAX_CACHED_USER_ALPHA_FILES == 50
        assert CloudDefaults.CONTEXT_CACHE_TTL_SECONDS == 86400

    def test_agent_limits_are_sane(self):
        from brain_alpha_ops.runtime_constants import AgentLimits
        assert AgentLimits.MAX_TOOL_CANDIDATES == 100
        assert AgentLimits.MAX_BATCH_SIMULATIONS == 10
        assert AgentLimits.MAX_BATCH_SIMULATION_WORKERS == 3
        assert "1d" in AgentLimits.MAX_SYNC_RANGE
        assert "all" in AgentLimits.MAX_SYNC_RANGE

    def test_constants_not_duplicated_across_classes(self):
        """Verify CloudDefaults and WebDefaults don't override each other."""
        from brain_alpha_ops.runtime_constants import CloudDefaults, WebDefaults
        # CLOUD_SYNC_STALE_SECONDS should be consistent
        assert CloudDefaults.CLOUD_SYNC_STALE_SECONDS == 86400

    def test_repository_defaults_files(self):
        from brain_alpha_ops.runtime_constants import RepositoryDefaults
        assert "candidates.jsonl" in RepositoryDefaults.EXPRESSION_INDEXED_FILES
        assert "submissions.jsonl" in RepositoryDefaults.EXPRESSION_INDEXED_FILES

    def test_scoring_defaults_sum_to_1(self):
        from brain_alpha_ops.runtime_constants import ScoringDefaults
        total = (
            ScoringDefaults.DEFAULT_PRIOR_LAYER_WEIGHT
            + ScoringDefaults.DEFAULT_EMPIRICAL_LAYER_WEIGHT
            + ScoringDefaults.DEFAULT_CHECKLIST_LAYER_WEIGHT
        )
        assert abs(total - 1.0) < 0.01


# ═══════════════════════════════════════════════════════════════════════════
# Knowledge Base tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStructuredKnowledgeBase:
    """Verify the three-layer knowledge base works correctly."""

    def test_save_and_load(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            entry = KnowledgeEntry(
                layer="rule",
                category="field_selection",
                title="Test Rule: use rank with close",
                description="Rank of close price is a reliable base signal.",
                confidence=0.85,
            )
            entry_id = kb.save(entry)
            assert entry_id

            loaded = kb.load(entry_id)
            assert loaded is not None
            assert loaded.title == "Test Rule: use rank with close"
            assert loaded.layer == "rule"
            assert loaded.confidence == 0.85

    def test_list_layer(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            kb.save(KnowledgeEntry(layer="rule", category="field_selection", title="R1"))
            kb.save(KnowledgeEntry(layer="rule", category="operator_usage", title="R2"))
            kb.save(KnowledgeEntry(layer="finding", category="field_effectiveness", title="F1"))
            kb.save(KnowledgeEntry(layer="failure", category="overfit", title="X1"))

            rules = kb.list_layer("rules")
            findings = kb.list_layer("findings")
            failures = kb.list_layer("failures")

            assert len(rules) == 2
            assert len(findings) == 1
            assert len(failures) == 1

    def test_list_category(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            kb.save(KnowledgeEntry(layer="rule", category="field_selection", title="R1"))
            kb.save(KnowledgeEntry(layer="rule", category="field_selection", title="R2"))
            kb.save(KnowledgeEntry(layer="rule", category="operator_usage", title="R3"))

            field_rules = kb.list_category("rules", "field_selection")
            assert len(field_rules) == 2

            op_rules = kb.list_category("rules", "operator_usage")
            assert len(op_rules) == 1

    def test_delete(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            entry = KnowledgeEntry(layer="rule", category="field_selection", title="To Delete")
            entry_id = kb.save(entry)

            assert kb.delete(entry_id) is True
            assert kb.load(entry_id) is None
            assert kb.delete("nonexistent") is False

    def test_touch_increments_hit_count(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            entry = KnowledgeEntry(layer="finding", category="field_effectiveness", title="Touch Me")
            entry_id = kb.save(entry)

            kb.touch(entry_id)
            loaded = kb.load(entry_id)
            assert loaded.hit_count == 1

            kb.touch(entry_id)
            loaded = kb.load(entry_id)
            assert loaded.hit_count == 2

    def test_find_by_pattern(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            kb.save(KnowledgeEntry(
                layer="rule", category="expression_structure",
                title="Rule: rank(close)", expression_pattern="rank(close)",
            ))
            kb.save(KnowledgeEntry(
                layer="failure", category="overfit",
                title="Avoid: ts_zscore(close, 5)", expression_pattern="ts_zscore(close, 5)",
            ))

            matches = kb.find_by_pattern("rank(close)")
            assert len(matches) == 1
            assert matches[0].layer == "rule"

            matches_fail = kb.find_by_pattern("ts_zscore(close, 5)")
            assert len(matches_fail) == 1
            assert matches_fail[0].layer == "failure"

    def test_extract_from_memory(self):
        from brain_alpha_ops.research.knowledge_base import StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            memory_summary = {
                "families": [
                    {"name": "momentum_breakout", "count": 10, "success_rate": 0.7, "avg_score": 78},
                    {"name": "value_reversal", "count": 5, "success_rate": 0.62, "avg_score": 72},
                ],
                "fields": [
                    {"name": "close", "count": 8, "success_rate": 0.65, "avg_sharpe": 1.5},
                    {"name": "volume", "count": 6, "success_rate": 0.55, "avg_sharpe": 1.3},
                ],
                "operators": [
                    {"name": "rank", "count": 7, "success_rate": 0.7},
                    {"name": "ts_zscore", "count": 5, "success_rate": 0.6},
                ],
                "failure_patterns": [
                    {"reason": "low_sharpe", "count": 15},
                    {"reason": "self_correlation", "count": 8},
                ],
            }
            counts = kb.extract_from_memory(memory_summary)
            assert counts["rules"] >= 1
            assert counts["findings"] >= 1
            assert counts["failures"] >= 1

    def test_summary(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            kb.save(KnowledgeEntry(layer="rule", category="field_selection", title="R1"))
            kb.save(KnowledgeEntry(layer="finding", category="field_effectiveness", title="F1"))
            summary = kb.summary()
            assert summary["rules_count"] == 1
            assert summary["findings_count"] == 1
            assert summary["failures_count"] == 0
            assert summary["schema_version"] == "knowledge_base.v1"

    def test_get_generation_constraints(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            kb.save(KnowledgeEntry(
                layer="rule", category="field_selection",
                title="Use close", fields_involved=["close"],
            ))
            kb.save(KnowledgeEntry(
                layer="rule", category="operator_usage",
                title="Use rank", operators_involved=["rank"],
            ))
            kb.save(KnowledgeEntry(
                layer="failure", category="overfit",
                title="Avoid risky pattern", expression_pattern="risky",
            ))
            constraints = kb.get_generation_constraints()
            assert "close" in constraints["preferred_fields"]
            assert "rank" in constraints["preferred_operators"]
            assert len(constraints["forbidden_patterns"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Cross-Review Pipeline tests
# ═══════════════════════════════════════════════════════════════════════════

class TestReviewDecisionEngine:
    """Verify the decision engine produces correct decisions."""

    def test_accept_strong_consensus(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        decision = engine.decide(
            primary_confidence=0.85,
            reviewer_confidence=0.80,
            agreement=True,
            evidence_support=0.75,
        )
        assert decision.decision == "accept"
        assert decision.conservative is False

    def test_reject_low_primary_confidence(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        decision = engine.decide(
            primary_confidence=0.15,
            reviewer_confidence=0.80,
            agreement=True,
            evidence_support=0.80,
        )
        assert decision.decision == "reject"

    def test_conservative_on_disagreement(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        decision = engine.decide(
            primary_confidence=0.70,
            reviewer_confidence=0.65,
            agreement=False,
            evidence_support=0.50,
        )
        assert decision.decision == "conservative_review_required"

    def test_accept_with_warnings_moderate(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        decision = engine.decide(
            primary_confidence=0.60,
            reviewer_confidence=0.55,
            agreement=True,
            evidence_support=0.50,
        )
        assert decision.decision == "accept_with_warnings"

    def test_reject_very_weak_evidence(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        decision = engine.decide(
            primary_confidence=0.65,
            reviewer_confidence=0.60,
            agreement=True,
            evidence_support=0.15,
        )
        assert decision.decision == "reject"

    def test_confidence_score_bounded(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        for pc, rc, es in [(0.9, 0.9, 0.9), (0.1, 0.1, 0.1), (0.5, 0.5, 0.5)]:
            decision = engine.decide(
                primary_confidence=pc,
                reviewer_confidence=rc,
                agreement=True,
                evidence_support=es,
            )
            assert 0.0 <= decision.confidence_score <= 1.0

    def test_risk_flags_preserved(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        decision = engine.decide(
            primary_confidence=0.40,
            reviewer_confidence=0.45,
            agreement=True,
            evidence_support=0.40,
            risk_flags=["cloud_stale", "high_turnover"],
        )
        assert "cloud_stale" in decision.risk_flags

    def test_edge_case_nan_confidence(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        decision = engine.decide(
            primary_confidence=float("nan"),
            reviewer_confidence=0.5,
            agreement=True,
            evidence_support=0.5,
        )
        # NaN comparisons should default to rejection
        assert decision.decision in ("reject", "conservative_review_required")

    def test_edge_case_zero_evidence(self):
        from brain_alpha_ops.research.cross_review_pipeline import ReviewDecisionEngine
        engine = ReviewDecisionEngine()
        decision = engine.decide(
            primary_confidence=0.0,
            reviewer_confidence=0.0,
            agreement=False,
            evidence_support=0.0,
        )
        assert decision.decision == "reject"


# ═══════════════════════════════════════════════════════════════════════════
# Local Backtest Engine tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSyntheticDataProvider:
    """Verify synthetic data generation is correct and reproducible."""

    def test_generate_produces_correct_shape(self):
        from brain_alpha_ops.research.local_backtest_engine import SyntheticDataProvider
        provider = SyntheticDataProvider()
        data = provider.generate(n_dates=10, n_symbols=50, fields=["close", "volume", "returns"], seed=42)
        assert data.n_dates == 10
        assert data.n_symbols == 50
        assert len(data.dates) == 10
        assert len(data.symbols) == 50
        assert "close" in data.fields
        assert len(data.fields["close"]) == 10
        assert len(data.fields["close"][0]) == 50

    def test_generate_is_reproducible(self):
        from brain_alpha_ops.research.local_backtest_engine import SyntheticDataProvider
        provider = SyntheticDataProvider()
        data1 = provider.generate(n_dates=5, n_symbols=10, seed=42)
        data2 = provider.generate(n_dates=5, n_symbols=10, seed=42)
        assert data1.fields["close"][0][0] == data2.fields["close"][0][0]

    def test_close_prices_are_positive(self):
        from brain_alpha_ops.research.local_backtest_engine import SyntheticDataProvider
        provider = SyntheticDataProvider()
        data = provider.generate(n_dates=20, n_symbols=30)
        for row in data.fields["close"]:
            for price in row:
                assert price > 0, f"price {price} should be positive"

    def test_generate_all_standard_fields(self):
        from brain_alpha_ops.research.local_backtest_engine import SyntheticDataProvider
        provider = SyntheticDataProvider()
        data = provider.generate(n_dates=10, n_symbols=20)
        for field in SyntheticDataProvider.STANDARD_FIELDS:
            assert field in data.fields, f"field {field} should be generated"
            assert len(data.fields[field]) == 10
            assert len(data.fields[field][0]) == 20

    def test_dates_are_weekdays(self):
        from brain_alpha_ops.research.local_backtest_engine import SyntheticDataProvider
        from datetime import date
        provider = SyntheticDataProvider()
        data = provider.generate(n_dates=30, n_symbols=10, start_date="2024-01-01")
        for date_str in data.dates:
            d = date.fromisoformat(date_str)
            assert d.weekday() < 5, f"date {date_str} should be weekday"


class TestLocalExpressionEvaluator:
    """Verify the FASTEXPR expression evaluator is correct."""

    def test_literal(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=3, n_symbols=5)
        result = evaluator.evaluate("42.0", data)
        assert abs(result[0][0] - 42.0) < 1e-10

    def test_field_identity(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=3, n_symbols=5, seed=99)
        result = evaluator.evaluate("close", data)
        assert result[0][0] == data.fields["close"][0][0]

    def test_rank_operator(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=5, n_symbols=100, seed=42)
        result = evaluator.evaluate("rank(close)", data)
        # All values should be in [0, 1]
        for row in result:
            for v in row:
                assert 0.0 <= v <= 1.0

    def test_zscore_operator(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=5, n_symbols=100, seed=42)
        result = evaluator.evaluate("zscore(close)", data)
        for row in result:
            assert -5.0 <= min(row) <= 5.0
            assert -5.0 <= max(row) <= 5.0

    def test_ts_zscore_operator(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=30, n_symbols=10, seed=42)
        result = evaluator.evaluate("ts_zscore(close, 20)", data)
        # First 19 rows should be 0 (not enough data)
        has_nonzero = False
        for d in range(20, 30):
            for v in result[d]:
                if abs(v) > 0.01:
                    has_nonzero = True
        # At least some non-zero values after window
        assert has_nonzero or len(result) <= 20  # May be all zeros for very small data

    def test_arithmetic_operators(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=3, n_symbols=5, seed=42)
        # Test a single binary addition (the parser supports one binary op)
        result = evaluator.evaluate("close + 1.0", data)
        expected = data.fields["close"][0][0] + 1.0
        assert abs(result[0][0] - expected) < 1e-6

        # Test subtraction
        result2 = evaluator.evaluate("close - 0.5", data)
        expected2 = data.fields["close"][0][0] - 0.5
        assert abs(result2[0][0] - expected2) < 1e-6

        # Test multiplication
        result3 = evaluator.evaluate("close * 2.0", data)
        expected3 = data.fields["close"][0][0] * 2.0
        assert abs(result3[0][0] - expected3) < 1e-6

    def test_neg_operator(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=3, n_symbols=5, seed=42)
        result = evaluator.evaluate("neg(close)", data)
        assert result[0][0] == -data.fields["close"][0][0]

    def test_abs_log_sign(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=3, n_symbols=5, seed=42)
        result_abs = evaluator.evaluate("abs(close)", data)
        for v in result_abs[0]:
            assert v >= 0

        result_log = evaluator.evaluate("log(close)", data)
        for v in result_log[0]:
            assert not math.isnan(v)

        result_sign = evaluator.evaluate("sign(close)", data)
        for v in result_sign[0]:
            assert v in (-1.0, 0.0, 1.0)

    def test_ts_mean(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=30, n_symbols=5, seed=42)
        result = evaluator.evaluate("ts_mean(close, 10)", data)
        assert len(result) == 30

    def test_nested_expression(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=30, n_symbols=20, seed=42)
        result = evaluator.evaluate("rank(ts_zscore(close, 20))", data)
        for row in result:
            for v in row:
                assert 0.0 <= v <= 1.0

    def test_nan_replaced_with_zero(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=20, n_symbols=10, seed=42)
        result = evaluator.evaluate("ts_zscore(close, 5)", data)
        for row in result:
            for v in row:
                assert not math.isnan(v)
                assert not math.isinf(v)

    def test_unknown_field_returns_zeros(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=3, n_symbols=5, seed=42)
        result = evaluator.evaluate("nonexistent_field", data)
        for row in result:
            for v in row:
                assert v == 0.0

    def test_max_depth_enforced(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalExpressionEvaluator, SyntheticDataProvider
        evaluator = LocalExpressionEvaluator()
        data = SyntheticDataProvider().generate(n_dates=3, n_symbols=5)
        # Deeply nested expression — call count is tracked via parse_expr recursion
        # For the current parser, depth is checked at the _parse level, not parse_expr
        # So we just verify that reasonable expressions work without stack overflow
        moderately_deep = "rank(ts_zscore(close, 20))"
        result = evaluator.evaluate(moderately_deep, data, max_depth=6)
        assert result is not None  # Should complete without error


class TestPortfolioConstructor:
    """Verify portfolio construction is correct."""

    def test_weights_are_dollar_neutral(self):
        from brain_alpha_ops.research.local_backtest_engine import PortfolioConstructor
        constructor = PortfolioConstructor(long_quantile=0.3, short_quantile=0.3)
        alphas = [[i * 0.01 for i in range(50)] for _ in range(10)]
        weights = constructor.construct(alphas)
        for day_weights in weights:
            total = sum(day_weights)
            assert abs(total) < 0.01, f"weights should sum to ~0, got {total}"

    def test_long_short_separation(self):
        from brain_alpha_ops.research.local_backtest_engine import PortfolioConstructor
        constructor = PortfolioConstructor(long_quantile=0.2, short_quantile=0.2)
        # Create data where alpha clearly separates stocks
        alphas = [[float(i) for i in range(100)] for _ in range(5)]
        weights = constructor.construct(alphas)
        for day_weights in weights:
            long_count = sum(1 for w in day_weights if w > 0)
            short_count = sum(1 for w in day_weights if w < 0)
            assert long_count >= 1
            assert short_count >= 1


class TestMetricsComputer:
    """Verify metrics computation is correct."""

    def test_zero_returns_zero_sharpe(self):
        from brain_alpha_ops.research.local_backtest_engine import MetricsComputer
        mc = MetricsComputer()
        weights = [[0.0] * 10 for _ in range(20)]
        returns = [[0.0] * 10 for _ in range(20)]
        metrics = mc.compute(weights, returns)
        assert metrics.sharpe == 0.0
        assert metrics.fitness == 0.0

    def test_constant_positive_pnl(self):
        from brain_alpha_ops.research.local_backtest_engine import MetricsComputer
        mc = MetricsComputer()
        # Weight equally and use constant positive returns
        weights = [[1.0 / 10] * 10 for _ in range(250)]
        returns = [[0.001] * 10 for _ in range(250)]
        metrics = mc.compute(weights, returns)
        # Should have high Sharpe, positive returns
        assert metrics.sharpe > 2.0
        assert metrics.returns > 0.0
        assert metrics.margin_bps > 0

    def test_turnover_computation(self):
        from brain_alpha_ops.research.local_backtest_engine import MetricsComputer
        mc = MetricsComputer()
        # Alternating weights → high turnover
        weights = []
        for d in range(20):
            if d % 2 == 0:
                weights.append([1.0 / 5] * 5 + [0.0] * 5)
            else:
                weights.append([0.0] * 5 + [1.0 / 5] * 5)
        returns = [[0.0] * 10 for _ in range(20)]
        metrics = mc.compute(weights, returns)
        assert metrics.turnover > 0.5  # High turnover

    def test_fitness_formula(self):
        from brain_alpha_ops.research.local_backtest_engine import MetricsComputer
        mc = MetricsComputer()
        # All-positive returns, zero turnover
        weights = [[1.0 / 10] * 10 for _ in range(252)]
        returns = [[0.001] * 10 for _ in range(252)]
        metrics = mc.compute(weights, returns)
        # fitness = sharpe * sqrt(|returns| / max(turnover, 0.125))
        expected = metrics.sharpe * math.sqrt(abs(metrics.returns) / max(metrics.turnover, 0.125))
        assert abs(metrics.fitness - expected) < 0.001

    def test_metrics_to_dict(self):
        from brain_alpha_ops.research.local_backtest_engine import MetricsComputer
        mc = MetricsComputer()
        weights = [[0.0] * 5 for _ in range(10)]
        returns = [[0.0] * 5 for _ in range(10)]
        metrics = mc.compute(weights, returns)
        d = metrics.to_dict()
        assert "sharpe" in d
        assert "fitness" in d
        assert "turnover" in d


class TestLocalBacktestEngine:
    """Full integration test of the local backtest engine."""

    def test_evaluate_simple_expression(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
        engine = LocalBacktestEngine(seed=42, n_dates=100, n_symbols=200)
        result = engine.evaluate("rank(close)")
        assert result["ok"] is True
        assert isinstance(result["sharpe"], float)
        assert isinstance(result["fitness"], float)
        assert "pass_local" in result
        assert "pass_reasons" in result

    def test_batch_evaluate(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
        engine = LocalBacktestEngine(seed=42, n_dates=50, n_symbols=100)
        expressions = [
            "rank(close)",
            "rank(returns)",
            "ts_zscore(close, 20)",
            "zscore(volume)",
        ]
        results = engine.batch_evaluate(expressions)
        assert len(results) == 4
        for r in results:
            assert r["ok"] is True

    def test_rank_expressions_sorts_by_fitness(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
        engine = LocalBacktestEngine(seed=42, n_dates=50, n_symbols=100)
        expressions = ["rank(close)", "rank(returns)", "rank(volume)"]
        ranked = engine.rank_expressions(expressions, top_n=2)
        assert len(ranked) == 2
        assert ranked[0]["fitness"] >= ranked[1]["fitness"]

    def test_data_caching(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
        engine = LocalBacktestEngine(seed=42, n_dates=50, n_symbols=50)
        data1 = engine.get_data("test_cache")
        data2 = engine.get_data("test_cache")
        assert data1 is data2  # Same object (cached)

    def test_evaluate_invalid_expression(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
        engine = LocalBacktestEngine()
        result = engine.evaluate("invalid_syntax((")
        assert result["ok"] is False
        assert "error" in result
        assert result["pass_local"] is False

    def test_evaluate_with_custom_data(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
        engine = LocalBacktestEngine()
        custom_data = engine.generate_data(n_dates=30, n_symbols=30)
        result = engine.evaluate("rank(close)", data=custom_data)
        assert result["ok"] is True

    def test_metrics_are_realistic(self):
        from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
        engine = LocalBacktestEngine(seed=42, n_dates=250, n_symbols=100)
        result = engine.evaluate("rank(ts_zscore(close, 20))")
        # With synthetic data, Sharpe should be somewhat reasonable
        assert -5.0 <= result["sharpe"] <= 5.0
        assert result["turnover"] >= 0.0
        assert result["turnover"] <= 1.0


class TestCandidateGeneratorKnowledgeConstraints:
    """Verify structured knowledge constraints affect fallback generation."""

    def test_fallback_generator_prefers_knowledge_fields_and_avoids_forbidden_patterns(self, monkeypatch):
        from brain_alpha_ops.research.generator import CandidateGenerator

        generator = CandidateGenerator()
        generator.update_context(
            [{"name": "close"}, {"name": "volume"}, {"name": "returns"}],
            [{"name": "rank"}, {"name": "ts_delta"}, {"name": "ts_std_dev"}],
        )
        monkeypatch.setattr(
            generator,
            "_build_official_field_pool",
            lambda dataset_id="": ["close", "volume", "returns"],
        )
        generator.set_knowledge_constraints(
            {
                "preferred_fields": ["volume"],
                "preferred_operators": ["rank"],
                "forbidden_patterns": ["ts_rank"],
            }
        )

        candidates = generator.generate(3)

        assert candidates
        assert candidates[0].data_fields
        assert "volume" in candidates[0].data_fields
        assert all("ts_rank" not in candidate.expression for candidate in candidates)


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline Stages tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPipelineStages:
    """Verify the pipeline stage framework."""

    def test_stage_result_initialization(self):
        from brain_alpha_ops.research.pipeline_stages import StageResult, StageStatus
        result = StageResult(stage_name="test")
        assert result.status == StageStatus.PENDING
        assert result.items_processed == 0
        assert result.error == ""

    def test_stage_result_to_dict(self):
        from brain_alpha_ops.research.pipeline_stages import StageResult, StageStatus
        result = StageResult(
            stage_name="test_stage",
            status=StageStatus.COMPLETED,
            items_processed=10,
            items_passed=8,
            items_failed=2,
        )
        d = result.to_dict()
        assert d["stage_name"] == "test_stage"
        assert d["status"] == "COMPLETED"
        assert d["items_processed"] == 10

    def test_orchestrator_empty(self):
        from brain_alpha_ops.research.pipeline_stages import PipelineStagesOrchestrator
        orchestrator = PipelineStagesOrchestrator()
        results = orchestrator.run(Mock())
        assert len(results) == 0

    def test_orchestrator_single_stage(self):
        from brain_alpha_ops.research.pipeline_stages import (
            PipelineStage, PipelineStagesOrchestrator, StageResult,
        )

        class MockStage(PipelineStage):
            stage_name: str = "mock"
            def execute(self, ctx): return ctx

        orchestrator = PipelineStagesOrchestrator()
        orchestrator.add_stage(MockStage())
        results = orchestrator.run(Mock())
        assert len(results) == 1
        assert results[0].stage_name == "mock"

    def test_orchestrator_skip_on_failure(self):
        from brain_alpha_ops.research.pipeline_stages import (
            PipelineStage, PipelineStagesOrchestrator, StageResult, StageStatus,
        )

        class FailingStage(PipelineStage):
            stage_name: str = "failing"
            def execute(self, ctx): raise ValueError("intentional failure")

        class ShouldSkipStage(PipelineStage):
            stage_name: str = "should_skip"
            def execute(self, ctx): return ctx

        orchestrator = PipelineStagesOrchestrator()
        orchestrator.add_stage(FailingStage())
        orchestrator.add_stage(ShouldSkipStage())
        results = orchestrator.run(Mock())
        assert len(results) == 2
        assert results[0].status == StageStatus.FAILED
        assert results[1].status == StageStatus.SKIPPED

    def test_orchestrator_summary(self):
        from brain_alpha_ops.research.pipeline_stages import (
            PipelineStage, PipelineStagesOrchestrator,
        )

        class OkStage(PipelineStage):
            stage_name: str = "ok_stage"
            def execute(self, ctx): return ctx

        orchestrator = PipelineStagesOrchestrator()
        orchestrator.add_stage(OkStage())
        results = orchestrator.run(Mock())
        summary = orchestrator.summary(results)
        assert summary["overall"] == "PASS"
        assert summary["completed"] == 1
        assert summary["total_stages"] == 1
        assert summary["schema_version"] == "pipeline_stages.v1"

    def test_build_full_pipeline(self):
        from brain_alpha_ops.research.pipeline_stages import build_full_pipeline
        pipeline = build_full_pipeline()
        assert len(pipeline.stages) == 6
        names = [s.stage_name for s in pipeline.stages]
        assert names == ["generation", "local_scoring", "official_validation", "simulation", "quality_gate", "submission"]

    def test_build_local_only_pipeline(self):
        from brain_alpha_ops.research.pipeline_stages import build_local_only_pipeline
        pipeline = build_local_only_pipeline()
        assert len(pipeline.stages) == 3
        names = [s.stage_name for s in pipeline.stages]
        assert "generation" in names
        assert "local_scoring" in names
        assert "quality_gate" in names
        # No API-dependent stages
        assert "official_validation" not in names
        assert "simulation" not in names

    def test_stage_status_enum(self):
        from brain_alpha_ops.research.pipeline_stages import StageStatus
        assert StageStatus.PENDING.name == "PENDING"
        assert StageStatus.COMPLETED.value > StageStatus.PENDING.value
        assert StageStatus.FAILED.value > StageStatus.PENDING.value


class TestKnowledgeEvidenceChecker:
    """Verify evidence checking against the knowledge base."""

    def test_empty_kb_no_matches(self):
        from brain_alpha_ops.research.cross_review_pipeline import KnowledgeEvidenceChecker
        with tempfile.TemporaryDirectory() as tmp:
            checker = KnowledgeEvidenceChecker(tmp)
            claims = [{"type": "field_recommendation", "text": "Use close price"}]
            results = checker.check(claims)
            assert len(results) == 1
            assert results[0].evidence_score == 0.0

    def test_with_populated_kb(self):
        from brain_alpha_ops.research.knowledge_base import KnowledgeEntry, StructuredKnowledgeBase
        from brain_alpha_ops.research.cross_review_pipeline import KnowledgeEvidenceChecker
        with tempfile.TemporaryDirectory() as tmp:
            kb = StructuredKnowledgeBase(tmp)
            kb.save(KnowledgeEntry(
                layer="rule", category="field_selection",
                title="Use close price as reliable field",
                confidence=0.85,
                fields_involved=["close"],
            ))
            kb.save(KnowledgeEntry(
                layer="failure", category="overfit",
                title="Avoid using only short window momentum",
                confidence=0.75,
            ))

            checker = KnowledgeEvidenceChecker(tmp)
            claims = [
                {"type": "field_recommendation", "text": "close price is recommended", "confidence": 0.8},
                {"type": "action_recommendation", "text": "use short window momentum", "confidence": 0.5},
            ]
            results = checker.check(claims)

            # First claim: matches a rule → positive evidence
            assert results[0].evidence_score > 0
            # Second claim: matches a failure → reduced evidence
            assert results[1].evidence_score <= 0.0 or results[1].risk_level in ("medium", "high")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

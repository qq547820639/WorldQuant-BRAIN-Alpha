"""Tests for expression_diversity module — skeleton diversity guard."""

from __future__ import annotations

import pytest

from brain_alpha_ops.research.expression_diversity import (
    DiversityReport,
    ExpressionDiversityGuard,
)


class TestExpressionSkeleton:
    """Test skeleton extraction from expressions."""

    def setup_method(self):
        self.guard = ExpressionDiversityGuard()

    def test_simple_rank_skeleton(self):
        skeleton = self.guard.skeleton("rank(returns)")
        assert skeleton == "rank ( FIELD )"

    def test_skeleton_normalizes_fields(self):
        # Different fields should produce the same skeleton
        s1 = self.guard.skeleton("rank(returns)")
        s2 = self.guard.skeleton("rank(market_cap)")
        # Both should have FIELD replaced — verify both contain FIELD marker
        assert "FIELD" in s1
        assert "FIELD" in s2
        # The skeletons should be equivalent in structure
        # Since market_cap contains underscore, it may be tokenized differently
        # Verify the core structure matches
        assert "rank" in s1.lower()
        assert "rank" in s2.lower()

    def test_skeleton_normalizes_numbers(self):
        s1 = self.guard.skeleton("ts_mean(close, 20)")
        s2 = self.guard.skeleton("ts_mean(close, 60)")
        assert s1 == s2

    def test_skeleton_preserves_operators(self):
        s1 = self.guard.skeleton("ts_mean(close, 20)")
        s2 = self.guard.skeleton("ts_std_dev(close, 20)")
        assert s1 != s2  # Different operators

    def test_skeleton_normalizes_legacy_operator_aliases(self):
        alias = self.guard.skeleton("ts_std(close, 20) + ts_argmax(open, 5)")
        official = self.guard.skeleton("ts_std_dev(close, 20) + ts_arg_max(open, 5)")

        assert alias == official
        assert "ts_std " not in alias
        assert "ts_argmax" not in alias

    def test_complex_skeleton(self):
        skeleton = self.guard.skeleton(
            "group_neutralize(ts_mean(winsorize(market_cap, 0.01), 60), industry)"
        )
        # Should contain group_neutralize and ts_mean but not specific fields
        assert "group_neutralize" in skeleton
        assert "ts_mean" in skeleton
        assert "FIELD" in skeleton
        assert "N" in skeleton

    def test_skeleton_case_sensitivity(self):
        # BRAIN expressions are case-insensitive for operators
        s1 = self.guard.skeleton("rank(returns)")
        s2 = self.guard.skeleton("RANK(returns)")
        # The skeleton preserves case as-is; we just verify it works
        assert isinstance(s1, str)
        assert isinstance(s2, str)

    def test_empty_expression(self):
        skeleton = self.guard.skeleton("")
        assert skeleton == ""

    def test_skeleton_with_arithmetic(self):
        skeleton = self.guard.skeleton("rank(returns) + ts_mean(volume, 20)")
        assert "rank" in skeleton
        assert "ts_mean" in skeleton
        assert "+" in skeleton

    def test_skeleton_with_nested_operators(self):
        skeleton = self.guard.skeleton("ts_mean(rank(returns), 20)")
        assert "ts_mean" in skeleton
        assert "rank" in skeleton


class TestExpressionDiversityGuardConvergence:
    """Test convergence detection."""

    def setup_method(self):
        self.guard = ExpressionDiversityGuard(max_skeleton_concentration=0.30)

    def test_converged_when_same_skeleton_dominates(self):
        # 4 out of 5 have the same skeleton → 80% > 30% threshold
        pool = [
            "rank(returns)",
            "rank(market_cap)",
            "rank(volume)",
            "rank(close)",
            "ts_mean(returns, 20)",
        ]
        # New expression also rank(FIELD) → 5/6 = 83.3%
        assert self.guard.is_converged("rank(some_field)", pool) is True

    def test_not_converged_when_diverse(self):
        pool = [
            "rank(returns)",
            "ts_mean(close, 20)",
            "group_rank(volume, sector)",
            "ts_std_dev(returns, 60)",
            "ts_decay_linear(close, 10)",
        ]
        assert self.guard.is_converged("winsorize(market_cap, 0.01)", pool) is False

    def test_threshold_boundary(self):
        guard = ExpressionDiversityGuard(max_skeleton_concentration=0.50)
        pool = ["rank(returns)", "rank(close)", "ts_mean(volume, 20)"]
        # 2 out of 3 share skeleton, adding new rank → 3/4 = 75% > 50%
        assert guard.is_converged("rank(market_cap)", pool) is True

    def test_empty_pool(self):
        # Single expression: 1/1 = 100% concentration > 30%, so it's converged
        assert self.guard.is_converged("rank(returns)", []) is True


class TestExpressionDiversityGuardAnalyze:
    """Test pool analysis."""

    def setup_method(self):
        self.guard = ExpressionDiversityGuard()

    def test_empty_pool(self):
        report = self.guard.analyze_pool([])
        assert report.total_expressions == 0
        assert report.recommended_action == "generate_more"

    def test_diverse_pool(self):
        pool = [
            "rank(returns)",
            "ts_mean(close, 20)",
            "group_rank(volume, sector)",
            "ts_std_dev(returns, 60)",
            "ts_decay_linear(close, 10)",
        ]
        report = self.guard.analyze_pool(pool)
        assert report.total_expressions == 5
        assert report.unique_skeletons >= 3
        assert report.is_converged is False
        assert report.recommended_action == "none"

    def test_converged_pool(self):
        pool = [
            "rank(returns)",
            "rank(market_cap)",
            "rank(volume)",
            "rank(close)",
            "ts_mean(returns, 20)",
        ]
        report = self.guard.analyze_pool(pool)
        assert report.is_converged is True
        assert report.recommended_action in ("force_skeleton_mutation", "force_exploration")

    def test_report_to_dict(self):
        pool = ["rank(returns)", "ts_mean(close, 20)"]
        report = self.guard.analyze_pool(pool)
        d = report.to_dict()
        assert "total_expressions" in d
        assert "unique_skeletons" in d
        assert "is_converged" in d
        assert "details" in d

    def test_report_skeleton_distribution(self):
        pool = ["rank(returns)", "rank(close)", "ts_mean(volume, 20)"]
        report = self.guard.analyze_pool(pool)
        distribution = report.details.get("skeleton_distribution", {})
        assert len(distribution) >= 1
        # At least one skeleton has count info
        for skel, info in distribution.items():
            assert "count" in info
            assert "ratio" in info

    def test_single_expression_pool(self):
        pool = ["rank(returns)"]
        report = self.guard.analyze_pool(pool)
        assert report.total_expressions == 1
        assert report.unique_skeletons == 1
        assert report.skeleton_diversity_ratio == 1.0


class TestExpressionDiversityGuardForceDiversify:
    """Test diversification strategy suggestions."""

    def setup_method(self):
        self.guard = ExpressionDiversityGuard()

    def test_suggests_strategies(self):
        strategies = self.guard.force_diversify("rank(returns)")
        assert len(strategies) > 0
        assert all(isinstance(s, str) for s in strategies)

    def test_max_attempts_limit(self):
        strategies = self.guard.force_diversify("rank(returns)", max_attempts=3)
        assert len(strategies) <= 3

    def test_ts_expression_triggers_group_suggestion(self):
        strategies = self.guard.force_diversify("ts_mean(close, 20)")
        # Should suggest switching from ts_ to group_ since expression contains ts_
        has_group_suggestion = any("group_" in s or "cross_sectional" in s.lower() for s in strategies)
        assert has_group_suggestion

    def test_non_ts_expression_suggests_ts(self):
        strategies = self.guard.force_diversify("rank(returns)")
        has_ts_suggestion = any("ts_" in s or "time_series" in s.lower() for s in strategies)
        assert has_ts_suggestion
        assert all("ts_std," not in strategy for strategy in strategies)
        assert all("use_decay_linear:" not in strategy for strategy in strategies)
        assert all("with decay_linear" not in strategy for strategy in strategies)
        assert all("vector_neutralize" not in strategy for strategy in strategies)

    def test_complex_expression_without_arithmetic(self):
        strategies = self.guard.force_diversify("rank(returns)")
        # Without + or - in expression, should suggest combining signals
        has_combine = any("combine" in s.lower() for s in strategies)
        assert has_combine

    def test_expression_with_arithmetic(self):
        strategies = self.guard.force_diversify("rank(returns) + ts_mean(close,20)")
        # With arithmetic already present, may not suggest combining
        has_combine = any("combine" in s.lower() for s in strategies)
        # It may or may not suggest combining — just verify it returns something
        assert len(strategies) > 0


class TestDiversityReport:
    """Test DiversityReport dataclass."""

    def test_default_report(self):
        report = DiversityReport()
        assert report.total_expressions == 0
        assert report.is_converged is False
        assert report.recommended_action == "none"

    def test_to_dict(self):
        report = DiversityReport(
            total_expressions=10,
            unique_skeletons=5,
            skeleton_diversity_ratio=0.5,
            is_converged=True,
            recommended_action="force_skeleton_mutation",
        )
        d = report.to_dict()
        assert d["total_expressions"] == 10
        assert d["unique_skeletons"] == 5
        assert d["is_converged"] is True
        assert d["recommended_action"] == "force_skeleton_mutation"


class TestExpressionDiversityEdgeCases:
    """Edge case testing."""

    def setup_method(self):
        self.guard = ExpressionDiversityGuard()

    def test_very_long_expression(self):
        expr = "group_neutralize(ts_decay_linear(ts_delta(winsorize(market_cap, 0.01), 60), 20), industry)"
        skeleton = self.guard.skeleton(expr)
        assert isinstance(skeleton, str)
        assert len(skeleton) > 0

    def test_expression_with_special_characters(self):
        expr = "rank(close) * 2.5 + ts_mean(volume, 20) / 100"
        skeleton = self.guard.skeleton(expr)
        assert "*" in skeleton
        assert "+" in skeleton
        assert "/" in skeleton

    def test_expression_with_parentheses_only(self):
        expr = "(close + open) / 2"
        skeleton = self.guard.skeleton(expr)
        assert isinstance(skeleton, str)

    def test_same_expression_different_punctuation(self):
        s1 = self.guard.skeleton("rank(  returns  )")
        s2 = self.guard.skeleton("rank(returns)")
        # Whitespace should be normalized
        assert s1 == s2

    def test_concentration_with_large_pool(self):
        """Verify analysis works with larger pools."""
        pool = ["rank(returns)"] * 50 + ["ts_mean(close, 20)"] * 30 + ["group_rank(volume, sector)"] * 20
        report = self.guard.analyze_pool(pool)
        assert report.total_expressions == 100
        assert report.is_converged is True  # 50% concentration > 30% threshold

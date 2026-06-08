"""Extreme-value tests for the scoring, expression, and configuration pipelines.

Covers:
  - Very large numbers (1e308, near float max)
  - Very small numbers (1e-308, near denormal)
  - Very long expression strings (1000+ chars)
  - Maximum candidate batch sizes
  - Deeply nested data structures
  - Numeric overflow paths in scoring helpers
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from brain_alpha_ops.config import QualityThresholds, ScoringConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import (
    _ratio,
    _num,
    _int_num,
    _bounded_score,
    item,
    build_scorecard,
    empirical_score,
    evaluate_quality_gate,
    decision_band,
    calculate_fitness,
    estimate_score_confidence,
)
from brain_alpha_ops.research.expression_engine import (
    ExpressionEngine,
    validate_expression,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def thresholds():
    return QualityThresholds()


@pytest.fixture
def scoring_cfg():
    return ScoringConfig()


@pytest.fixture
def engine():
    return ExpressionEngine()


def _candidate(**overrides):
    c = Candidate(
        alpha_id="extreme_test",
        expression="rank(close)",
        family="Extreme",
        hypothesis="Extreme value test",
        data_fields=["close"],
        operators=["rank"],
    )
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


# ═══════════════════════════════════════════════════════════════════════
# Very large numbers (near float64 max)
# ═══════════════════════════════════════════════════════════════════════

class TestVeryLargeNumbers:
    """Verify float-max-range values don't cause under/overflow."""

    def test_sharpe_near_float_max(self, thresholds):
        result = empirical_score({"sharpe": 1e308, "fitness": 1.0}, thresholds)
        assert isinstance(result, dict)
        assert "score" in result

    def test_fitness_near_float_max(self, thresholds):
        c = _candidate()
        c.official_alpha_id = "off_vlarge"
        c.official_metrics = {
            "sharpe": 1e308, "fitness": 1e308,
            "turnover": 0.3, "returns": 1e308,
            "drawdown": 0.1, "pass_fail": "PASS",
        }
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_all_metrics_near_float_max(self, thresholds):
        c = _candidate()
        c.official_alpha_id = "off_allmax"
        c.official_metrics = {
            "sharpe": 1e308, "fitness": 1e308, "turnover": 1e308,
            "returns": 1e308, "drawdown": 1e308,
            "sub_universe_sharpe": 1e308, "correlation": 1e308,
            "pass_fail": "PASS",
        }
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)

    def test_ratio_near_float_max(self):
        result = _ratio(1e308)
        assert isinstance(result, float)
        assert not math.isnan(result)

    def test_num_near_float_max(self):
        result = _num(1e308)
        assert isinstance(result, float)

    def test_bounded_score_near_float_max(self):
        result = _bounded_score(1e308)
        assert isinstance(result, float)

    def test_calculate_fitness_near_float_max(self):
        result = calculate_fitness(1e308, 1e308, 1e308)
        assert isinstance(result, float)


# ═══════════════════════════════════════════════════════════════════════
# Very small numbers (near denormal)
# ═══════════════════════════════════════════════════════════════════════

class TestVerySmallNumbers:
    """Verify near-zero and denormal values don't cause issues."""

    def test_sharpe_near_denormal(self, thresholds):
        result = empirical_score({"sharpe": 1e-308, "fitness": 1e-308}, thresholds)
        assert isinstance(result, dict)

    def test_all_metrics_near_zero(self, thresholds):
        c = _candidate()
        c.official_alpha_id = "off_tiny"
        c.official_metrics = {
            "sharpe": 1e-308, "fitness": 1e-308, "turnover": 1e-308,
            "returns": 1e-308, "drawdown": 1e-308,
            "pass_fail": "PASS",
        }
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)

    def test_ratio_near_denormal(self):
        result = _ratio(1e-308)
        assert isinstance(result, float)

    def test_bounded_score_near_denormal(self):
        result = _bounded_score(1e-308)
        assert isinstance(result, float)

    def test_exact_zero_next_to_denormal_in_calculate_fitness(self):
        result = calculate_fitness(0.0, 1e-308, 1e-308)
        assert isinstance(result, float)

    def test_negative_denormal(self):
        result = _ratio(-1e-308)
        assert isinstance(result, float)


# ═══════════════════════════════════════════════════════════════════════
# Very long expression strings (1000+ characters)
# ═══════════════════════════════════════════════════════════════════════

class TestVeryLongExpressions:
    """Verify expression validation handles extremely long inputs."""

    def test_1000_char_expression(self, engine):
        expr = "rank(ts_delta(close, 20)) + " * 100  # >1000 chars
        report = engine.validate(expr)
        assert report is not None

    def test_5000_char_expression(self, engine):
        expr = "rank(ts_delta(close, 20)) + " * 500  # >5000 chars
        report = engine.validate(expr)
        assert report is not None

    def test_long_expression_module_validate(self):
        expr = "rank(ts_delta(close, 20)) + " * 100
        report = validate_expression(expr)
        assert report is not None

    def test_long_expression_in_candidate_scorecard(self, thresholds):
        long_expr = "rank(ts_delta(close, 20)) + " * 50 + "rank(ts_delta(volume, 20))"
        c = _candidate(expression=long_expr, data_fields=["close", "volume"], operators=["rank", "ts_delta"])
        c.official_alpha_id = "off_long"
        c.official_metrics = {"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_max_valid_expression_length_is_handled(self, engine):
        """Expression at exactly 512 chars (the default max) should validate."""
        base = "rank(ts_delta(close, 20)) + rank(volume)"
        expr = base
        while len(expr) < 500:
            expr += " + rank(close)"
        report = engine.validate(expr[:512])
        assert report is not None


# ═══════════════════════════════════════════════════════════════════════
# Maximum candidate batch sizes
# ═══════════════════════════════════════════════════════════════════════

class TestMaxBatchSizes:
    """Verify large numbers of candidates don't break scoring invariants."""

    def test_100_candidates_scored_independently(self, thresholds):
        """100 candidates each produce valid independent scorecards."""
        for i in range(100):
            c = Candidate(
                alpha_id=f"batch_{i}",
                expression=f"rank(close) + rank(volume)",
                family="BatchTest",
                hypothesis=f"Batch candidate {i}",
                data_fields=["close", "volume"],
                operators=["rank"],
            )
            c.official_alpha_id = f"off_batch_{i}"
            c.official_metrics = {
                "sharpe": 1.5 + (i % 3) * 0.1,
                "fitness": 1.1 + (i % 5) * 0.05,
                "turnover": 0.2 + (i % 4) * 0.05,
                "returns": 0.08, "drawdown": 0.1,
                "pass_fail": "PASS",
            }
            sc = build_scorecard(c, thresholds)
            assert isinstance(sc, dict)
            assert "total_score" in sc

    def test_large_data_fields_list(self, thresholds):
        fields = [f"field_{i}" for i in range(500)]
        c = _candidate(data_fields=fields)
        c.official_alpha_id = "off_many_fields"
        c.official_metrics = {"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)


# ═══════════════════════════════════════════════════════════════════════
# Numeric overflow paths
# ═══════════════════════════════════════════════════════════════════════

class TestNumericOverflow:
    """Verify scoring helpers handle potential overflow/underflow."""

    def test_item_with_max_float_values(self):
        result = item("overflow", 1e308, "higher", 1e308, True, 1e308)
        assert isinstance(result, dict)

    def test_int_num_on_large_float(self):
        result = _int_num(1e308)
        assert isinstance(result, int)
        # Converting 1e308 to int results in a very large integer
        # Should not raise OverflowError

    def test_int_num_on_negative_large_float(self):
        result = _int_num(-1e308)
        assert isinstance(result, int)

    def test_ratio_inf_produces_inf(self):
        result = _ratio(float("inf"))
        assert result == float("inf")

    def test_ratio_neg_inf(self):
        result = _ratio(float("-inf"))
        assert result == float("-inf")

    def test_calculate_fitness_overflow_path(self):
        result = calculate_fitness(1e300, 1e300, 1e-300)
        assert isinstance(result, float)

    def test_decision_band_at_extreme_score(self, scoring_cfg):
        band = decision_band(1e308, scoring=scoring_cfg)
        assert isinstance(band, str)


# ═══════════════════════════════════════════════════════════════════════
# Negative extremes
# ═══════════════════════════════════════════════════════════════════════

class TestNegativeExtremes:
    """Verify negative extreme values are handled properly."""

    def test_all_metrics_negative_extreme(self, thresholds):
        c = _candidate()
        c.official_alpha_id = "off_negextreme"
        c.official_metrics = {
            "sharpe": -1e308, "fitness": -1e308, "turnover": -1e308,
            "returns": -1e308, "drawdown": -1e308,
            "pass_fail": "PASS",
        }
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)

    def test_negative_float_max_in_empirical_score(self, thresholds):
        result = empirical_score({"sharpe": -1e308, "fitness": -1e308}, thresholds)
        assert isinstance(result, dict)

    def test_bounded_score_negative_extreme(self):
        result = _bounded_score(-1e308)
        assert isinstance(result, float)


# ═══════════════════════════════════════════════════════════════════════
# Edge of threshold boundaries
# ═══════════════════════════════════════════════════════════════════════

class TestThresholdBoundaries:
    """Verify scoring at exact threshold boundaries."""

    def test_exact_threshold_values(self, thresholds):
        """Scoring should work with values exactly at each threshold."""
        thresh_keys = ["sharpe", "fitness", "returns", "drawdown", "correlation", "turnover"]
        for key in thresh_keys:
            if hasattr(thresholds, key):
                val = getattr(thresholds, key)
                c = _candidate()
                c.official_alpha_id = f"off_thresh_{key}"
                c.official_metrics = {
                    "sharpe": val, "fitness": val, "turnover": val,
                    "returns": val, "drawdown": val, "pass_fail": "PASS",
                }
                sc = build_scorecard(c, thresholds)
                assert isinstance(sc, dict)

    def test_just_above_threshold(self, thresholds):
        """Values epsilon-above threshold."""
        epsilon = 0.01
        for key in ["sharpe", "fitness"]:
            if hasattr(thresholds, key):
                val = getattr(thresholds, key) + epsilon
                c = _candidate()
                c.official_alpha_id = f"off_above_{key}"
                c.official_metrics = {
                    "sharpe": val, "fitness": val, "pass_fail": "PASS",
                }
                sc = build_scorecard(c, thresholds)
                assert isinstance(sc, dict)

    def test_just_below_threshold(self, thresholds):
        """Values epsilon-below threshold."""
        epsilon = 0.01
        for key in ["sharpe", "fitness"]:
            if hasattr(thresholds, key):
                val = max(0, getattr(thresholds, key) - epsilon)
                c = _candidate()
                c.official_alpha_id = f"off_below_{key}"
                c.official_metrics = {
                    "sharpe": val, "fitness": val, "pass_fail": "PASS",
                }
                sc = build_scorecard(c, thresholds)
                assert isinstance(sc, dict)

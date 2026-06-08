"""Boundary-condition tests for core scoring, expression validation, and candidate operations.

Covers:
  - Null/None inputs for candidate generation and scoring functions
  - Empty string expressions
  - Zero-length collections
  - NaN and Infinity values in scoring
  - Negative values where positive expected
  - Division-by-zero edge cases in helper functions
  - Max-size inputs (very long expressions, many fields)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from brain_alpha_ops.config import OpsConfig, QualityThresholds, ScoringConfig
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import (
    _ratio,
    _num,
    _int_num,
    _bounded_score,
    item,
    check,
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
    complexity_score,
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


def _minimal_candidate(**overrides):
    c = Candidate(
        alpha_id="boundary_test",
        expression="rank(close)",
        family="Boundary",
        hypothesis="Boundary test",
        data_fields=["close"],
        operators=["rank"],
    )
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


# ═══════════════════════════════════════════════════════════════════════
# Null / None inputs
# ═══════════════════════════════════════════════════════════════════════

class TestNullNoneInputs:
    """Verify grace under null/None inputs for scoring and helper functions."""

    def test_empirical_score_with_null_metrics_returns_structured(self, thresholds):
        result = empirical_score({"sharpe": None, "fitness": None}, thresholds)
        assert isinstance(result, dict)
        assert "score" in result

    def test_empirical_score_with_empty_metrics(self, thresholds):
        result = empirical_score({}, thresholds)
        assert isinstance(result, dict)

    def test_build_scorecard_with_null_metrics_does_not_crash(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_boundary"
        c.official_metrics = {"sharpe": None, "fitness": None, "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_build_scorecard_with_missing_metrics_keys(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_boundary"
        c.official_metrics = {"pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_evaluate_quality_gate_with_null_metrics(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_boundary"
        c.official_metrics = {"sharpe": None, "fitness": None, "turnover": 0.3, "pass_fail": "PASS"}
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)
        assert "submission_ready" in gate

    def test_ratio_with_none_defaults_to_zero(self):
        assert _ratio(None) == 0.0

    def test_num_with_none_defaults_to_zero(self):
        assert _num(None) == 0.0

    def test_int_num_with_none_defaults_to_zero(self):
        assert _int_num(None) == 0

    def test_candidate_with_none_expression(self):
        c = _minimal_candidate(expression=None)
        assert c.expression is None

    def test_candidate_none_data_fields_preserved_as_none(self):
        """__post_init__ only normalizes if not None; None stays None."""
        c = _minimal_candidate(data_fields=None)
        assert c.data_fields is None

    def test_candidate_none_operators_preserved_as_none(self):
        c = _minimal_candidate(operators=None)
        assert c.operators is None


# ═══════════════════════════════════════════════════════════════════════
# Empty string expressions
# ═══════════════════════════════════════════════════════════════════════

class TestEmptyExpressions:
    """Verify behavior with empty or whitespace-only expressions."""

    def test_empty_expression_validation(self, engine):
        report = engine.validate("")
        assert report is not None
        assert hasattr(report, "valid")

    def test_whitespace_only_expression(self, engine):
        report = engine.validate("   ")
        assert report is not None

    def test_empty_expression_in_candidate_scorecard(self, thresholds):
        c = _minimal_candidate(expression="")
        c.official_alpha_id = "off_empty"
        c.official_metrics = {"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_expression_with_newlines_only(self, engine):
        report = engine.validate("\n\n\n")
        assert report is not None

    def test_module_validate_expression_empty(self):
        report = validate_expression("")
        assert report is not None


# ═══════════════════════════════════════════════════════════════════════
# Zero-length collections
# ═══════════════════════════════════════════════════════════════════════

class TestZeroLengthCollections:
    """Verify behavior with empty lists and zero-length collections."""

    def test_zero_data_fields_candidate_scorecard(self, thresholds):
        c = _minimal_candidate(data_fields=[])
        c.official_alpha_id = "off_zero_fields"
        c.official_metrics = {"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_zero_operators_candidate_scorecard(self, thresholds):
        c = _minimal_candidate(operators=[])
        c.official_alpha_id = "off_zero_ops"
        c.official_metrics = {"sharpe": 1.5, "fitness": 1.1, "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_empty_source_tags_candidate(self):
        c = _minimal_candidate(source_tags=[])
        assert c.source_tags == []

    def test_candidate_to_dict_with_empty_collections(self):
        c = _minimal_candidate(data_fields=[], operators=[], source_tags=[])
        d = c.to_dict()
        assert "data_fields" in d
        assert "operators" in d


# ═══════════════════════════════════════════════════════════════════════
# NaN and Infinity values
# ═══════════════════════════════════════════════════════════════════════

class TestNaNInfinity:
    """Verify NaN and Infinity handling in scoring paths."""

    def test_empirical_score_with_nan_metrics(self, thresholds):
        result = empirical_score({"sharpe": float("nan"), "fitness": float("nan")}, thresholds)
        assert isinstance(result, dict)

    def test_empirical_score_with_inf_metrics(self, thresholds):
        result = empirical_score({"sharpe": float("inf"), "fitness": float("-inf")}, thresholds)
        assert isinstance(result, dict)

    def test_build_scorecard_with_nan_official_metrics(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_nan"
        c.official_metrics = {"sharpe": float("nan"), "fitness": float("nan"), "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_build_scorecard_with_inf_official_metrics(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_inf"
        c.official_metrics = {"sharpe": float("inf"), "fitness": float("inf"), "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_ratio_with_nan(self):
        assert math.isnan(_ratio(float("nan")))

    def test_ratio_with_infinity(self):
        assert _ratio(float("inf")) == float("inf")

    def test_num_with_nan_is_nan(self):
        assert math.isnan(_num(float("nan")))

    def test_num_with_infinity(self):
        assert _num(float("inf")) == float("inf")

    def test_bounded_score_with_nan(self):
        score = _bounded_score(float("nan"))
        assert isinstance(score, float)

    def test_bounded_score_with_infinity(self):
        score = _bounded_score(float("inf"))
        assert isinstance(score, float)

    def test_calculate_fitness_with_nan_inputs(self):
        result = calculate_fitness(float("nan"), 0.08, 0.25)
        assert isinstance(result, float)

    def test_calculate_fitness_with_inf_inputs(self):
        result = calculate_fitness(float("inf"), 0.08, 0.25)
        assert isinstance(result, float)


# ═══════════════════════════════════════════════════════════════════════
# Negative values where positive expected
# ═══════════════════════════════════════════════════════════════════════

class TestNegativeWherePositiveExpected:
    """Verify robustness when negative values appear where only positive is sensible."""

    def test_negative_sharpe_in_empirical_score(self, thresholds):
        result = empirical_score({"sharpe": -1.5, "fitness": -0.5}, thresholds)
        assert isinstance(result, dict)

    def test_negative_sharpe_in_build_scorecard(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_neg"
        c.official_metrics = {"sharpe": -0.8, "fitness": -0.3, "turnover": 0.3, "pass_fail": "PASS"}
        scorecard = build_scorecard(c, thresholds)
        assert isinstance(scorecard, dict)

    def test_negative_returns(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_neg_ret"
        c.official_metrics = {
            "sharpe": 1.5, "fitness": 1.1, "turnover": 0.3,
            "returns": -0.05, "drawdown": 0.1, "pass_fail": "PASS",
        }
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)

    def test_negative_turnover(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_neg_to"
        c.official_metrics = {
            "sharpe": 1.5, "fitness": 1.1, "turnover": -0.1,
            "returns": 0.08, "drawdown": 0.1, "pass_fail": "PASS",
        }
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)

    def test_negative_correlation(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_neg_corr"
        c.official_metrics = {
            "sharpe": 1.5, "fitness": 1.1, "turnover": 0.3,
            "returns": 0.08, "drawdown": 0.1, "correlation": -0.5,
            "pass_fail": "PASS",
        }
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)

    def test_negative_drawdown(self, thresholds):
        c = _minimal_candidate()
        c.official_alpha_id = "off_neg_dd"
        c.official_metrics = {
            "sharpe": 1.5, "fitness": 1.1, "turnover": 0.3,
            "returns": 0.08, "drawdown": -0.1, "pass_fail": "PASS",
        }
        gate = evaluate_quality_gate(c, thresholds)
        assert isinstance(gate, dict)


# ═══════════════════════════════════════════════════════════════════════
# Division by zero edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestDivisionByZero:
    """Verify robustness against division-by-zero paths."""

    def test_ratio_zero_denominator(self):
        result = _ratio(0.0)
        assert result == 0.0

    def test_ratio_bounded_zero_denominator(self):
        result = _ratio(0.0, bounded=True)
        assert result is not None

    def test_division_by_zero_in_empirical_score(self, thresholds):
        result = empirical_score({"sharpe": 0.0, "fitness": 0.0}, thresholds)
        assert isinstance(result, dict)

    def test_zero_fitness_in_calculate_fitness(self):
        result = calculate_fitness(1.5, 0.08, 0.0)
        assert isinstance(result, float)

    def test_calculate_fitness_all_zeros(self):
        result = calculate_fitness(0.0, 0.0, 0.0)
        assert isinstance(result, float)


# ═══════════════════════════════════════════════════════════════════════
# Max-size inputs
# ═══════════════════════════════════════════════════════════════════════

class TestMaxSizeInputs:
    """Verify tolerance for oversized inputs."""

    def test_very_long_expression_validation(self, engine):
        long_expr = "rank(ts_delta(close, 20)) + " * 100 + "rank(ts_delta(volume, 20))"
        report = engine.validate(long_expr)
        assert report is not None

    def test_many_data_fields_in_candidate(self):
        fields = [f"field_{i}" for i in range(200)]
        c = _minimal_candidate(data_fields=fields)
        assert len(c.data_fields) == 200

    def test_many_operators_in_candidate(self):
        ops = [f"op_{i}" for i in range(100)]
        c = _minimal_candidate(operators=ops)
        assert len(c.operators) == 100

    def test_expression_with_deep_nesting(self, engine):
        nested = "rank(" * 50 + "close" + ")" * 50
        report = engine.validate(nested)
        assert report is not None

    def test_very_long_hypothesis(self):
        long_h = "This hypothesis is " + "very " * 200 + "long."
        c = _minimal_candidate(hypothesis=long_h)
        assert len(c.hypothesis) > 1000


# ═══════════════════════════════════════════════════════════════════════
# Helper function boundaries
# ═══════════════════════════════════════════════════════════════════════

class TestHelperBoundaries:
    """Verify boundary behavior in scoring helper functions."""

    def test_item_zero_actual(self):
        result = item("test", 0.0, "higher", 1.0, True, 10)
        assert isinstance(result, dict)
        assert result["name"] == "test"

    def test_item_extreme_values(self):
        result = item("test_ext", 1e308, "lower", 0.0, True, 10)
        assert isinstance(result, dict)

    def test_check_zero_points(self):
        result = check("test", True, 0, "meaning")
        assert isinstance(result, dict)

    def test_check_negative_points(self):
        result = check("test", True, -5, "meaning")
        assert isinstance(result, dict)

    def test_decision_band_zero_score(self, scoring_cfg):
        band = decision_band(0.0, scoring=scoring_cfg)
        assert isinstance(band, str)

    def test_decision_band_negative_score(self, scoring_cfg):
        band = decision_band(-10.0, scoring=scoring_cfg)
        assert isinstance(band, str)

    def test_decision_band_very_high_score(self, scoring_cfg):
        band = decision_band(9999.0, scoring=scoring_cfg)
        assert isinstance(band, str)

    def test_estimate_score_confidence_empty_scorecard(self):
        result = estimate_score_confidence({})
        assert isinstance(result, dict)

    def test_estimate_score_confidence_minimal_scorecard(self):
        result = estimate_score_confidence({"total_score": 0, "passed": False})
        assert isinstance(result, dict)

    def test_candidate_from_dict_minimal(self):
        """from_dict with minimal required fields."""
        c2 = Candidate.from_dict({"alpha_id": "x", "expression": "rank(close)", "family": "f", "hypothesis": "h"})
        assert c2.alpha_id == "x"


# ═══════════════════════════════════════════════════════════════════════
# Expression engine boundary cases
# ═══════════════════════════════════════════════════════════════════════

class TestExpressionEngineBoundaries:
    """Boundary cases specific to ExpressionEngine and validate_expression."""

    def test_engine_validate_with_null_graceful(self, engine):
        try:
            report = engine.validate(None)
            assert report is not None
        except (TypeError, AttributeError):
            pass  # null rejection is also acceptable

    def test_engine_validate_with_non_string(self, engine):
        try:
            report = engine.validate(42)
            assert report is not None
        except (TypeError, AttributeError):
            pass

    def test_engine_validate_single_number(self, engine):
        report = engine.validate("42")
        assert report is not None

    def test_engine_validate_bare_field(self, engine):
        report = engine.validate("close")
        assert report is not None

    def test_module_validate_expression_simple(self):
        report = validate_expression("rank(close)")
        assert report is not None

    def test_complexity_score_for_simple_expression(self):
        report = validate_expression("rank(close)")
        if hasattr(report, "profile") and report.profile is not None:
            score = complexity_score(report.profile)
            assert isinstance(score, float)

    def test_bare_field_module_validate(self):
        report = validate_expression("close")
        assert report is not None

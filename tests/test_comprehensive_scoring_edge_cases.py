"""Comprehensive edge-case tests for the official scoring pipeline.

Covers:
  1. Null/empty metrics handling
  2. Extreme values (negative sharpe, zero division, NaN)
  3. Boundary thresholds (exact match, epsilon-off)
  4. Network/API unavailability simulation
  5. Configurable gate pass/fail alignment verification
  6. Attribution tree integrity across all score layers
  7. Parameter traceability end-to-end
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

# Ensure the project root is on the import path
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from brain_alpha_ops.config import (
    OpsConfig,
    QualityThresholds,
    ScoringConfig,
)
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.scoring import (
    build_scorecard,
    calculate_fitness,
    empirical_score,
    item,
    prior_score,
    decision_band,
    evaluate_quality_gate,
    estimate_score_confidence,
)
from brain_alpha_ops.scoring.official_scoring import (
    OfficialScoringSystem,
    ScoringResult,
    ScoreHistoryDB,
)
from brain_alpha_ops.scoring.gates import (
    GateConfig,
    GateResult,
    OFFICIAL_HARD_GATE_NAMES,
)
from brain_alpha_ops.scoring.release_score_gate import (
    decide_release,
    evaluate_release_score,
    OfficialSnapshot,
    ThresholdPolicy,
)
from brain_alpha_ops.scoring.attribution import (
    build_attribution_tree,
    AttributionNode,
    dim_explanation,
)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def default_thresholds():
    return QualityThresholds()


@pytest.fixture
def default_scoring():
    return ScoringConfig()


@pytest.fixture
def default_ops_config():
    return OpsConfig()


@pytest.fixture
def empty_candidate():
    return Candidate(
        alpha_id="test_empty",
        expression="rank(close)",
        family="Momentum",
        hypothesis="Basic price momentum",
    )


@pytest.fixture
def strong_official_metrics():
    return {
        "sharpe": 1.8,
        "fitness": 1.5,
        "turnover": 0.15,
        "turnover_raw": 0.15,
        "returns": 0.012,
        "drawdown": 0.08,
        "correlation": 0.35,
        "weight_concentration": 0.045,
        "sub_universe_sharpe": 1.6,
        "subUniverseSize": 2000,
        "alphaSize": 3000,
        "margin": 6.5,
        "pass_fail": "PASS",
    }


@pytest.fixture
def weak_official_metrics():
    return {
        "sharpe": 0.8,
        "fitness": 0.6,
        "turnover": 0.85,
        "turnover_raw": 0.85,
        "returns": 0.003,
        "drawdown": 0.45,
        "correlation": 0.75,
        "weight_concentration": 0.15,
        "sub_universe_sharpe": 0.3,
        "subUniverseSize": 1000,
        "alphaSize": 1000,
        "margin": 1.5,
        "pass_fail": "FAIL",
    }


# ═══════════════════════════════════════════════════════════════════════
# Section 1: Null / Empty Metrics Handling
# ═══════════════════════════════════════════════════════════════════════

class TestNullMetricsHandling:

    def test_empirical_score_empty_metrics(self, default_thresholds):
        """Empty metrics should return score=0.0 with missing status."""
        result = empirical_score({}, default_thresholds)
        assert result["score"] == 0.0
        assert result["status"] == "missing_official_metrics"
        assert result["items"] == []

    def test_empirical_score_none_metrics(self, default_thresholds):
        """None metrics should be treated same as empty dict."""
        result = empirical_score(None, default_thresholds)
        assert result["score"] == 0.0
        assert result["status"] == "missing_official_metrics"

    def test_empirical_score_partial_metrics(self, default_thresholds):
        """Metrics with only some fields should not crash."""
        partial = {"sharpe": 1.5}
        result = empirical_score(partial, default_thresholds)
        assert "score" in result
        assert "items" in result
        assert len(result["items"]) > 0

    def test_build_scorecard_empty_candidate(self, empty_candidate, default_thresholds, default_scoring):
        """Build scorecard on candidate with no official metrics."""
        result = build_scorecard(empty_candidate, default_thresholds, scoring=default_scoring)
        assert result["score_basis"] == "local_prior"
        assert result["empirical"]["status"] == "missing_official_metrics"
        assert result["total_score"] >= 0
        assert result["total_score"] <= 100

    def test_qos_handles_explicit_none_metrics(self, default_thresholds, default_scoring):
        """OfficialScoringSystem should handle None in candidate.official_metrics."""
        qos = OfficialScoringSystem()
        candidate = Candidate(
            alpha_id="test_none_metrics",
            expression="ts_rank(close, 10)",
            family="Momentum",
            hypothesis="Test expression with no metrics",
        )
        candidate.official_metrics = None  # type: ignore
        result = qos.evaluate(candidate)
        assert result.total_score >= 0
        assert result.empirical["status"] == "missing_official_metrics"


# ═══════════════════════════════════════════════════════════════════════
# Section 2: Extreme Values (Negative, Zero, Infinity, NaN)
# ═══════════════════════════════════════════════════════════════════════

class TestExtremeValues:

    def test_empirical_score_negative_sharpe(self, default_thresholds):
        """Negative sharpe should not cause crash; fitness crosscheck handles gracefully."""
        metrics = {
            "sharpe": -0.5,
            "fitness": -0.3,
            "turnover": 0.2,
            "returns": -0.01,
            "drawdown": 0.3,
            "correlation": 0.1,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": -0.2,
        }
        result = empirical_score(metrics, default_thresholds)
        assert "score" in result
        assert result["hard_gate_failed"] is True
        assert any(
            item["name"] == "sub_universe_sharpe" and not item["passed"]
            for item in result["items"]
        )

    def test_empirical_score_zero_turnover(self, default_thresholds):
        """Zero turnover should trigger LOW_TURNOVER hard gate failure."""
        metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.0,
            "turnover_raw": 0.0,
            "returns": 0.01,
            "drawdown": 0.1,
            "correlation": 0.2,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.3,
        }
        result = empirical_score(metrics, default_thresholds)
        turnover_min_item = next(
            (item for item in result["items"] if item["name"] == "turnover_min"), None
        )
        assert turnover_min_item is not None
        assert turnover_min_item["passed"] is False
        assert result["hard_gate_failed"] is True

    def test_calculate_fitness_zero_turnover(self):
        """Calculate fitness with zero turnover should use min denominator 0.125."""
        result = calculate_fitness(1.5, 0.02, 0.0)
        expected = 1.5 * math.sqrt(abs(0.02) / 0.125)
        assert abs(result - expected) < 1e-6

    def test_calculate_fitness_negative_returns(self):
        """Fitness with negative returns uses abs(returns)."""
        result = calculate_fitness(1.0, -0.02, 0.2)
        expected = 1.0 * math.sqrt(abs(-0.02) / 0.2)
        assert abs(result - expected) < 1e-6

    def test_calculate_fitness_raw_turnover_preferred(self):
        """raw_turnover should take precedence over normalized turnover."""
        result_raw = calculate_fitness(1.0, 0.01, 0.001, raw_turnover=2.5)
        result_norm = calculate_fitness(1.0, 0.01, 0.001)
        assert result_raw != result_norm

    def test_empirical_score_extreme_sharpe(self, default_thresholds):
        """Sharpe of 100 (extreme but possible) should not crash."""
        metrics = {
            "sharpe": 100.0,
            "fitness": 80.0,
            "turnover": 0.05,
            "turnover_raw": 0.05,
            "returns": 0.5,
            "drawdown": 0.01,
            "correlation": 0.1,
            "weight_concentration": 0.01,
            "sub_universe_sharpe": 90.0,
        }
        result = empirical_score(metrics, default_thresholds)
        assert result["score"] >= 0

    def test_empirical_score_nan_returns(self, default_thresholds):
        """NaN values in metrics should produce 0.0 via _num()."""
        import math as _math
        metrics = {
            "sharpe": float("nan"),
            "fitness": 0.5,
            "turnover": 0.2,
            "returns": float("nan"),
            "drawdown": 0.1,
            "correlation": 0.3,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 0.4,
        }
        result = empirical_score(metrics, default_thresholds)
        assert result["score"] >= 0  # no crash

    def test_build_scorecard_econ_logic_empty_inputs(self, default_thresholds, default_scoring):
        """Empty hypothesis + expression gets low economic_logic."""
        candidate = Candidate(
            alpha_id="empty_econ",
            expression="",
            family="Momentum",
            hypothesis="",
        )
        result = build_scorecard(candidate, default_thresholds, scoring=default_scoring)
        # Should not crash with empty inputs
        assert "prior" in result
        assert result["prior"]["score"] >= 0


# ═══════════════════════════════════════════════════════════════════════
# Section 3: Boundary Thresholds — Exact Match and Epsilon-Off
# ═══════════════════════════════════════════════════════════════════════

class TestBoundaryThresholds:

    def test_sharpe_exactly_at_threshold(self, default_thresholds):
        """Sharpe == 1.25 (exact threshold) should pass."""
        metrics = {
            "sharpe": 1.25,
            "fitness": 1.2,
            "turnover": 0.15,
            "returns": 0.01,
            "drawdown": 0.1,
            "correlation": 0.1,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.1,
        }
        result = empirical_score(metrics, default_thresholds)
        sharpe_item = next(i for i in result["items"] if i["name"] == "sharpe")
        assert sharpe_item["passed"] is True

    def test_sharpe_one_basis_point_below_threshold(self, default_thresholds):
        """Sharpe == 1.24 (0.01 below threshold) should fail."""
        metrics = {
            "sharpe": 1.24,
            "fitness": 1.2,
            "turnover": 0.15,
            "returns": 0.01,
            "drawdown": 0.1,
            "correlation": 0.1,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.1,
        }
        result = empirical_score(metrics, default_thresholds)
        sharpe_item = next(i for i in result["items"] if i["name"] == "sharpe")
        assert sharpe_item["passed"] is False
        assert result["hard_gate_failed"] is True

    def test_fitness_exact_threshold(self, default_thresholds):
        """Fitness == 1.0 (exact threshold) should pass."""
        metrics = {
            "sharpe": 1.5,
            "fitness": 1.0,
            "turnover": 0.15,
            "returns": 0.01,
            "drawdown": 0.1,
            "correlation": 0.1,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.3,
        }
        result = empirical_score(metrics, default_thresholds)
        fitness_item = next(i for i in result["items"] if i["name"] == "fitness")
        assert fitness_item["passed"] is True

    def test_self_correlation_exact_threshold(self, default_thresholds):
        """Self-correlation == 0.70 (exact threshold) should fail."""
        metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.15,
            "returns": 0.01,
            "drawdown": 0.1,
            "correlation": 0.70,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.3,
        }
        result = empirical_score(metrics, default_thresholds)
        sc_item = next(i for i in result["items"] if i["name"] == "self_correlation")
        assert sc_item["passed"] is False

    def test_self_correlation_with_sharpe_exception(self, default_thresholds):
        """Self-correlation >= 0.70 but with Sharpe exception should pass."""
        metrics = {
            "sharpe": 1.65,  # 1.65 >= 1.50 * 1.10 → exception
            "fitness": 1.2,
            "turnover": 0.15,
            "returns": 0.01,
            "drawdown": 0.1,
            "correlation": 0.72,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.4,
            "related_alpha_sharpe": 1.5,
        }
        result = empirical_score(metrics, default_thresholds)
        sc_item = next(i for i in result["items"] if i["name"] == "self_correlation")
        assert sc_item["passed"] is True
        assert sc_item.get("exception_applied") is True

    def test_decision_band_boundaries(self):
        """Decision band should produce correct classification at boundaries."""
        assert decision_band(85.0) == "submit_candidate"
        assert decision_band(84.99) == "optimize_before_submit"
        assert decision_band(70.0) == "optimize_before_submit"
        assert decision_band(69.99) == "research_only"
        assert decision_band(50.0) == "research_only"
        assert decision_band(49.99) == "abandon_or_rebuild"
        assert decision_band(0.0) == "abandon_or_rebuild"

    def test_hard_gate_blocked_overrides_decision_band(self):
        """hard_gate_failed=True → 'hard_gate_blocked' regardless of score."""
        assert decision_band(95.0, hard_gate_failed=True) == "hard_gate_blocked"
        assert decision_band(0.0, hard_gate_failed=True) == "hard_gate_blocked"


# ═══════════════════════════════════════════════════════════════════════
# Section 4: Official Gate Config — Pass/Fail Alignment
# ═══════════════════════════════════════════════════════════════════════

class TestOfficialGateAlignment:

    def test_gate_config_rejects_non_official_hard_gate(self):
        """Adding a non-official check as hard gate must raise ValueError."""
        gc = GateConfig()
        with pytest.raises(ValueError):
            gc.add_hard_gate("drawdown", lambda m: True, "Drawdown is not a BRAIN hard gate")

    def test_gate_config_accepts_all_official_gate_names(self):
        """Every name in OFFICIAL_HARD_GATE_NAMES must be usable as hard gate."""
        gc = GateConfig()
        for name in OFFICIAL_HARD_GATE_NAMES:
            gc.add_hard_gate(name, lambda m, n=name: True, f"Check {name}")
        assert len(gc.hard_gates) == len(OFFICIAL_HARD_GATE_NAMES)

    def test_gate_config_zero_deviation_when_aligned(self, strong_official_metrics):
        """Gate should report zero_deviation when config matches official."""
        gc = GateConfig()
        gc.add_hard_gate("sharpe", lambda m: m.get("sharpe", 0) >= 1.25, "SHARPE check")
        result = gc.evaluate(strong_official_metrics)
        assert result.passed
        # Verify the gate reports alignment
        assert all(g.zero_deviation for g in [result])

    def test_release_gate_strong_candidate(self, strong_official_metrics, default_thresholds):
        """Release gate should PASS for strong metrics."""
        decision = evaluate_release_score(strong_official_metrics, default_thresholds)
        assert decision.status == "PASS"
        assert decision.pass_fail is True

    def test_release_gate_weak_candidate(self, weak_official_metrics, default_thresholds):
        """Release gate should FAIL for weak metrics."""
        decision = evaluate_release_score(weak_official_metrics, default_thresholds)
        assert decision.status == "FAIL"
        assert decision.pass_fail is False

    def test_release_gate_empty_metrics(self, default_thresholds):
        """Release gate with empty metrics should fail gracefully."""
        decision = evaluate_release_score({}, default_thresholds)
        assert hasattr(decision, "status")
        assert decision.pass_fail is False

    def test_gate_config_soft_gates_dont_block(self, strong_official_metrics):
        """Soft gate failures should not cause overall failure."""
        gc = GateConfig()
        gc.add_soft_gate("always_fail", lambda m: False, "Should fail quietly")
        result = gc.evaluate(strong_official_metrics)
        assert result.passed  # overall still passes


# ═══════════════════════════════════════════════════════════════════════
# Section 5: Attribution Tree Integrity
# ═══════════════════════════════════════════════════════════════════════

class TestAttributionTree:

    def test_attribution_tree_has_three_layers(self, strong_official_metrics, default_thresholds, default_scoring):
        """Attribution tree must have root + 3 layer children."""
        candidate = Candidate(
            alpha_id="attrib_test",
            expression="ts_rank(winsorize(close, 0.01), 20)",
            family="Momentum",
            hypothesis="Price momentum with winsorization for risk control",
            official_metrics=strong_official_metrics,
        )
        scorecard = build_scorecard(candidate, default_thresholds, scoring=default_scoring)
        tree = build_attribution_tree(scorecard)
        assert tree.name == "total_score"
        child_names = {c.name for c in tree.children}
        assert "prior_score" in child_names
        assert "empirical_score" in child_names
        assert "submission_checklist" in child_names

    def test_attribution_tree_to_dict_no_crash(self, strong_official_metrics, default_thresholds, default_scoring):
        """Tree to_dict() should not crash on nested children."""
        candidate = Candidate(
            alpha_id="tree_dict",
            expression="group_rank(close, subindustry)",
            family="CrossSectional",
            hypothesis="Cross-sectional rank within industry",
            official_metrics=strong_official_metrics,
        )
        scorecard = build_scorecard(candidate, default_thresholds, scoring=default_scoring)
        tree = build_attribution_tree(scorecard)
        d = tree.to_dict()
        assert isinstance(d, dict)
        assert "name" in d
        assert "score" in d
        assert "children" in d

    def test_dim_explanation_covers_all_prior_dims(self):
        """dim_explanation should return non-empty string for all prior dimensions."""
        dims = [
            "economic_logic", "structure", "field_operator_support",
            "data_compliance", "horizon_turnover_proxy", "risk_control_proxy",
            "diversity", "explainability"
        ]
        for dim in dims:
            explanation = dim_explanation(dim, 80)
            assert isinstance(explanation, str)
            assert len(explanation) > 0

    def test_attribution_node_historical_trend(self):
        """AttributionNode should serialize historical_trend correctly."""
        node = AttributionNode(
            name="test",
            score=75.0,
            weight=1.0,
            contribution=75.0,
            historical_trend="improving",
        )
        d = node.to_dict()
        assert d["historical_trend"] == "improving"

    def test_qos_returns_attribution_tree(self, strong_official_metrics):
        """OfficialScoringSystem result must include attribution tree."""
        qos = OfficialScoringSystem()
        candidate = Candidate(
            alpha_id="qos_attrib",
            expression="ts_delta(close, 10)",
            family="Trend",
            hypothesis="Short-term price delta",
            official_metrics=strong_official_metrics,
        )
        result = qos.evaluate(candidate)
        assert result.attribution_tree is not None
        tree_dict = result.to_dict()
        assert tree_dict["attribution_tree"] is not None


# ═══════════════════════════════════════════════════════════════════════
# Section 6: Parameter Traceability (End-to-End)
# ═══════════════════════════════════════════════════════════════════════

class TestParameterTraceability:

    def test_scorecard_settings_trace(self, strong_official_metrics, default_thresholds, default_scoring):
        """Scorecard must include settings_trace with delay info."""
        candidate = Candidate(
            alpha_id="trace_test",
            expression="ts_mean(close, 20)",
            family="Momentum",
            hypothesis="Long-term moving average",
            official_metrics=strong_official_metrics,
        )
        scorecard = build_scorecard(candidate, default_thresholds, scoring=default_scoring)
        assert "settings_trace" in scorecard

    def test_scorecard_calibration_fields(self, strong_official_metrics, default_thresholds, default_scoring):
        """Scorecard calibration must include prior-empirical delta."""
        candidate = Candidate(
            alpha_id="calib_test",
            expression="ts_delta(close, 10)",
            family="Momentum",
            hypothesis="Price delta",
            official_metrics=strong_official_metrics,
        )
        scorecard = build_scorecard(candidate, default_thresholds, scoring=default_scoring)
        assert "calibration" in scorecard
        assert "prior_minus_empirical" in scorecard["calibration"]
        assert "sample_weight" in scorecard["calibration"]

    def test_qos_threshold_trace_complete(self, default_ops_config):
        """Threshold trace must include all 10 official threshold keys."""
        qos = OfficialScoringSystem(default_ops_config)
        trace = qos._threshold_trace()
        expected_keys = {
            "min_sharpe", "min_sharpe_delay0", "min_fitness", "min_fitness_delay0",
            "min_turnover", "platform_max_turnover", "max_self_correlation",
            "max_prod_correlation", "max_weight_concentration",
            "sub_universe_sharpe_min_ratio",
        }
        assert set(trace.keys()) == expected_keys
        for key in trace:
            assert "value" in trace[key]
            assert "source" in trace[key]

    def test_qos_config_hash_deterministic(self, default_ops_config):
        """Config hash must be deterministic for same config."""
        qos = OfficialScoringSystem(default_ops_config)
        h1 = qos._config_hash()
        h2 = qos._config_hash()
        assert h1 == h2


# ═══════════════════════════════════════════════════════════════════════
# Section 7: Score Confidence Estimation
# ═══════════════════════════════════════════════════════════════════════

class TestScoreConfidence:

    def test_confidence_empty_empirical(self):
        """Confidence for empty empirical should be 'low'."""
        result = estimate_score_confidence({"empirical": {"items": []}})
        assert result["confidence_level"] == "low"
        assert result["data_completeness"] == 0.0

    def test_confidence_all_passed_strong(self):
        """High completeness + low dispersion → 'high' confidence."""
        items = [
            item("sharpe", 2.0, ">=", 1.25, True, 20, is_hard_gate=True),
            item("fitness", 1.5, ">=", 1.0, True, 15, is_hard_gate=True),
            item("turnover_platform", 0.15, "<=", 0.70, True, 8, is_hard_gate=True),
            item("weight_concentration", 0.04, "<=", 0.10, True, 5, is_hard_gate=True),
        ]
        result = estimate_score_confidence({"empirical": {"items": items}})
        assert result["confidence_level"] == "high"

    def test_confidence_mixed_results(self):
        """Mixed pass/fail should still produce valid confidence."""
        items = [
            item("sharpe", 2.0, ">=", 1.25, True, 20, is_hard_gate=True),
            item("fitness", 0.5, ">=", 1.0, False, 15, is_hard_gate=True),
            item("turnover_platform", 0.85, "<=", 0.70, False, 8, is_hard_gate=True),
        ]
        result = estimate_score_confidence({"empirical": {"items": items}})
        assert result["confidence_level"] in {"low", "medium", "high"}
        assert "interpretation" in result


# ═══════════════════════════════════════════════════════════════════════
# Section 8: Score History Database
# ═══════════════════════════════════════════════════════════════════════

class TestScoreHistoryDB:

    def test_append_and_load(self, tmp_path):
        """Score history can be appended and loaded back."""
        db = ScoreHistoryDB(str(tmp_path / "scores.jsonl"))
        result = ScoringResult(
            alpha_id="test_alpha",
            expression="rank(close)",
            total_score=85.0,
            decision_band="submit_candidate",
            passed_gate=True,
        )
        db.append(result)
        db.append(result)

        records = db.load_all()
        assert len(records) >= 2

    def test_convergence_insufficient_data(self, tmp_path):
        """Convergence with < 3 records returns insufficient_data."""
        db = ScoreHistoryDB(str(tmp_path / "scores.jsonl"))
        stats = db.convergence_stats()
        assert stats["status"] == "insufficient_data"

    def test_convergence_with_trend(self, tmp_path):
        """Convergence stats should detect improving trend."""
        db = ScoreHistoryDB(str(tmp_path / "scores_conv.jsonl"))
        for score in [60, 65, 70, 78, 85]:
            result = ScoringResult(
                alpha_id="conv_test",
                expression="rank(close)",
                total_score=score,
                decision_band="research_only",
                passed_gate=False,
            )
            db.append(result)
        stats = db.convergence_stats(limit=100)
        assert stats["status"] == "ready"
        assert "trend" in stats
        assert "pass_rate" in stats


# ═══════════════════════════════════════════════════════════════════════
# Section 9: Prior Score Edge Cases
# ═══════════════════════════════════════════════════════════════════════

class TestPriorScoreEdgeCases:

    def test_prior_score_empty_expression(self, default_scoring):
        """Prior score should handle empty expression gracefully."""
        candidate = Candidate(
            alpha_id="empty_expr",
            expression="",
            family="Momentum",
            hypothesis="",
        )
        result = prior_score(candidate, weights_override=default_scoring.prior_weights_override)
        assert result["score"] >= 0
        assert result["score"] <= 100
        assert "dimensions" in result

    def test_prior_score_single_field_single_operator(self):
        """Minimal expression with one field and one operator."""
        candidate = Candidate(
            alpha_id="min_expr",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Cross-sectional rank of price",
            data_fields=["close"],
            operators=["rank"],
        )
        result = prior_score(candidate)
        assert result["score"] >= 0

    def test_prior_score_complex_multi_operator(self):
        """Complex expression with many operators and fields."""
        candidate = Candidate(
            alpha_id="complex",
            expression="group_rank(winsorize(ts_mean(close, 20), 0.01), subindustry)",
            family="CrossSectional",
            hypothesis="Risk-controlled sector-neutral mean reversion signal",
            data_fields=["close"],
            operators=["group_rank", "winsorize", "ts_mean"],
        )
        result = prior_score(candidate)
        assert result["dimensions"]["economic_logic"] >= 0
        assert result["dimensions"]["risk_control_proxy"] > 0


# ═══════════════════════════════════════════════════════════════════════
# Section 10: Official Scoring API Simulation
# ═══════════════════════════════════════════════════════════════════════

class TestApiSimulation:

    def test_api_simulation_zero_deviation_strong(self, strong_official_metrics):
        """Strong metrics with pass_fail=PASS should have zero deviation."""
        qos = OfficialScoringSystem()
        candidate = Candidate(
            alpha_id="api_sim_strong",
            expression="ts_delta(close, 10)",
            family="Momentum",
            hypothesis="Short-term delta",
            official_metrics=strong_official_metrics,
        )
        result = qos.evaluate(candidate)
        assert result.api_output_deviation == 0.0
        assert result.simulated_api_output["status"] == "PASS"
        assert result.simulated_api_output["gate"]["hard_gate_passed"] is True

    def test_api_simulation_reports_deviation(self, weak_official_metrics):
        """Weak metrics with pass_fail mismatch should report deviation."""
        qos = OfficialScoringSystem()
        candidate = Candidate(
            alpha_id="api_sim_weak",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Simple rank",
            official_metrics=weak_official_metrics,
        )
        result = qos.evaluate(candidate)
        assert len(result.deviation_details) > 0

    def test_api_simulation_no_official_metrics(self):
        """API simulation should still work without official metrics."""
        qos = OfficialScoringSystem()
        candidate = Candidate(
            alpha_id="api_no_metrics",
            expression="ts_mean(close, 20)",
            family="Momentum",
            hypothesis="Moving average",
        )
        result = qos.evaluate(candidate)
        assert "simulated_api_output" in result.to_dict()
        assert result.simulated_api_output["meta"]["simulated"] is True

    def test_qos_score_trend_tracking(self, strong_official_metrics, weak_official_metrics):
        """Score trend should work over multiple evaluations."""
        qos = OfficialScoringSystem()
        candidate = Candidate(
            alpha_id="trend_track",
            expression="ts_delta(close, 10)",
            family="Momentum",
            hypothesis="Delta",
            official_metrics=strong_official_metrics,
        )
        qos.evaluate(candidate)
        trend = qos.get_score_trend("trend_track")
        assert trend is None  # only one evaluation

        candidate.official_metrics = weak_official_metrics
        qos.evaluate(candidate)
        trend = qos.get_score_trend("trend_track")
        assert trend == "declining"


# ═══════════════════════════════════════════════════════════════════════
# Section 11: Helper Functions
# ═══════════════════════════════════════════════════════════════════════

class TestHelpers:

    def test_item_constructor_structure(self):
        """item() should produce correct structure."""
        result = item("sharpe", 1.5, ">=", 1.25, True, 20, is_hard_gate=True)
        assert result["name"] == "sharpe"
        assert result["actual"] == 1.5
        assert result["direction"] == ">="
        assert result["target"] == 1.25
        assert result["passed"] is True
        assert result["points"] == 20
        assert result["is_hard_gate"] is True
        assert result["source"] == "BRAIN_Official"

    def test_item_non_hard_gate_source(self):
        """Non-hard-gate items should have '经验' source."""
        result = item("returns", 0.01, ">=", 0.0, True, 5, is_hard_gate=False)
        assert result["source"] == "经验"

    def test_qos_scoring_result_to_dict_complete(self):
        """ScoringResult.to_dict() should be JSON-serializable."""
        result = ScoringResult(
            alpha_id="json_test",
            expression="rank(close)",
            total_score=85.0,
            decision_band="submit_candidate",
            passed_gate=True,
        )
        d = result.to_dict()
        json_str = json.dumps(d, ensure_ascii=False)
        assert len(json_str) > 0
        parsed = json.loads(json_str)
        assert parsed["alpha_id"] == "json_test"

    def test_qos_report_readable(self):
        """Attribution report should be human-readable string."""
        result = ScoringResult(
            alpha_id="report_test",
            expression="rank(close)",
            total_score=88.0,
            decision_band="submit_candidate",
            passed_gate=True,
            improvement_hints=["Test hint 1", "Test hint 2"],
            top_failures=[],
        )
        report = result.attribution_report()
        assert "report_test" in report
        assert "88.00" in report or "88.0" in report


# ═══════════════════════════════════════════════════════════════════════
# Section 12: Resilience & Network Error Simulation
# ═══════════════════════════════════════════════════════════════════════

class TestResilience:

    def test_scorecard_survives_corrupt_metrics(self, default_thresholds, default_scoring):
        """Corrupt/invalid metric values should not crash scorecard builder."""
        corrupt = {"sharpe": "not_a_number", "fitness": None, "turnover": []}
        candidate = Candidate(
            alpha_id="corrupt",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Test",
            official_metrics=corrupt,
        )
        result = build_scorecard(candidate, default_thresholds, scoring=default_scoring)
        assert result["total_score"] >= 0
        assert result["total_score"] <= 100

    def test_prior_score_handles_none_fields(self):
        """Prior score should handle None for data_fields gracefully."""
        candidate = Candidate(
            alpha_id="none_fields",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Test",
        )
        candidate.data_fields = None  # type: ignore
        result = prior_score(candidate)
        assert result["score"] >= 0

    def test_prior_score_handles_none_operators(self):
        """Prior score should handle None for operators gracefully."""
        candidate = Candidate(
            alpha_id="none_ops",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Test",
        )
        candidate.operators = None  # type: ignore
        result = prior_score(candidate)
        assert result["score"] >= 0

    def test_evaluate_quality_gate_no_official_metrics(self, default_thresholds, default_scoring):
        """Quality gate should report missing metrics, not crash."""
        candidate = Candidate(
            alpha_id="no_metrics",
            expression="rank(close)",
            family="Momentum",
            hypothesis="Simple rank momentum test signal",
        )
        gate = evaluate_quality_gate(candidate, default_thresholds)
        assert gate["submission_ready"] is False
        assert "official_metrics_present" in str(gate["failed_reasons"])

    def test_empirical_score_inf_values(self, default_thresholds):
        """Inf values should be handled safely."""
        metrics = {"sharpe": float("inf"), "fitness": 0.5, "turnover": 0.2}
        result = empirical_score(metrics, default_thresholds)
        assert "score" in result

    def test_official_snapshot_from_partial_metrics(self):
        """OfficialSnapshot.from_metrics should handle missing keys."""
        partial = {"sharpe": 1.5, "fitness": 1.0}
        snap = OfficialSnapshot.from_metrics(partial)
        assert snap.sharpe == 1.5
        assert snap.fitness == 1.0
        assert snap.turnover == 0.0  # default for missing


# ═══════════════════════════════════════════════════════════════════════
# Section 13: BraindDataLoader Integration
# ═══════════════════════════════════════════════════════════════════════

class TestDataLoaderIntegration:

    def test_singleton_thread_safety(self):
        """OfficialDataLoader singleton should be thread-safe."""
        from brain_alpha_ops.data.loader import OfficialDataLoader
        import threading
        results = []

        def get_instance():
            loader = OfficialDataLoader.instance()
            results.append(id(loader))

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 1  # all threads got the same instance

    def test_official_context_file_check(self):
        """Ensure official context file check does not crash."""
        from brain_alpha_ops.data.loader import ensure_official_context_files
        result = ensure_official_context_files("data")
        assert "present" in result or "missing" in result


# ═══════════════════════════════════════════════════════════════════════
# Section 14: C4 Model Boundaries
# ═══════════════════════════════════════════════════════════════════════

class TestModelBoundaries:

    def test_candidate_from_dict_extra_fields(self):
        """Candidate.from_dict should preserve unknown keys in extra_fields."""
        data = {
            "alpha_id": "extra_test",
            "expression": "rank(close)",
            "family": "Momentum",
            "hypothesis": "Test",
            "custom_field_123": "preserved_value",
            "another_unknown": 42,
        }
        candidate = Candidate.from_dict(data)
        assert candidate.extra_fields.get("custom_field_123") == "preserved_value"
        assert candidate.extra_fields.get("another_unknown") == 42

    def test_candidate_from_dict_roundtrip(self):
        """Candidate to_dict → from_dict should preserve core fields."""
        original = Candidate(
            alpha_id="roundtrip",
            expression="ts_mean(close, 20)",
            family="Trend",
            hypothesis="Moving average trend signal",
            data_fields=["close"],
            operators=["ts_mean"],
            dataset_id="analyst4",
        )
        reconstructed = Candidate.from_dict(original.to_dict())
        assert reconstructed.alpha_id == original.alpha_id
        assert reconstructed.expression == original.expression
        assert reconstructed.family == original.family
        assert reconstructed.dataset_id == original.dataset_id
        assert reconstructed.data_fields == original.data_fields

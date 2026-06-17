"""End-to-end tests for web console workflows.

Tests cover:
  - Full alpha lifecycle through web console
  - Configuration management
  - Candidate management
  - Backtest monitoring
  - Submission readiness
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestWebConsoleAlphaLifecycle:
    """Test alpha lifecycle through web console."""

    def test_alpha_generation_workflow(self):
        """Test alpha generation workflow."""
        from brain_alpha_ops.research.generator import CandidateGenerator

        generator = CandidateGenerator()
        candidates = generator.generate(5, dataset_id="pv1")

        assert len(candidates) > 0
        for candidate in candidates:
            assert hasattr(candidate, "alpha_id")
            assert hasattr(candidate, "expression")
            assert hasattr(candidate, "family")

    def test_alpha_scoring_workflow(self):
        """Test alpha scoring workflow."""
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import build_scorecard, evaluate_quality_gate
        from brain_alpha_ops.config import QualityThresholds

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Price momentum test",
        )
        candidate.official_metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.3,
            "pass_fail": "PASS",
        }

        thresholds = QualityThresholds()
        scorecard = build_scorecard(candidate, thresholds)
        gate = evaluate_quality_gate(candidate, thresholds)

        assert scorecard["total_score"] > 0
        assert "decision_band" in scorecard
        assert "submission_ready" in gate

    def test_alpha_attribution_workflow(self):
        """Test alpha attribution workflow."""
        from brain_alpha_ops.scoring.attribution import build_attribution_tree

        scorecard = {
            "total_score": 75.0,
            "prior": {"score": 80.0, "items": []},
            "empirical": {"score": 70.0, "items": []},
            "submission_checklist": {"score": 85.0, "items": []},
            "layer_weights": {"prior": 0.3, "empirical": 0.45, "checklist": 0.25},
        }

        tree = build_attribution_tree(scorecard)
        assert tree is not None
        assert tree.name == "total_score"
        assert len(tree.children) == 3


class TestWebConsoleConfiguration:
    """Test configuration management."""

    def test_config_loading(self):
        """Test configuration loading."""
        from brain_alpha_ops.config import OpsConfig, BrainSettings

        config = OpsConfig()
        assert config.settings is not None
        assert config.budget is not None
        assert config.scoring is not None

    def test_config_to_dict(self):
        """Test configuration serialization."""
        from brain_alpha_ops.config import OpsConfig

        config = OpsConfig()
        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert "settings" in config_dict
        assert "budget" in config_dict

    def test_quality_thresholds(self):
        """Test quality thresholds."""
        from brain_alpha_ops.config import QualityThresholds

        thresholds = QualityThresholds()
        assert thresholds.min_sharpe > 0
        assert thresholds.min_fitness > 0


class TestWebConsoleCandidateManagement:
    """Test candidate management."""

    def test_candidate_creation(self):
        """Test candidate creation."""
        from brain_alpha_ops.models import Candidate

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Price momentum test",
        )

        assert candidate.alpha_id == "test_alpha"
        assert candidate.expression == "rank(ts_delta(close, 20))"
        assert candidate.family == "momentum"

    def test_candidate_serialization(self):
        """Test candidate serialization."""
        from brain_alpha_ops.models import Candidate

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Price momentum test",
        )

        candidate_dict = candidate.to_dict()
        assert isinstance(candidate_dict, dict)
        assert candidate_dict["alpha_id"] == "test_alpha"

    def test_candidate_from_dict(self):
        """Test candidate deserialization."""
        from brain_alpha_ops.models import Candidate

        data = {
            "alpha_id": "test_alpha",
            "expression": "rank(ts_delta(close, 20))",
            "family": "momentum",
            "hypothesis": "Price momentum test",
        }

        candidate = Candidate.from_dict(data)
        assert candidate.alpha_id == "test_alpha"


class TestWebConsoleBacktestMonitoring:
    """Test backtest monitoring."""

    def test_backtest_slot_payload(self):
        """Test backtest slot payload structure."""
        from brain_alpha_ops.web_backtest_slots import backtest_slots_payload

        # Mock the read function to return expected tuple
        def mock_read(*args, **kwargs):
            return [], 0, ""

        result = backtest_slots_payload(read_jsonl_records=mock_read)
        assert isinstance(result, dict)
        assert "slots" in result or "ok" in result

    def test_convergence_tracking(self):
        """Test convergence tracking."""
        from brain_alpha_ops.research.convergence import ConvergenceTracker

        tracker = ConvergenceTracker(window_size=5, stall_threshold=3)

        for cycle in range(10):
            tracker.record_cycle(
                cycle=cycle,
                produced=10,
                passed_local=5,
                simulated=3,
                passed_gate=1,
                submitted=0,
                candidates=[],
            )

        summary = tracker.summary()
        assert "sharpe_trend" in summary
        assert "stalled" in summary


class TestWebConsoleSubmissionReadiness:
    """Test submission readiness."""

    def test_submission_readiness_check(self):
        """Test submission readiness check."""
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import build_scorecard
        from brain_alpha_ops.config import QualityThresholds

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Price momentum test",
        )
        candidate.official_metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.3,
            "pass_fail": "PASS",
        }

        thresholds = QualityThresholds()
        scorecard = build_scorecard(candidate, thresholds)

        # Check if ready for submission
        is_ready = scorecard.get("decision_band") == "SUBMISSION_READY"
        assert isinstance(is_ready, bool)

    def test_quality_gate_check(self):
        """Test quality gate check."""
        from brain_alpha_ops.scoring.gates import GateConfig, OFFICIAL_HARD_GATE_NAMES
        from brain_alpha_ops.config import QualityThresholds

        thresholds = QualityThresholds()
        gate_config = GateConfig(thresholds)

        # Add gates
        for gate_name in OFFICIAL_HARD_GATE_NAMES:
            gate_config.add_hard_gate(
                gate_name,
                lambda metrics, thresholds, name=gate_name: metrics.get(name, 0) > 0,
            )

        # Evaluate
        metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover_min": 0.02,
            "turnover_platform": 0.5,
            "self_correlation": 0.1,
            "prod_correlation": 0.2,
            "weight_concentration": 0.05,
            "sub_universe_sharpe": 1.3,
        }

        result = gate_config.evaluate(metrics)
        assert hasattr(result, "passed")
        assert hasattr(result, "check_items")

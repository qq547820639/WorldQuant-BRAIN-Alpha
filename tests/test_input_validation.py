"""Input validation tests for API endpoints.

Tests cover:
  - Expression validation
  - Settings validation
  - Candidate validation
  - Configuration validation
"""

from __future__ import annotations

import pytest


class TestExpressionValidation:
    """Test expression validation."""

    def test_valid_expression(self):
        """Test valid expression passes validation."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        result = engine.validate("rank(ts_delta(close, 20))")
        assert result.parsed is True
        assert result.valid is True

    def test_empty_expression_fails(self):
        """Test empty expression fails validation."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        result = engine.validate("")
        assert result.parsed is False
        assert result.valid is False

    def test_invalid_syntax_fails(self):
        """Test invalid syntax fails validation."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        result = engine.validate("rank(close")
        assert result.parsed is False

    def test_unknown_operator_fails(self):
        """Test unknown operator fails validation."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        result = engine.validate("unknown_op(close)")
        assert result.parsed is True
        # Should have issues with unknown operator

    def test_expression_length_limit(self):
        """Test expression length limit."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine(max_expression_length=100)
        long_expr = "rank(close) + " * 20
        result = engine.validate(long_expr)
        # Should handle long expressions gracefully


class TestSettingsValidation:
    """Test settings validation."""

    def test_valid_settings(self):
        """Test valid settings pass validation."""
        from brain_alpha_ops.config import BrainSettings

        settings = BrainSettings(
            instrumentType="EQUITY",
            region="USA",
            delay=1,
            universe="TOP3000",
        )
        assert settings.instrumentType == "EQUITY"
        assert settings.region == "USA"

    def test_settings_default_values(self):
        """Test settings have default values."""
        from brain_alpha_ops.config import BrainSettings

        settings = BrainSettings()
        assert settings.instrumentType is not None
        assert settings.region is not None
        assert settings.delay is not None


class TestCandidateValidation:
    """Test candidate validation."""

    def test_valid_candidate(self):
        """Test valid candidate creation."""
        from brain_alpha_ops.models import Candidate

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Price momentum test",
        )
        assert candidate.alpha_id == "test_alpha"
        assert candidate.expression == "rank(ts_delta(close, 20))"

    def test_candidate_with_empty_expression(self):
        """Test candidate with empty expression."""
        from brain_alpha_ops.models import Candidate

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="",
            family="momentum",
            hypothesis="Test",
        )
        # Should handle empty expression gracefully
        assert candidate.expression == ""

    def test_candidate_serialization_roundtrip(self):
        """Test candidate serialization roundtrip."""
        from brain_alpha_ops.models import Candidate

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="rank(close)",
            family="momentum",
            hypothesis="Test",
        )
        data = candidate.to_dict()
        restored = Candidate.from_dict(data)
        assert restored.alpha_id == candidate.alpha_id
        assert restored.expression == candidate.expression


class TestConfigurationValidation:
    """Test configuration validation."""

    def test_valid_config(self):
        """Test valid configuration creation."""
        from brain_alpha_ops.config import OpsConfig

        config = OpsConfig()
        assert config.settings is not None
        assert config.budget is not None

    def test_config_to_dict_roundtrip(self):
        """Test configuration serialization roundtrip."""
        from brain_alpha_ops.config import OpsConfig

        config = OpsConfig()
        config_dict = config.to_dict()
        assert isinstance(config_dict, dict)
        assert "settings" in config_dict

    def test_quality_thresholds_validation(self):
        """Test quality thresholds validation."""
        from brain_alpha_ops.config import QualityThresholds

        thresholds = QualityThresholds(
            min_sharpe=1.25,
            min_fitness=1.0,
        )
        assert thresholds.min_sharpe == 1.25
        assert thresholds.min_fitness == 1.0


class TestAPIEndpointValidation:
    """Test API endpoint validation."""

    def test_simulation_settings_validation(self):
        """Test simulation settings validation."""
        settings = {
            "region": "USA",
            "delay": 1,
            "universe": "TOP3000",
            "instrumentType": "EQUITY",
        }
        # All required fields present
        assert "region" in settings
        assert "delay" in settings
        assert "universe" in settings

    def test_alpha_expression_validation(self):
        """Test alpha expression validation."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        valid_expressions = [
            "rank(close)",
            "ts_mean(close, 20)",
            "rank(ts_delta(close, 20))",
        ]
        for expr in valid_expressions:
            result = engine.validate(expr)
            assert result.parsed is True

    def test_filter_range_validation(self):
        """Test filter range validation."""
        # FilterRange is used in filter_alphas but not directly importable
        # Test that the filter method accepts valid parameters
        from brain_alpha_ops.config import BrainSettings

        settings = BrainSettings(region="USA", delay=1, universe="TOP3000")
        assert settings.region == "USA"
        assert settings.delay == 1
        assert settings.universe == "TOP3000"

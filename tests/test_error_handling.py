"""Comprehensive error handling tests.

Tests cover:
  - API error handling
  - Configuration error handling
  - Pipeline error handling
  - Web layer error handling
"""

from __future__ import annotations

import pytest


class TestAPIErrorHandling:
    """Test API error handling."""

    def test_brain_api_error_creation(self):
        """Test BrainAPIError creation."""
        from brain_alpha_ops.brain_api.base import BrainAPIError

        error = BrainAPIError("Test error", status_code=400)
        assert str(error) == "Test error"
        assert error.status_code == 400

    def test_brain_api_error_with_payload(self):
        """Test BrainAPIError with payload."""
        from brain_alpha_ops.brain_api.base import BrainAPIError

        payload = {"detail": "Invalid request"}
        error = BrainAPIError("Test error", payload=payload)
        assert error.payload == payload

    def test_brain_api_error_with_retry_after(self):
        """Test BrainAPIError with retry_after."""
        from brain_alpha_ops.brain_api.base import BrainAPIError

        error = BrainAPIError("Rate limited", retry_after=60.0)
        assert error.retry_after == 60.0

    def test_brain_api_error_with_error_code(self):
        """Test BrainAPIError with error_code."""
        from brain_alpha_ops.brain_api.base import BrainAPIError

        error = BrainAPIError("Auth failed", error_code="AUTH_INVALID")
        assert error.error_code == "AUTH_INVALID"


class TestConfigurationErrorHandling:
    """Test configuration error handling."""

    def test_config_validation_error(self):
        """Test ConfigValidationError creation."""
        from brain_alpha_ops.config._loader import ConfigValidationError

        error = ConfigValidationError("Invalid config")
        assert str(error) == "Invalid config"

    def test_quality_thresholds_validation(self):
        """Test QualityThresholds validation."""
        from brain_alpha_ops.config import QualityThresholds

        # Valid thresholds
        thresholds = QualityThresholds(min_sharpe=1.25, min_fitness=1.0)
        assert thresholds.min_sharpe == 1.25
        assert thresholds.min_fitness == 1.0


class TestPipelineErrorHandling:
    """Test pipeline error handling."""

    def test_expression_parse_error(self):
        """Test ExpressionParseError creation."""
        from brain_alpha_ops.research.expression_ast import ExpressionParseError

        error = ExpressionParseError("Invalid expression")
        assert str(error) == "Invalid expression"

    def test_expression_parse_error_in_validation(self):
        """Test ExpressionParseError in validation flow."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        # Empty expression should be handled gracefully
        result = engine.validate("")
        assert result.parsed is False
        assert result.valid is False

    def test_expression_parse_error_with_deep_nesting(self):
        """Test ExpressionParseError with deep nesting."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        # Very long expression should be handled gracefully
        long_expr = "rank(ts_delta(close, 20)) + " * 100
        result = engine.validate(long_expr)
        # Should either parse or fail gracefully
        assert hasattr(result, "parsed")


class TestWebLayerErrorHandling:
    """Test web layer error handling."""

    def test_redact_error_message(self):
        """Test error message redaction."""
        from brain_alpha_ops.redaction import redact_error_message

        error = ValueError("password=secret123")
        redacted = redact_error_message(error)
        assert "secret123" not in redacted

    def test_classify_error(self):
        """Test error classification."""
        from brain_alpha_ops.errors import classify_error

        error = ValueError("test error")
        result = classify_error(error)
        assert hasattr(result, "error_code")
        assert hasattr(result, "category")

    def test_rate_limit_error(self):
        """Test rate limit error handling."""
        from brain_alpha_ops.web_rate_limit import RequestRateLimiter, RateLimitPolicy

        limiter = RequestRateLimiter(RateLimitPolicy(window_seconds=10, read_requests=1))
        limiter.check(key="test", method="GET", path="/api/test", now=100)
        result = limiter.check(key="test", method="GET", path="/api/test", now=101)
        assert result["ok"] is False
        assert result["error_code"] == "RATE_LIMITED"


class TestScoringErrorHandling:
    """Test scoring error handling."""

    def test_scoring_with_missing_metrics(self):
        """Test scoring with missing official metrics."""
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import build_scorecard
        from brain_alpha_ops.config import QualityThresholds

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Test hypothesis",
        )
        # No official_metrics set
        thresholds = QualityThresholds()
        scorecard = build_scorecard(candidate, thresholds)
        # Should still produce a valid scorecard
        assert "total_score" in scorecard
        assert "decision_band" in scorecard

    def test_scoring_with_empty_expression(self):
        """Test scoring with empty expression."""
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import build_scorecard
        from brain_alpha_ops.config import QualityThresholds

        candidate = Candidate(
            alpha_id="test_alpha",
            expression="",
            family="momentum",
            hypothesis="Test hypothesis",
        )
        thresholds = QualityThresholds()
        scorecard = build_scorecard(candidate, thresholds)
        # Should still produce a valid scorecard
        assert "total_score" in scorecard


class TestMetricsErrorHandling:
    """Test metrics error handling."""

    def test_metrics_with_invalid_name(self):
        """Test metrics with invalid name."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        # Should handle empty name gracefully
        collector.counter("", 1)
        collector.gauge("", 1.0)
        collector.histogram("", 1.0)

    def test_metrics_with_negative_value(self):
        """Test metrics with negative value."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.counter("test", -1)
        collector.gauge("test", -1.0)
        collector.histogram("test", -1.0)
        # Should not crash
        summary = collector.summary()
        assert "counters" in summary


class TestCodeQualityMetrics:
    """Test code quality metrics."""

    def test_quality_report_generation(self):
        """Test quality report generation."""
        from brain_alpha_ops.code_quality import generate_quality_report

        report = generate_quality_report()
        assert report.total_modules > 0
        assert report.total_lines > 0
        assert report.total_functions > 0
        assert report.avg_docstring_coverage > 0
        assert report.avg_type_annotation_coverage > 0

    def test_quality_report_formatting(self):
        """Test quality report formatting."""
        from brain_alpha_ops.code_quality import generate_quality_report, format_quality_report

        report = generate_quality_report()
        formatted = format_quality_report(report)
        assert isinstance(formatted, str)
        assert "Total modules" in formatted
        assert "Docstring coverage" in formatted

    def test_module_analysis(self):
        """Test module analysis."""
        from brain_alpha_ops.code_quality import analyze_module
        from pathlib import Path

        # Analyze a known module
        module_path = Path("brain_alpha_ops/types.py")
        if module_path.exists():
            metrics = analyze_module(module_path)
            assert metrics.lines_of_code > 0
            assert metrics.function_count >= 0
            assert metrics.class_count >= 0


class TestTestCoverageMetrics:
    """Test test coverage metrics."""

    def test_coverage_report_generation(self):
        """Test coverage report generation."""
        from test_coverage import generate_coverage_report

        report = generate_coverage_report()
        assert report.total_test_files > 0
        assert report.total_tests > 0
        assert report.test_files_with_tests > 0

    def test_coverage_report_formatting(self):
        """Test coverage report formatting."""
        from test_coverage import generate_coverage_report, format_coverage_report

        report = generate_coverage_report()
        formatted = format_coverage_report(report)
        assert isinstance(formatted, str)
        assert "Total test files" in formatted
        assert "Total tests" in formatted

    def test_test_file_analysis(self):
        """Test test file analysis."""
        from test_coverage import analyze_test_file
        from pathlib import Path

        # Analyze a known test file
        test_path = Path("tests/test_models.py")
        if test_path.exists():
            metrics = analyze_test_file(test_path)
            assert metrics.test_count >= 0
            assert isinstance(metrics.test_names, list)

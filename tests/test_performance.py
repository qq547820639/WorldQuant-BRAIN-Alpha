"""Performance benchmarks for critical code paths.

These tests measure execution time for key operations to detect
performance regressions. Run with: pytest tests/test_performance.py -v -m slow
"""

from __future__ import annotations

import time
from typing import Callable

import pytest


def _benchmark(func: Callable, iterations: int = 100) -> float:
    """Run function multiple times and return average execution time in ms."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    return sum(times) / len(times)


@pytest.mark.slow
class TestExpressionEnginePerformance:
    """Benchmark expression parsing and validation."""

    def test_parse_simple_expression(self):
        """Benchmark parsing a simple expression."""
        from brain_alpha_ops.research.expression_ast import parse_expression

        expr = "rank(ts_delta(close, 20))"
        avg_ms = _benchmark(lambda: parse_expression(expr), iterations=1000)
        assert avg_ms < 1.0  # Should parse in under 1ms

    def test_parse_complex_expression(self):
        """Benchmark parsing a complex nested expression."""
        from brain_alpha_ops.research.expression_ast import parse_expression

        expr = "group_neutralize(decay_linear(ts_delta(winsorize(market_cap + volume, 0.01), 60), 20), industry)"
        avg_ms = _benchmark(lambda: parse_expression(expr), iterations=1000)
        assert avg_ms < 2.0  # Should parse in under 2ms

    def test_validate_expression(self):
        """Benchmark expression validation."""
        from brain_alpha_ops.research.expression_engine import ExpressionEngine

        engine = ExpressionEngine()
        expr = "rank(ts_delta(close, 20))"
        avg_ms = _benchmark(lambda: engine.validate(expr), iterations=100)
        assert avg_ms < 10.0  # Should validate in under 10ms


@pytest.mark.slow
class TestScoringPerformance:
    """Benchmark scoring operations."""

    def test_build_scorecard(self):
        """Benchmark scorecard building."""
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import build_scorecard
        from brain_alpha_ops.config import QualityThresholds

        candidate = Candidate(
            alpha_id="bench_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Benchmark test",
        )
        candidate.official_metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.3,
            "pass_fail": "PASS",
        }
        thresholds = QualityThresholds()

        avg_ms = _benchmark(lambda: build_scorecard(candidate, thresholds), iterations=100)
        assert avg_ms < 50.0  # Should build scorecard in under 50ms

    def test_evaluate_quality_gate(self):
        """Benchmark quality gate evaluation."""
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import evaluate_quality_gate
        from brain_alpha_ops.config import QualityThresholds

        candidate = Candidate(
            alpha_id="bench_alpha",
            expression="rank(ts_delta(close, 20))",
            family="momentum",
            hypothesis="Benchmark test",
        )
        candidate.official_metrics = {
            "sharpe": 1.5,
            "fitness": 1.2,
            "turnover": 0.3,
            "pass_fail": "PASS",
        }
        thresholds = QualityThresholds()

        avg_ms = _benchmark(lambda: evaluate_quality_gate(candidate, thresholds), iterations=100)
        assert avg_ms < 20.0  # Should evaluate in under 20ms


@pytest.mark.slow
class TestCandidateGenerationPerformance:
    """Benchmark candidate generation."""

    def test_generate_candidates(self):
        """Benchmark candidate generation."""
        from brain_alpha_ops.research.generator import CandidateGenerator

        generator = CandidateGenerator()
        avg_ms = _benchmark(lambda: generator.generate(10, dataset_id="pv1"), iterations=10)
        assert avg_ms < 100.0  # Should generate 10 candidates in under 100ms


@pytest.mark.slow
class TestAPIPerformance:
    """Benchmark API operations with stub."""

    def test_stub_simulation_flow(self):
        """Benchmark stub simulation flow."""
        from tests.production_api_stub import ProductionBrainAPIStub

        api = ProductionBrainAPIStub()

        def run_simulation():
            sim_id = api.submit_simulation("rank(close)", {"region": "USA"})
            api.poll_simulation(sim_id)

        avg_ms = _benchmark(run_simulation, iterations=10)
        assert avg_ms < 50.0  # Should complete in under 50ms


@pytest.mark.slow
class TestMemoryUsage:
    """Basic memory usage checks."""

    def test_pipeline_memory_usage(self):
        """Check pipeline doesn't leak excessive memory."""
        import sys
        from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
        from brain_alpha_ops.config import OpsConfig
        from tests.production_api_stub import ProductionBrainAPIStub

        config = OpsConfig()
        pipeline = AlphaResearchPipeline(config=config, api=ProductionBrainAPIStub())

        # Get initial size
        initial_size = sys.getsizeof(pipeline.__dict__)

        # Access services multiple times
        for _ in range(10):
            _ = pipeline.services

        # Check size didn't grow excessively
        final_size = sys.getsizeof(pipeline.__dict__)
        assert final_size < initial_size * 2  # Should not double in size


@pytest.mark.slow
class TestMetricsCollection:
    """Test metrics collection module."""

    def test_counter_metric(self):
        """Test counter metric collection."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.counter("test_counter", 5)
        collector.counter("test_counter", 3)

        summary = collector.summary()
        assert summary["counters"]["test_counter"] == 8

    def test_gauge_metric(self):
        """Test gauge metric collection."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.gauge("test_gauge", 42.0)

        summary = collector.summary()
        assert summary["gauges"]["test_gauge"] == 42.0

    def test_histogram_metric(self):
        """Test histogram metric collection."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.histogram("test_histogram", 10.0)
        collector.histogram("test_histogram", 20.0)
        collector.histogram("test_histogram", 30.0)

        summary = collector.summary()
        assert summary["histograms"]["test_histogram"]["count"] == 3
        assert summary["histograms"]["test_histogram"]["avg"] == 20.0
        assert summary["histograms"]["test_histogram"]["min"] == 10.0
        assert summary["histograms"]["test_histogram"]["max"] == 30.0

    def test_timer_metric(self):
        """Test timer metric collection."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        with collector.timer("test_timer"):
            time.sleep(0.001)  # 1ms

        summary = collector.summary()
        assert "test_timer" in summary["histograms"]
        assert summary["histograms"]["test_timer"]["count"] == 1
        assert summary["histograms"]["test_timer"]["avg"] > 0

    def test_metrics_with_tags(self):
        """Test metrics with tags."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.counter("api_call", 1, endpoint="/api/run", method="POST")
        collector.counter("api_call", 1, endpoint="/api/run", method="GET")

        summary = collector.summary()
        assert len(summary["counters"]) == 2

    def test_metrics_reset(self):
        """Test metrics reset."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        collector.counter("test_counter", 5)
        collector.gauge("test_gauge", 42.0)

        collector.reset()

        summary = collector.summary()
        assert summary["counters"] == {}
        assert summary["gauges"] == {}

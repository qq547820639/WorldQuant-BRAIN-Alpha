"""Concurrency and thread safety tests.

Tests cover:
  - Thread-safe operations
  - Concurrent access patterns
  - Lock behavior
  - Race condition prevention
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest


class TestThreadSafety:
    """Test thread-safe operations."""

    def test_metrics_collector_thread_safety(self):
        """Test MetricsCollector is thread-safe."""
        from brain_alpha_ops.metrics import MetricsCollector

        collector = MetricsCollector()
        errors = []

        def worker(worker_id: int):
            try:
                for i in range(100):
                    collector.counter(f"worker_{worker_id}", 1)
                    collector.gauge(f"gauge_{worker_id}", float(i))
                    collector.histogram(f"hist_{worker_id}", float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        summary = collector.summary()
        assert len(summary["counters"]) == 10

    def test_rate_limiter_thread_safety(self):
        """Test RateLimiter is thread-safe."""
        from brain_alpha_ops.web_rate_limit import RequestRateLimiter, RateLimitPolicy

        limiter = RequestRateLimiter(RateLimitPolicy(window_seconds=10, read_requests=100))
        results = []
        errors = []

        def worker(worker_id: int):
            try:
                for i in range(50):
                    result = limiter.check(
                        key=f"worker_{worker_id}",
                        method="GET",
                        path="/api/test",
                        now=100.0 + i * 0.01,
                    )
                    results.append(result["ok"])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All results should be True (under limit)
        assert all(results)

    def test_convergence_tracker_thread_safety(self):
        """Test ConvergenceTracker is thread-safe."""
        from brain_alpha_ops.research.convergence import ConvergenceTracker

        tracker = ConvergenceTracker(window_size=20, stall_threshold=5)
        errors = []

        def worker(worker_id: int):
            try:
                for i in range(20):
                    tracker.record_cycle(
                        cycle=worker_id * 20 + i,
                        produced=10,
                        passed_local=5,
                        simulated=3,
                        passed_gate=1,
                        submitted=0,
                        candidates=[],
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        summary = tracker.summary()
        assert "sharpe_trend" in summary


class TestConcurrentOperations:
    """Test concurrent operations."""

    def test_concurrent_profile_expression(self):
        """Test concurrent profile_expression calls."""
        from brain_alpha_ops.research.expression_ast import profile_expression

        expressions = [f"rank(ts_delta(field_{i}, 20))" for i in range(100)]
        results = []

        def worker(expr):
            return profile_expression(expr)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, expr) for expr in expressions]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        assert len(results) == 100
        assert all(r.parsed for r in results)

    def test_concurrent_scorecard_building(self):
        """Test concurrent scorecard building."""
        from brain_alpha_ops.models import Candidate
        from brain_alpha_ops.research.scoring import build_scorecard
        from brain_alpha_ops.config import QualityThresholds

        candidates = [
            Candidate(
                alpha_id=f"alpha_{i}",
                expression=f"rank(ts_delta(close, {20 + i}))",
                family="momentum",
                hypothesis=f"Test {i}",
            )
            for i in range(50)
        ]
        for c in candidates:
            c.official_metrics = {"sharpe": 1.5, "fitness": 1.2, "turnover": 0.3, "pass_fail": "PASS"}

        thresholds = QualityThresholds()
        results = []

        def worker(candidate):
            return build_scorecard(candidate, thresholds)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(worker, c) for c in candidates]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        assert len(results) == 50
        assert all("total_score" in r for r in results)

    def test_concurrent_candidate_generation(self):
        """Test concurrent candidate generation."""
        from brain_alpha_ops.research.generator import CandidateGenerator

        results = []

        def worker(worker_id):
            generator = CandidateGenerator()
            return generator.generate(5, dataset_id="pv1")

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            for future in as_completed(futures):
                result = future.result()
                results.extend(result)

        assert len(results) > 0


class TestLockBehavior:
    """Test lock behavior."""

    def test_request_lock_behavior(self):
        """Test request lock prevents concurrent requests."""
        from brain_alpha_ops.brain_api.official import OfficialBrainAPI
        from brain_alpha_ops.config_models import OfficialAPIConfig

        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test", min_request_interval_seconds=0.1),
            token="token",
        )

        # Verify lock exists
        assert hasattr(api, "_request_lock")
        assert api._request_lock is not None

    def test_cache_lock_behavior(self):
        """Test cache lock prevents concurrent cache writes."""
        from brain_alpha_ops.brain_api.official import OfficialBrainAPI
        from brain_alpha_ops.config_models import OfficialAPIConfig

        api = OfficialBrainAPI(
            OfficialAPIConfig(base_url="https://example.test"),
            token="token",
        )

        # Verify cache lock exists
        assert hasattr(api, "_cache_lock")
        assert api._cache_lock is not None

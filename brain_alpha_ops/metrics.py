"""Metrics collection for monitoring pipeline performance.

This module provides lightweight metrics collection for monitoring
alpha pipeline performance without external dependencies.

Usage:
    from brain_alpha_ops.metrics import metrics

    # Record a metric
    metrics.record("pipeline.cycles_completed", 1)

    # Record timing
    with metrics.timer("pipeline.cycle_duration"):
        # ... do work
        pass

    # Get summary
    summary = metrics.summary()
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    timestamp: float
    tags: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Lightweight in-memory metrics collector."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._timers: dict[str, list[float]] = defaultdict(list)
        self._histograms: dict[str, list[float]] = defaultdict(list)
        # F-020: guard all reads/writes — the web console runs tasks in a
        # ThreadPoolExecutor (WebDefaults.TASK_EXECUTOR_MAX_WORKERS=4), so
        # concurrent counter increments / histogram appends race without a lock.
        self._lock = threading.Lock()

    def counter(self, name: str, value: int = 1, **tags: str) -> None:
        """Increment a counter metric."""
        key = self._make_key(name, tags)
        with self._lock:
            self._counters[key] += value

    def gauge(self, name: str, value: float, **tags: str) -> None:
        """Set a gauge metric."""
        key = self._make_key(name, tags)
        with self._lock:
            self._gauges[key] = value

    def histogram(self, name: str, value: float, **tags: str) -> None:
        """Record a histogram value."""
        key = self._make_key(name, tags)
        with self._lock:
            self._histograms[key].append(value)

    @contextmanager
    def timer(self, name: str, **tags: str) -> Generator[None, None, None]:
        """Context manager for timing operations."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.histogram(name, elapsed_ms, **tags)

    def summary(self) -> dict[str, Any]:
        """Get a summary of all collected metrics."""
        # F-020: snapshot under the lock, then compute stats outside the lock
        # to minimize critical-section hold time.
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            histograms = {name: list(values) for name, values in self._histograms.items()}
        return {
            "counters": counters,
            "gauges": gauges,
            "histograms": {
                name: {
                    "count": len(values),
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                    "avg": sum(values) / len(values) if values else 0,
                }
                for name, values in histograms.items()
            },
        }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()
            self._histograms.clear()

    def _make_key(self, name: str, tags: dict[str, str]) -> str:
        """Create a metric key from name and tags."""
        if tags:
            tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
            return f"{name}[{tag_str}]"
        return name


# Global metrics instance
metrics = MetricsCollector()


def record_pipeline_metric(name: str, value: float, **tags: str) -> None:
    """Record a pipeline metric."""
    metrics.histogram(f"pipeline.{name}", value, **tags)


def record_api_metric(name: str, value: float, **tags: str) -> None:
    """Record an API metric."""
    metrics.histogram(f"api.{name}", value, **tags)


def record_scoring_metric(name: str, value: float, **tags: str) -> None:
    """Record a scoring metric."""
    metrics.histogram(f"scoring.{name}", value, **tags)

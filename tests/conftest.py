from __future__ import annotations

"""Pytest configuration for safe local test collection."""

import sys
import os
from pathlib import Path

import pytest

# Add tests/ directory to Python path so test files can import from each other
tests_dir = str(Path(__file__).parent)
if tests_dir not in sys.path:
    sys.path.insert(0, tests_dir)


def pytest_ignore_collect(collection_path, config):
    """Skip e2e tests when playwright is not installed (CI does not have browser deps)."""
    path_text = str(collection_path)
    if "/e2e/" in path_text or "tests/e2e" in path_text or "e2e_" in path_text:
        if os.environ.get("BRAIN_BROWSER_E2E_LIVE") != "1":
            return True
        try:
            import playwright  # noqa: F401
        except ImportError:
            return True
    return None


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def api_stub():
    """Return a fresh, configured ProductionBrainAPIStub instance."""
    from tests.production_api_stub import ProductionBrainAPIStub
    return ProductionBrainAPIStub()


@pytest.fixture()
def sample_candidate():
    """Return a Candidate with reasonable default values."""
    from brain_alpha_ops.models import Candidate
    return Candidate(
        alpha_id="test_alpha_001",
        expression="rank(ts_delta(close, 20))",
        family="Momentum",
        hypothesis="short-term price momentum",
        data_fields=["close"],
        operators=["rank", "ts_delta"],
        official_metrics={
            "sharpe": 1.45,
            "fitness": 1.10,
            "turnover": 0.12,
            "returns": 0.045,
            "drawdown": 0.08,
            "correlation": 0.25,
            "pass_fail": "PASS",
        },
        scorecard={"total_score": 82},
        gate={"status": "PASS", "submission_ready": True},
        lifecycle_status="scored",
    )


@pytest.fixture()
def sample_metrics() -> dict:
    """Return an OfficialMetrics dict with reasonable default values."""
    return {
        "sharpe": 1.45,
        "fitness": 1.10,
        "turnover": 0.12,
        "returns": 0.045,
        "drawdown": 0.08,
        "margin": 5.2,
        "sub_universe_sharpe": 0.95,
        "correlation": 0.25,
        "weight_concentration": 0.06,
        "pass_fail": "PASS",
        "turnover_quality_warning": False,
        "failure_reason": None,
    }


@pytest.fixture()
def run_config():
    """Return a minimal RunConfig suitable for unit tests."""
    from brain_alpha_ops.config import RunConfig
    return RunConfig(environment="production")

"""Pipeline init tests extracted from ``tests/test_pipeline.py``.

Covers: pipeline construction, config validation, backtest slot management.
Full suite in ``test_pipeline.py``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from brain_alpha_ops.config import OpsConfig, ResearchBudget
from tests.fixtures.factories import make_stub_api
from brain_alpha_ops.research.pipeline import AlphaResearchPipeline


def test_pipeline_keeps_visible_backtest_slots_separate_from_official_capacity():
    """Visible backtest slots must be independent of official capacity limits."""
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(
            budget=ResearchBudget(
                max_candidates_per_cycle=3,
                max_official_simulations_per_cycle=1,
                max_official_concurrent_simulations=1,
                official_backtest_batch_size=1,
                max_cycles=1,
                require_cloud_sync=False,
            ),
            storage_dir=str(tmp),
        )
        pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
        assert pipeline._active_backtest_limit() == 1


def test_pipeline_init_requires_api_or_execution_backend():
    """Pipeline must reject construction without api or execution_backend."""
    import pytest
    from brain_alpha_ops.config import OpsConfig

    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(storage_dir=str(tmp))
        with pytest.raises(ValueError, match="api.*execution_backend"):
            AlphaResearchPipeline(config=config)


def test_pipeline_services_accessible_after_init():
    """Composition services must be accessible after pipeline init."""
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(storage_dir=str(tmp))
        pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
        assert hasattr(pipeline, "services")
        assert pipeline.services is not None
        assert hasattr(pipeline.services, "runtime")


def test_pipeline_strategy_profile_index_initialized():
    """Strategy profile index must be initialized on construction."""
    with tempfile.TemporaryDirectory() as tmp:
        config = OpsConfig(storage_dir=str(tmp))
        pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
        assert pipeline.strategy_profile_index is not None

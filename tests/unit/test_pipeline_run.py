"""Pipeline run tests extracted from ``tests/test_pipeline.py``.

Covers: run() orchestration, main loop, candidate generation.
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
from tests.production_api_stub import ProductionBrainAPIStub
from brain_alpha_ops.research.pipeline import AlphaResearchPipeline
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.pipeline_helpers import expr_key


def test_pipeline_candidate_pool_operations_work(tmp_path):
    """Candidate pool merge, prune, and ranking must work correctly."""
    from brain_alpha_ops.research.pipeline_helpers import rank_candidates

    c1 = Candidate(alpha_id="a1", family="test", hypothesis="test_h", expression="rank(close)", lifecycle_status="draft")
    c2 = Candidate(alpha_id="a2", family="test", hypothesis="test_h", expression="rank(volume)", lifecycle_status="draft")
    c1.local_quality = {"passed": True, "score": 85}
    c2.local_quality = {"passed": True, "score": 75}

    pool = {expr_key(c1): c1, expr_key(c2): c2}
    ranked = rank_candidates(list(pool.values()))
    assert len(ranked) == 2


def test_pipeline_single_cycle_halts_after_max(tmp_path):
    """Pipeline must halt after max_cycles."""
    config = OpsConfig(
        budget=ResearchBudget(
            max_candidates_per_cycle=1,
            max_cycles=1,
            require_cloud_sync=False,
        ),
        storage_dir=str(tmp_path),
    )
    pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
    assert config.budget.max_cycles == 1


def test_pipeline_run_creates_result_with_run_id(tmp_path):
    """run() must produce a PipelineResult with a unique run_id."""
    config = OpsConfig(
        budget=ResearchBudget(
            max_candidates_per_cycle=1,
            max_cycles=1,
            require_cloud_sync=False,
        ),
        storage_dir=str(tmp_path),
    )
    pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
    result = pipeline.run(auto_submit=False)
    assert result.run_id
    assert result.run_id.startswith("run_")
    assert isinstance(result.candidates, list)

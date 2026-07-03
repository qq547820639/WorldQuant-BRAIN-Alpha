"""Pipeline postprocess tests extracted from ``tests/test_pipeline.py``.

Covers: convergence tracking, auto-calibration, fusion, post-cycle summary.
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
from brain_alpha_ops.models import Candidate


def test_pipeline_convergence_accessible(tmp_path):
    """Convergence tracker must be accessible after pipeline init."""
    config = OpsConfig(
        budget=ResearchBudget(
            max_candidates_per_cycle=3,
            max_cycles=1,
            require_cloud_sync=False,
        ),
        storage_dir=str(tmp_path),
    )
    pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
    assert hasattr(pipeline, "convergence")
    summary = pipeline.convergence.summary()
    assert isinstance(summary, dict)
    assert "stalled" in summary


def test_pipeline_auto_calibrator_accessible(tmp_path):
    """Auto-calibrator must be accessible after pipeline init."""
    config = OpsConfig(
        budget=ResearchBudget(
            max_candidates_per_cycle=3,
            max_cycles=1,
            require_cloud_sync=False,
        ),
        storage_dir=str(tmp_path),
    )
    pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
    assert hasattr(pipeline, "auto_calibrator")


def test_pipeline_scoring_config_preserved(tmp_path):
    """Scoring config from OpsConfig must be preserved."""
    config = OpsConfig(
        budget=ResearchBudget(
            max_candidates_per_cycle=1,
            max_cycles=1,
            require_cloud_sync=False,
        ),
        storage_dir=str(tmp_path),
    )
    pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
    assert pipeline.config.scoring.prior_layer_weight == 0.30
    assert pipeline.config.thresholds.min_sharpe == 1.25


def test_pipeline_submission_policy_accessible(tmp_path):
    """Submission policy must be accessible from config."""
    config = OpsConfig(
        budget=ResearchBudget(
            max_candidates_per_cycle=1,
            max_cycles=1,
            require_cloud_sync=False,
        ),
        storage_dir=str(tmp_path),
    )
    pipeline = AlphaResearchPipeline(config=config, api=make_stub_api())
    assert hasattr(pipeline.config, "submission_policy")
    assert pipeline.config.submission_policy.max_auto_submissions_per_day == 3

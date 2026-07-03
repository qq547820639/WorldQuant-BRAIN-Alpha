"""Shared mock factories and fixtures for all test layers.

Import patterns::

    from tests.fixtures.factories import (
        make_candidate,
        make_scoring_policy_default,
        make_stub_api,
        make_single_cycle_config,
    )
"""

from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import (
    BrainSettings,
    OfficialAPIConfig,
    OpsConfig,
    ResearchBudget,
    ScoringConfig,
    QualityThresholds,
    SubmissionPolicy,
)
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.scoring.policy import (
    GateRuleSet,
    LayerWeights,
    ScoringPolicy,
    ThresholdProfile,
)


# ── Config factories ──────────────────────────────────────────────────

def make_single_cycle_config(
    tmp_path: str | Path | None = None,
    **budget_overrides: Any,
) -> OpsConfig:
    """Return an ``OpsConfig`` tuned for single-cycle pipeline tests.

    Args:
        tmp_path: Storage directory (auto-creates temp dir if None).
        **budget_overrides: Override any ``ResearchBudget`` field.
    """
    path = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    budget_kw: dict[str, Any] = {
        "max_candidates_per_cycle": 3,
        "max_official_validations_per_cycle": 0,
        "max_official_simulations_per_cycle": 0,
        "max_cycles": 1,
        "require_cloud_sync": False,
    }
    budget_kw.update(budget_overrides)
    return OpsConfig(budget=ResearchBudget(**budget_kw), storage_dir=str(path))


def make_default_config(tmp_path: str | Path | None = None) -> OpsConfig:
    """Return a default ``OpsConfig`` for general pipeline tests."""
    path = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    return OpsConfig(storage_dir=str(path))


# ── Candidate factories ───────────────────────────────────────────────

def make_candidate(
    *,
    alpha_id: str = "test-alpha-001",
    expression: str = "rank(close)",
    lifecycle_status: str = "draft",
    official_metrics: dict[str, Any] | None = None,
    local_quality: dict[str, Any] | None = None,
    gate: dict[str, Any] | None = None,
    **extra: Any,
) -> Candidate:
    """Build a ``Candidate`` with sensible test defaults.

    Args:
        alpha_id: Unique alpha identifier.
        expression: Alpha expression string.
        lifecycle_status: Lifecycle status string.
        official_metrics: Dict of official simulation metrics.
        local_quality: Dict of local quality scores.
        gate: Dict of gate results.
        **extra: Additional fields set via ``setattr``.
    """
    candidate = Candidate(
        alpha_id=alpha_id,
        family="test_family",
        hypothesis="test_hypothesis",
        expression=expression,
        lifecycle_status=lifecycle_status,
    )
    if official_metrics is not None:
        candidate.official_metrics = official_metrics
    if local_quality is not None:
        candidate.local_quality = local_quality
    if gate is not None:
        candidate.gate = gate
    for key, value in extra.items():
        setattr(candidate, key, value)
    return candidate


def make_scored_candidate(*, sharpe: float = 2.0, fitness: float = 1.5, **kwargs: Any) -> Candidate:
    """Build a candidate with pre-set official metrics for scoring tests."""
    return make_candidate(
        official_metrics={
            "sharpe": sharpe,
            "fitness": fitness,
            "turnover": 0.3,
            "self_correlation": 0.5,
        },
        **kwargs,
    )


# ── ScoringPolicy factories ───────────────────────────────────────────

def make_scoring_policy_default() -> ScoringPolicy:
    """Return the default (production-safe) ``ScoringPolicy``."""
    return ScoringPolicy.default()


def make_scoring_policy_aggressive() -> ScoringPolicy:
    """Return a lower-threshold policy for aggressive testing."""
    return replace(
        ScoringPolicy.default(),
        gates=GateRuleSet(
            submit_threshold=60.0,
            optimize_threshold=40.0,
            research_threshold=20.0,
        ),
    )


def make_scoring_policy_low_vol() -> ScoringPolicy:
    """Return a low-volatility regime policy."""
    return ScoringPolicy.default().with_regime("low_vol")


# ── Stub API ──────────────────────────────────────────────────────────

def make_stub_api(**overrides: Any) -> Any:
    """Build a ``ProductionBrainAPIStub`` for offline pipeline tests."""
    from tests.production_api_stub import ProductionBrainAPIStub
    return ProductionBrainAPIStub(**overrides)

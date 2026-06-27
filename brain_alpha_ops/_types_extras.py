"""Configuration TypedDict definitions split out from types.py for line-limit compliance.

These types are re-exported via brain_alpha_ops.types; prefer importing from there.
"""

from __future__ import annotations

from typing import TypedDict


class BrainSettingsDict(TypedDict, total=False):
    """BRAIN platform settings."""
    instrumentType: str
    region: str
    delay: int
    universe: str
    dataset: str
    type: str


class ResearchBudgetDict(TypedDict, total=False):
    """Research budget settings."""
    max_cycles: int
    max_candidates_per_cycle: int
    retained_alpha_pool_size: int
    min_prior_score_for_official_validation: float
    min_prior_score_for_official_simulation: float
    enable_secondary_fusion: bool
    run_forever: bool
    cycle_pause_seconds: float


class QualityThresholdsDict(TypedDict, total=False):
    """Quality threshold settings."""
    min_sharpe: float
    min_fitness: float
    min_turnover: float
    max_turnover: float
    max_self_correlation: float
    max_prod_correlation: float
    max_weight_concentration: float
    min_sub_universe_sharpe: float

"""Snapshot service callbacks and mutable state containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.models import Candidate


@dataclass(frozen=True)
class PipelineSnapshotServices:
    """Callbacks supplied by the pipeline coordinator for snapshot assembly."""

    candidate_pool_candidates: Callable[[list[Candidate]], list[Candidate]]
    pending_backtest_candidates: Callable[[list[Candidate]], list[Candidate]]
    validation_targets: Callable[[list[Candidate]], list[Candidate]]
    active_backtest_limit: Callable[[], int]
    poll_interval_seconds: Callable[[], float]
    slot_snapshot: Callable[[], list[dict]]
    current_strategy_profile: Callable[[], dict]
    strategy_lifecycle_summary: Callable[[dict, int], dict]
    strategy_plugin_summary: Callable[[], dict]
    observability_official_call_guard_snapshot: Callable[[], dict]
    assess_auto_submission: Callable[[Candidate, int], dict]
    smart_rank_candidates: Callable[[list[Candidate]], list[Candidate]]
    smart_ranking_score: Callable[[Candidate], float]
    cloud_correlation_risk: Callable[[Candidate], dict]


@dataclass(frozen=True)
class PipelineSnapshotState:
    """Mutable pipeline counters and records copied for snapshot rendering."""

    produced_count: int = 0
    officially_simulated_count: int = 0
    official_validation_attempted_count: int = 0
    official_validation_passed_count: int = 0
    backtests_submitted: int = 0
    recovered_backtest_slot_count: int = 0
    official_calls_halted: bool = False
    official_halt_reason: str = ""
    official_retry_remaining_seconds: float = 0.0
    observability_throttle: dict = field(default_factory=dict)
    observability_generation_guidance: dict = field(default_factory=dict)
    context_summary: dict = field(default_factory=dict)
    cloud_sync: dict = field(default_factory=dict)
    cloud_alphas: list[dict] = field(default_factory=list)
    lifecycle_records: list[dict] = field(default_factory=list)
    backtest_records: list[dict] = field(default_factory=list)
    convergence: dict = field(default_factory=dict)
    user_profile: dict = field(default_factory=dict)
    bandit_rewards: dict[int, list[float]] = field(default_factory=dict)
    bandit_counts: dict[int, int] = field(default_factory=dict)
    strategy_switch_count: int = 0
    strategy_profile_index: int = 0
    active_dataset_id: str = ""
    auto_calibrator_status: Any = "ready"
    scoring_calibrated: bool = False

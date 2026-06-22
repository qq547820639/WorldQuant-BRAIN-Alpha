"""Runtime state helpers for the alpha research pipeline coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.models import Candidate, PipelineEvent


@dataclass
class CycleState:
    """Mutable containers shared across one research cycle."""

    pool_by_expression: dict[str, Candidate] = field(default_factory=dict)
    accepted_candidates: list[Candidate] = field(default_factory=list)
    archive_stats: dict[str, int] = field(default_factory=dict)
    archive_samples: list[Candidate] = field(default_factory=list)
    blocked_expressions: set[str] = field(default_factory=set)


@dataclass
class PipelineRuntimeState:
    """Mutable runtime state owned by ``AlphaResearchPipeline``.

    The pipeline class keeps compatibility properties for these fields, but the
    values live in this grouped state object so constructor wiring is explicit
    and easier to audit.
    """

    config: Any | None = None
    api: Any | None = None
    repository: Any | None = None
    ledger: Any | None = None
    generator: Any | None = None
    progress_callback: Any | None = None
    stop_callback: Any | None = None
    _local_data_dir_existed_at_start: bool = False

    events: list[PipelineEvent] = field(default_factory=list)
    run_id: str = ""
    user_profile: dict[str, Any] = field(default_factory=dict)
    production_context: dict[str, Any] = field(default_factory=dict)

    official_calls_halted: bool = False
    official_halt_reason: str = ""
    official_resume_at: float = 0.0
    official_halt_cycle: int = 0
    official_call_guard: Any | None = None
    officially_simulated_count: int = 0
    official_validation_attempted_count: int = 0
    official_validation_passed_count: int = 0

    produced_count: int = 0
    context_summary: dict[str, Any] = field(default_factory=dict)
    last_backtests: list[dict[str, Any]] = field(default_factory=list)
    last_runtime_data: dict[str, Any] = field(default_factory=dict)
    lifecycle_records: list[dict[str, Any]] = field(default_factory=list)
    backtest_records: list[dict[str, Any]] = field(default_factory=list)
    backtests_submitted: int = 0
    recovered_backtest_slot_count: int = 0
    backtest_slot_manager: Any | None = None
    backtest_slots: dict[int, Candidate] = field(default_factory=dict)

    observability_throttle: dict[str, Any] = field(default_factory=dict)
    observability_generation_guidance: dict[str, Any] = field(default_factory=dict)
    _last_context_refresh: float = 0.0
    _knowledge_base: Any | None = None
    _local_backtest_engine: Any | None = None
    _cross_review_service: Any | None = None

    strategy_profile_index: int = 0
    strategy_switch_count: int = 0
    cycles_since_strategy_switch: int = 0
    official_results_since_strategy_switch: int = 0
    ready_since_strategy_switch: int = 0
    official_rejections_since_strategy_switch: int = 0
    _bandit_rewards: dict[int, list[float]] = field(default_factory=dict)
    _bandit_counts: dict[int, int] = field(default_factory=dict)
    strategy_lifecycle: Any | None = None
    strategy_plugins: Any | None = None

    cloud_alphas: list[dict[str, Any]] = field(default_factory=list)
    cloud_sync: dict[str, Any] = field(default_factory=dict)
    _cloud_similarity_rows: list[dict[str, Any]] = field(default_factory=list)
    _cloud_risk_cache: dict[tuple[str, str, int], dict[str, Any]] = field(default_factory=dict)

    _loader: Any | None = None
    _mapper: Any | None = None
    _theme_engine: Any | None = None
    _selector: Any | None = None
    _hypothesis_library: Any | None = None
    _active_dataset_id: str = ""
    _context_field_names: set[str] = field(default_factory=set)
    _context_operator_names: set[str] = field(default_factory=set)
    _dataset_field_names_cache: dict[str, set[str]] = field(default_factory=dict)
    _active_assistant_guidance: dict[str, Any] | None = None
    _cached_assistant_guidance: dict[str, Any] | None = None
    _cached_guidance_at_cycle: int = -1

    check_registry: Any | None = None
    convergence: Any | None = None
    auto_calibrator: Any | None = None
    optimizer: Any | None = None


def bind_runtime_state_properties(owner_class: type, state_attr: str = "_runtime_state") -> None:
    """Bind PipelineRuntimeState fields as compatibility properties on owner_class.

    P3-6 refactor note: this uses dynamic ``setattr`` to attach a getter/
    setter property per field on ``owner_class``.  This works at runtime but
    defeats mypy / IDE auto-completion because the class body has no source
    for those names.

    Why we still ship it: the alternative (copying 60+ fields onto
    ``AlphaResearchPipeline`` directly) would have broken three downstream
    consumers that introspect ``PipelineRuntimeState`` dataclass fields.
    The deprecation plan is to migrate callers one-by-one to read
    ``pipeline._runtime_state.<field>`` directly, then delete this helper
    in a major version bump.  Until then the property shim keeps the
    existing ``pipeline.<field>`` syntax working.

    Each generated property is tagged with ``__runtime_state_proxy__`` so
    tooling can recognise and warn about legacy access patterns.
    """

    for field_name in PipelineRuntimeState.__dataclass_fields__:
        if hasattr(owner_class, field_name):
            continue
        prop = _runtime_state_property(field_name, state_attr)
        # ``property`` objects only gained ``__set_name__`` in Python 3.10;
        # the call is a no-op on 3.9 so we guard for cross-version safety.
        set_name = getattr(prop, "__set_name__", None)
        if set_name is not None:
            set_name(owner_class, field_name)
        try:
            setattr(prop, "__runtime_state_proxy__", True)
        except (AttributeError, TypeError):
            pass
        setattr(owner_class, field_name, prop)


def _runtime_state_property(field_name: str, state_attr: str) -> property:
    def getter(instance: Any) -> Any:
        return getattr(getattr(instance, state_attr), field_name)

    def setter(instance: Any, value: Any) -> None:
        setattr(getattr(instance, state_attr), field_name, value)

    return property(getter, setter)


@dataclass(frozen=True)
class StrategyRewardSnapshot:
    """Computed reward and lifecycle metrics for one strategy profile."""

    reward: float
    metrics: dict[str, int | float]


def compute_strategy_reward(candidates: list[Candidate]) -> StrategyRewardSnapshot:
    """Compute the bandit reward from official Sharpe and submission readiness."""

    sharpe_values = [
        float(candidate.official_metrics.get("sharpe", 0.0) or 0.0)
        for candidate in candidates
        if candidate.official_metrics
    ]
    avg_sharpe = sum(sharpe_values) / max(len(sharpe_values), 1)
    pass_rate = sum(1 for candidate in candidates if candidate.gate.get("submission_ready")) / max(len(candidates), 1)
    reward = avg_sharpe * (0.5 + 0.5 * pass_rate)
    return StrategyRewardSnapshot(
        reward=reward,
        metrics={
            "avg_sharpe": round(avg_sharpe, 6),
            "pass_rate": round(pass_rate, 6),
            "pool_size": len(candidates),
        },
    )


def record_strategy_reward(
    profile_index: int,
    candidates: list[Candidate],
    rewards: dict[int, list[float]],
    counts: dict[int, int],
) -> StrategyRewardSnapshot:
    """Append a profile reward and update selection counts in place."""

    snapshot = compute_strategy_reward(candidates)
    rewards.setdefault(profile_index, []).append(snapshot.reward)
    counts[profile_index] = counts.get(profile_index, 0) + 1
    return snapshot


def bandit_runtime_summary(
    active_profile: dict[str, Any],
    rewards: dict[int, list[float]],
    counts: dict[int, int],
    *,
    total_switches: int,
) -> dict[str, Any]:
    """Return the Web/API runtime payload for adaptive strategy bandit state."""

    return {
        "active_profile": active_profile.get("name", "unknown"),
        "profile_rewards": {
            str(index): round(sum(values) / max(len(values), 1), 3)
            for index, values in rewards.items()
        },
        "profile_counts": counts,
        "total_switches": total_switches,
    }

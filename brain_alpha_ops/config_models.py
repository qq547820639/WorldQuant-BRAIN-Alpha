"""Dataclass models for BRAIN Alpha Ops runtime configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
from typing import Any


@dataclass
class BrainSettings:
    instrumentType: str = "EQUITY"
    region: str = "USA"
    universe: str = "TOP3000"
    dataset: str = ""  # empty = use dataset from official_datasets.json / DatasetSelector
    delay: int = 1
    decay: int = 10
    neutralization: str = "SUBINDUSTRY"
    truncation: float = 0.05
    pasteurization: str = "ON"
    unitHandling: str = "VERIFY"
    nanHandling: str = "ON"
    language: str = "FASTEXPR"
    visualization: bool = False
    type: str = "REGULAR"

    def to_platform_dict(self) -> dict[str, Any]:
        data = asdict(self)
        alpha_type = data.pop("type")
        data.pop("dataset", None)
        return {"type": alpha_type, "settings": data}


@dataclass
class ResearchBudget:
    max_candidates_per_cycle: int = 20
    max_generation_attempts: int = 5
    max_official_validations_per_cycle: int = 10
    max_official_simulations_per_cycle: int = 3
    max_official_concurrent_simulations: int = 3
    retained_alpha_pool_size: int = 10
    official_backtest_batch_size: int = 3
    min_local_quality_score: float = 4.0
    min_prior_score_for_official_validation: float = 60.0
    min_prior_score_for_official_simulation: float = 70.0
    stop_official_calls_on_rate_limit: bool = True
    run_forever: bool = False
    cycle_pause_seconds: float = 2.0
    official_retry_pause_seconds: float = 60.0
    adaptive_strategy_enabled: bool = True
    adaptive_min_official_results: int = 12
    adaptive_min_cycles: int = 20
    adaptive_min_ready_rate: float = 0.05
    max_simulation_retries: int = 1
    enable_secondary_fusion: bool = True
    require_cloud_sync: bool = True
    cloud_sync_range: str = "3d"
    cloud_sync_max_elapsed_seconds: float = 0.0
    resume_persisted_backtests: bool = True
    max_cycles: int = 10
    dataset_strategy: str = "rotate"  # all | rotate | random | specific
    generation_mode_ratio: str = "70/20/10"  # hypothesis_driven / experience_feedback / random_exploration
    hypothesis_library_dir: str = "brain_alpha_ops/research/hypotheses"
    strategy_plugins_enabled: bool = False
    strategy_plugin_specs: list[str] = field(default_factory=list)
    use_assistant_guidance: bool = True
    assistant_guidance_min_confidence: float = 0.6


@dataclass
class ScoringConfig:
    """Configurable scoring weights that accept calibrate_weights.py output."""

    prior_layer_weight: float = 0.30
    empirical_layer_weight: float = 0.45
    checklist_layer_weight: float = 0.25
    local_prior_weight: float = 0.65
    local_quality_weight: float = 0.35
    prior_weights_override: dict[str, float] | None = None
    decision_thresholds: dict[str, float] = field(
        default_factory=lambda: {"submit": 85.0, "optimize": 70.0, "research": 50.0}
    )
    assistant_guidance_score_adjustment_enabled: bool = True
    assistant_guidance_score_min_confidence: float = 0.6
    assistant_guidance_score_min_outcome_count: int = 1
    assistant_guidance_score_bonus_cap: float = 4.0
    assistant_guidance_score_penalty_cap: float = 5.0
    market_regime: str = "normal"

    def get_layer_weights(self) -> dict[str, float]:
        return {
            "prior": self.prior_layer_weight,
            "empirical": self.empirical_layer_weight,
            "checklist": self.checklist_layer_weight,
        }

    def get_local_weights(self) -> dict[str, float]:
        return {
            "prior": self.local_prior_weight,
            "quality": self.local_quality_weight,
        }


@dataclass
class QualityThresholds:
    min_sharpe: float = 1.25
    min_fitness: float = 1.0
    min_sharpe_delay0: float = 2.0
    min_fitness_delay0: float = 1.3
    min_turnover: float = 0.01
    platform_max_turnover: float = 0.70
    max_self_correlation: float = 0.70
    max_prod_correlation: float = 0.70
    max_weight_concentration: float = 0.10
    sub_universe_sharpe_min_ratio: float = 0.75
    target_max_turnover: float = 0.30
    min_margin_bps: float = 4.0
    max_drawdown: float = 0.25
    min_returns: float = 0.0
    enforce_target_turnover_as_hard_gate: bool = False
    market_regime: str = "normal"
    regime_adjustments: dict = field(
        default_factory=lambda: {
            "normal": {"sharpe_factor": 1.0, "fitness_factor": 1.0, "turnover_factor": 1.0},
            "low_vol": {"sharpe_factor": 1.15, "fitness_factor": 1.10, "turnover_factor": 0.90},
            "high_vol": {"sharpe_factor": 0.85, "fitness_factor": 0.90, "turnover_factor": 1.20},
        }
    )
    require_official_pass: bool = True
    require_official_metrics: bool = True
    require_data_compliance: bool = True
    require_economic_logic: bool = True

    @property
    def max_turnover(self) -> float:
        """Deprecated alias for platform_max_turnover."""
        return self.platform_max_turnover


@dataclass
class SubmissionPolicy:
    max_auto_submissions_per_day: int = 3
    max_auto_submissions_per_run: int = 2
    min_minutes_between_auto_submissions: int = 120
    max_expression_similarity: float = 0.90
    block_micro_variants: bool = True
    require_pre_submit_check_passed: bool = True


@dataclass
class OfficialAPIConfig:
    base_url: str = "https://api.worldquantbrain.com"
    authentication_path: str = "/authentication"
    simulations_path: str = "/simulations"
    data_sets_path: str = "/data-sets"
    data_fields_path: str = "/data-fields"
    operators_path: str = "/operators"
    alpha_path_template: str = "/alphas/{alpha_id}"
    user_alphas_path: str = "/users/self/alphas"
    alpha_check_path_template: str = "/alphas/{alpha_id}/check"
    alpha_submit_path_template: str = "/alphas/{alpha_id}/submit"
    alpha_correlations_path: str = "/alphas/correlations/check"
    user_profile_path: str = "/users/self"
    timeout_seconds: int = 60
    poll_attempts: int = 120
    poll_interval_seconds: float = 6.0
    min_request_interval_seconds: float = 3.0  # Per-request minimum; batch delay is separate
    rate_limit_retry_attempts: int = 0
    rate_limit_backoff_seconds: float = 60.0  # Aligned with BRAIN community best practice
    cache_dir: str = "data/api_cache"
    context_cache_ttl_seconds: int = 86400
    allow_stale_context_on_rate_limit: bool = False


@dataclass
class OpsConfig:
    settings: BrainSettings = field(default_factory=BrainSettings)
    budget: ResearchBudget = field(default_factory=ResearchBudget)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    thresholds: QualityThresholds = field(default_factory=QualityThresholds)
    submission_policy: SubmissionPolicy = field(default_factory=SubmissionPolicy)
    official_api: OfficialAPIConfig = field(default_factory=OfficialAPIConfig)
    storage_dir: str = "data"
    source_tag_policy: str = "official/experience/inference/manual"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CredentialConfig:
    username: str = ""
    password: str = ""
    token: str = ""
    username_env: str = "BRAIN_USERNAME"
    password_env: str = "BRAIN_PASSWORD"
    token_env: str = "BRAIN_TOKEN"

    def resolve(self) -> dict[str, str]:
        return {
            "username": self.username or os.getenv(self.username_env, ""),
            "password": self.password or os.getenv(self.password_env, ""),
            "token": self.token or os.getenv(self.token_env, ""),
        }


@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    session_ttl_seconds: int = 43200
    allow_multiple_sessions: bool = True
    allow_remote: bool = False
    secure_cookies: bool = False
    admin_token_env: str = "BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN"


@dataclass
class RunConfig:
    environment: str = "production"
    auto_submit: bool = False
    credentials: CredentialConfig = field(default_factory=CredentialConfig)
    web: WebConfig = field(default_factory=WebConfig)
    ops: OpsConfig = field(default_factory=OpsConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

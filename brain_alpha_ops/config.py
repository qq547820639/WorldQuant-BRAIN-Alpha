"""Configuration for the account-safety-first research pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
import json
import math
import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

from brain_alpha_ops.brain_api.canonical import (
    SUPPORTED_ALPHA_TYPES,
    SUPPORTED_DELAYS,
    SUPPORTED_INSTRUMENT_TYPES,
    SUPPORTED_LANGUAGES,
    SUPPORTED_NAN_HANDLING,
    SUPPORTED_NEUTRALIZATIONS,
    SUPPORTED_PASTEURIZATION,
    SUPPORTED_REGIONS,
    SUPPORTED_UNIT_HANDLING,
    SUPPORTED_UNIVERSES,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_CONFIG_PATH = PROJECT_ROOT / "config" / "run_config.json"

_VALID_ENVIRONMENTS = {"mock", "production"}
_VALID_REGIONS = SUPPORTED_REGIONS
_VALID_UNIVERSES = SUPPORTED_UNIVERSES
_VALID_DELAYS = SUPPORTED_DELAYS
_VALID_NEUTRALIZATIONS = SUPPORTED_NEUTRALIZATIONS
_VALID_ALPHA_TYPES = SUPPORTED_ALPHA_TYPES
_VALID_DATASET_STRATEGIES = {"all", "rotate", "random", "specific"}
_VALID_MARKET_REGIMES = {"normal", "low_vol", "high_vol"}
_VALID_ON_OFF = SUPPORTED_PASTEURIZATION
_VALID_UNIT_HANDLING = SUPPORTED_UNIT_HANDLING


class ConfigValidationError(ValueError):
    """Raised when run_config.json contains unsupported or unsafe values."""


def runtime_project_root() -> Path:
    """Return the persistent application root.

    PyInstaller one-file apps unpack Python modules into a temporary directory.
    Runtime data must stay next to the executable, not under the temporary
    unpack directory and not in the source checkout unless running from source.
    """
    override = os.getenv("BRAIN_ALPHA_OPS_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return PROJECT_ROOT


def default_run_config_path() -> Path:
    runtime_path = runtime_project_root() / "config" / "run_config.json"
    if runtime_path.is_file():
        return runtime_path
    return DEFAULT_RUN_CONFIG_PATH


def resolve_runtime_path(value: str | Path, *, base: Path | None = None) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str(((base or runtime_project_root()) / path).resolve())


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
        # Remove fields that BRAIN API rejects or doesn't expect
        data.pop("dataset", None)
        return {"type": alpha_type, "settings": data}


@dataclass
class ResearchBudget:
    max_candidates_per_cycle: int = 20
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
    official_retry_pause_seconds: float = 6.0
    adaptive_strategy_enabled: bool = True
    adaptive_min_official_results: int = 12
    adaptive_min_cycles: int = 20
    adaptive_min_ready_rate: float = 0.05
    max_simulation_retries: int = 1
    enable_secondary_fusion: bool = True
    require_cloud_sync: bool = True
    cloud_sync_range: str = "3d"
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
    """可配置的评分权重 — 支持 calibrate_weights.py 输出直接注入。

    所有权重均可在校准后覆盖，未覆盖的维度使用默认经验值。
    Schema version 在 scorecard 中独立追踪，不与此 dataclass 耦合。
    """
    # ── Scorecard 三层权重 ──
    prior_layer_weight: float = 0.30      # prior_score 在 total_score 中的权重
    empirical_layer_weight: float = 0.45  # empirical_score 在 total_score 中的权重
    checklist_layer_weight: float = 0.25  # submission_checklist 在 total_score 中的权重

    # ── Local convergence 权重 ──
    local_prior_weight: float = 0.65   # prior_score 在 local_rank 中的权重
    local_quality_weight: float = 0.35 # local_quality 在 local_rank 中的权重

    # ── 可覆盖的 prior 维度权重（None = 使用默认经验值） ──
    prior_weights_override: dict[str, float] | None = None

    # Assistant guidance outcome local-ranking adjustment.
    assistant_guidance_score_adjustment_enabled: bool = True
    assistant_guidance_score_min_confidence: float = 0.6
    assistant_guidance_score_min_outcome_count: int = 1
    assistant_guidance_score_bonus_cap: float = 4.0
    assistant_guidance_score_penalty_cap: float = 5.0

    # ── 市场环境分层 ──
    market_regime: str = "normal"  # "normal" | "low_vol" | "high_vol"

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
    # =========================================================================
    # All thresholds sourced from BRAIN official documentation and API responses.
    # Source: https://api.worldquantbrain.com — Alpha Check, Data Fields, Operators
    #
    # ── Platform hard gates (ERROR — must pass for BRAIN submission) ──
    #   LOW_SHARPE          : < 1.25 (Delay-1) / < 2.0 (Delay-0)
    #   LOW_FITNESS         : < 1.0  (Delay-1) / < 1.3 (Delay-0)
    #   LOW_TURNOVER        : < 1%
    #   HIGH_TURNOVER       : > 70%        ← platform_max_turnover
    #   CONCENTRATED_WEIGHT : single stock > 10%
    #   SELF_CORRELATION    : >= 0.70 (with Sharpe × 1.10 exception rule)
    #   LOW_SUB_UNIVERSE_SHARPE : sub_sharpe < 0.75 × √(sub/alpha) × sharpe
    #
    # ── Quality targets (WARNING — guide optimization & submission priority) ──
    #   Turnover < 30%  — target_max_turnover, 稳健 alpha 建议上限
    #   Margin  >= 4.0 bps — min_margin_bps
    #
    #   Drawdown is NOT a BRAIN hard check — qualitative guidance only.
    # =========================================================================
    # Platform hard gates (BRAIN API Alpha Check)
    min_sharpe: float = 1.25              # BRAIN: LOW_SHARPE if < 1.25 (Delay-1)
    min_fitness: float = 1.0              # BRAIN: LOW_FITNESS if < 1.0  (Delay-1)
    min_sharpe_delay0: float = 2.0        # BRAIN: LOW_SHARPE if < 2.0 (Delay-0)
    min_fitness_delay0: float = 1.3       # BRAIN: LOW_FITNESS if < 1.3 (Delay-0)
    min_turnover: float = 0.01            # BRAIN: LOW_TURNOVER if < 1%
    platform_max_turnover: float = 0.70   # BRAIN: HIGH_TURNOVER if > 70% (平台硬门槛)
    max_self_correlation: float = 0.70    # BRAIN: SELF_CORRELATION if >= 0.70 (PnL correlation)
    max_prod_correlation: float = 0.70    # derived from BRAIN SELF_CORRELATION standard
    max_weight_concentration: float = 0.10 # BRAIN: CONCENTRATED_WEIGHT if single stock > 10%
    sub_universe_sharpe_min_ratio: float = 0.75  # BRAIN: LOW_SUB_UNIVERSE_SHARPE formula factor
    # Quality targets (advisor standard — WARNING, not hard gate)
    target_max_turnover: float = 0.30     # 顾问标准: Turnover < 30% 优先提交; 30%-70% 需优化
    min_margin_bps: float = 4.0           # 顾问标准: minimum margin in basis points
    max_drawdown: float = 0.25            # qualitative — NOT a BRAIN hard check; guidance only
    min_returns: float = 0.0              # qualitative — positive returns expected
    # ── Turnover 策略控制 ──
    # enforce_target_turnover_as_hard_gate: True → turnover_quality (≤30%) 升级为硬门禁
    #   （与 BRAIN 官方 70% 标准不同的自定义强化约束）
    #   False (default) → turnover_quality 为 WARNING 级，仅标记不阻断
    enforce_target_turnover_as_hard_gate: bool = False
    # ── 市场环境分层调整 ──
    market_regime: str = "normal"         # "normal" | "low_vol" | "high_vol"
    #
    # 调整说明：高波动环境下 Sharpe 往往被压低、turnover 偏高。
    # 低波动环境下 Sharpe 可能虚高。regime_adjustments 仅作为本地归因/
    # 校准元数据，不能改变 BRAIN 官方硬门槛。
    regime_adjustments: dict = field(default_factory=lambda: {
        "normal": {"sharpe_factor": 1.0, "fitness_factor": 1.0, "turnover_factor": 1.0},
        "low_vol": {"sharpe_factor": 1.15, "fitness_factor": 1.10, "turnover_factor": 0.90},
        "high_vol": {"sharpe_factor": 0.85, "fitness_factor": 0.90, "turnover_factor": 1.20},
    })
    # Operational
    require_official_pass: bool = True
    require_official_metrics: bool = True
    require_data_compliance: bool = True
    require_economic_logic: bool = True

    # Backward-compat aliases (deprecated — prefer platform_max_turnover / target_max_turnover)
    @property
    def max_turnover(self) -> float:
        """Deprecated alias → platform_max_turnover (BRAIN hard gate 0.70)."""
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
    alpha_correlations_path: str = "/alphas/correlations/check"  # P2: PROD_CORRELATION check
    user_profile_path: str = "/users/self"  # User profile — tier, level, points, consultant status
    timeout_seconds: int = 60
    poll_attempts: int = 120
    poll_interval_seconds: float = 6.0
    min_request_interval_seconds: float = 3.0
    rate_limit_retry_attempts: int = 0
    rate_limit_backoff_seconds: float = 15.0
    cache_dir: str = "data/api_cache"
    context_cache_ttl_seconds: int = 86400
    allow_stale_context_on_rate_limit: bool = True


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
    # Keep these empty in normal use. Prefer environment variables for secrets.
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


@dataclass
class RunConfig:
    environment: str = "production"
    auto_submit: bool = False
    credentials: CredentialConfig = field(default_factory=CredentialConfig)
    web: WebConfig = field(default_factory=WebConfig)
    ops: OpsConfig = field(default_factory=OpsConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_run_config(path: str | Path | None = None) -> RunConfig:
    config_path = Path(path) if path else default_run_config_path()
    if not config_path.exists():
        return _normalize_runtime_paths(validate_run_config(RunConfig()))
    data = json.loads(config_path.read_text(encoding="utf-8"))
    config = _update_dataclass(RunConfig(), data)
    return _normalize_runtime_paths(validate_run_config(config))


def load_ops_config(path: str | Path | None = None) -> OpsConfig:
    return load_run_config(path).ops


def write_run_config(config: RunConfig, path: str | Path | None = None) -> Path:
    validate_run_config(config)
    config_path = Path(path) if path else default_run_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def validate_run_config(config: RunConfig) -> RunConfig:
    """Validate the supported run configuration surface.

    The loader intentionally ignores unknown JSON keys for forward
    compatibility, but known keys must keep the types and ranges expected by
    the pipeline, web console, and official API adapter.
    """
    if not isinstance(config, RunConfig):
        raise ConfigValidationError("run_config must be a RunConfig instance")

    errors: list[str] = []
    _require_enum(errors, "environment", config.environment, _VALID_ENVIRONMENTS)
    _require_bool(errors, "auto_submit", config.auto_submit)
    _validate_credentials(errors, config.credentials)
    _validate_web(errors, config.web)
    _validate_ops(errors, config.ops)
    if errors:
        raise ConfigValidationError("Invalid run configuration: " + "; ".join(errors))
    return config


def _validate_credentials(errors: list[str], credentials: CredentialConfig) -> None:
    if not isinstance(credentials, CredentialConfig):
        errors.append("credentials must be an object")
        return
    for field_name in ("username", "password", "token", "username_env", "password_env", "token_env"):
        _require_str(errors, f"credentials.{field_name}", getattr(credentials, field_name))


def _validate_web(errors: list[str], web: WebConfig) -> None:
    if not isinstance(web, WebConfig):
        errors.append("web must be an object")
        return
    _require_str(errors, "web.host", web.host, allow_empty=False)
    _require_int_range(errors, "web.port", web.port, min_value=1, max_value=65535)
    _require_bool(errors, "web.open_browser", web.open_browser)
    _require_int_range(errors, "web.session_ttl_seconds", web.session_ttl_seconds, min_value=60)
    _require_bool(errors, "web.allow_multiple_sessions", web.allow_multiple_sessions)
    _require_bool(errors, "web.allow_remote", web.allow_remote)


def _validate_ops(errors: list[str], ops: OpsConfig) -> None:
    if not isinstance(ops, OpsConfig):
        errors.append("ops must be an object")
        return
    _validate_settings(errors, ops.settings)
    _validate_budget(errors, ops.budget)
    _validate_scoring(errors, ops.scoring)
    _validate_thresholds(errors, ops.thresholds)
    _validate_submission_policy(errors, ops.submission_policy)
    _validate_official_api(errors, ops.official_api)
    _require_str(errors, "ops.storage_dir", ops.storage_dir, allow_empty=False)
    _require_str(errors, "ops.source_tag_policy", ops.source_tag_policy, allow_empty=False)


def _validate_settings(errors: list[str], settings: BrainSettings) -> None:
    if not isinstance(settings, BrainSettings):
        errors.append("ops.settings must be an object")
        return
    _require_enum(errors, "ops.settings.instrumentType", settings.instrumentType, SUPPORTED_INSTRUMENT_TYPES)
    _require_enum(errors, "ops.settings.region", settings.region, _VALID_REGIONS)
    _require_enum(errors, "ops.settings.universe", settings.universe, _VALID_UNIVERSES)
    _require_str(errors, "ops.settings.dataset", settings.dataset)
    _require_enum(errors, "ops.settings.delay", settings.delay, _VALID_DELAYS)
    _require_int_range(errors, "ops.settings.decay", settings.decay, min_value=0)
    _require_enum(errors, "ops.settings.neutralization", settings.neutralization, _VALID_NEUTRALIZATIONS)
    _require_float_range(errors, "ops.settings.truncation", settings.truncation, min_value=0.0, max_value=1.0)
    _require_enum(errors, "ops.settings.pasteurization", settings.pasteurization, _VALID_ON_OFF)
    _require_enum(errors, "ops.settings.unitHandling", settings.unitHandling, _VALID_UNIT_HANDLING)
    _require_enum(errors, "ops.settings.nanHandling", settings.nanHandling, SUPPORTED_NAN_HANDLING)
    _require_enum(errors, "ops.settings.language", settings.language, SUPPORTED_LANGUAGES)
    _require_bool(errors, "ops.settings.visualization", settings.visualization)
    _require_enum(errors, "ops.settings.type", settings.type, _VALID_ALPHA_TYPES)


def _validate_budget(errors: list[str], budget: ResearchBudget) -> None:
    if not isinstance(budget, ResearchBudget):
        errors.append("ops.budget must be an object")
        return
    for field_name in (
        "max_candidates_per_cycle",
        "max_official_concurrent_simulations",
        "retained_alpha_pool_size",
        "official_backtest_batch_size",
    ):
        _require_int_range(errors, f"ops.budget.{field_name}", getattr(budget, field_name), min_value=1)
    for field_name in (
        "max_official_validations_per_cycle",
        "max_official_simulations_per_cycle",
        "adaptive_min_official_results",
        "adaptive_min_cycles",
        "max_simulation_retries",
        "max_cycles",
    ):
        _require_int_range(errors, f"ops.budget.{field_name}", getattr(budget, field_name), min_value=0)
    for field_name in (
        "min_local_quality_score",
        "min_prior_score_for_official_validation",
        "min_prior_score_for_official_simulation",
        "cycle_pause_seconds",
        "official_retry_pause_seconds",
    ):
        _require_float_range(errors, f"ops.budget.{field_name}", getattr(budget, field_name), min_value=0.0)
    for field_name in (
        "stop_official_calls_on_rate_limit",
        "run_forever",
        "adaptive_strategy_enabled",
        "enable_secondary_fusion",
        "require_cloud_sync",
        "resume_persisted_backtests",
        "strategy_plugins_enabled",
        "use_assistant_guidance",
    ):
        _require_bool(errors, f"ops.budget.{field_name}", getattr(budget, field_name))
    _require_float_range(errors, "ops.budget.adaptive_min_ready_rate", budget.adaptive_min_ready_rate, min_value=0.0, max_value=1.0)
    _require_enum(errors, "ops.budget.dataset_strategy", budget.dataset_strategy, _VALID_DATASET_STRATEGIES)
    _validate_generation_mode_ratio(errors, budget.generation_mode_ratio)
    _require_str(errors, "ops.budget.hypothesis_library_dir", budget.hypothesis_library_dir)
    _require_string_list(errors, "ops.budget.strategy_plugin_specs", budget.strategy_plugin_specs)
    _require_str(errors, "ops.budget.cloud_sync_range", budget.cloud_sync_range, allow_empty=False)
    _require_float_range(
        errors,
        "ops.budget.assistant_guidance_min_confidence",
        budget.assistant_guidance_min_confidence,
        min_value=0.0,
        max_value=1.0,
    )


def _validate_scoring(errors: list[str], scoring: ScoringConfig) -> None:
    if not isinstance(scoring, ScoringConfig):
        errors.append("ops.scoring must be an object")
        return
    _validate_weight_group(
        errors,
        "ops.scoring.layer_weights",
        {
            "prior_layer_weight": scoring.prior_layer_weight,
            "empirical_layer_weight": scoring.empirical_layer_weight,
            "checklist_layer_weight": scoring.checklist_layer_weight,
        },
    )
    _validate_weight_group(
        errors,
        "ops.scoring.local_weights",
        {
            "local_prior_weight": scoring.local_prior_weight,
            "local_quality_weight": scoring.local_quality_weight,
        },
    )
    if scoring.prior_weights_override is not None:
        if not isinstance(scoring.prior_weights_override, dict):
            errors.append("ops.scoring.prior_weights_override must be an object or null")
        else:
            for key, value in scoring.prior_weights_override.items():
                _require_str(errors, "ops.scoring.prior_weights_override key", key, allow_empty=False)
                _require_float_range(
                    errors,
                    f"ops.scoring.prior_weights_override.{key}",
                    value,
                    min_value=0.0,
                )
    _require_bool(
        errors,
        "ops.scoring.assistant_guidance_score_adjustment_enabled",
        scoring.assistant_guidance_score_adjustment_enabled,
    )
    _require_float_range(
        errors,
        "ops.scoring.assistant_guidance_score_min_confidence",
        scoring.assistant_guidance_score_min_confidence,
        min_value=0.0,
        max_value=1.0,
    )
    _require_int_range(
        errors,
        "ops.scoring.assistant_guidance_score_min_outcome_count",
        scoring.assistant_guidance_score_min_outcome_count,
        min_value=0,
    )
    _require_float_range(
        errors,
        "ops.scoring.assistant_guidance_score_bonus_cap",
        scoring.assistant_guidance_score_bonus_cap,
        min_value=0.0,
    )
    _require_float_range(
        errors,
        "ops.scoring.assistant_guidance_score_penalty_cap",
        scoring.assistant_guidance_score_penalty_cap,
        min_value=0.0,
    )
    _require_enum(errors, "ops.scoring.market_regime", scoring.market_regime, _VALID_MARKET_REGIMES)


def _validate_thresholds(errors: list[str], thresholds: QualityThresholds) -> None:
    if not isinstance(thresholds, QualityThresholds):
        errors.append("ops.thresholds must be an object")
        return
    for field_name in (
        "min_sharpe",
        "min_fitness",
        "min_sharpe_delay0",
        "min_fitness_delay0",
        "min_margin_bps",
    ):
        _require_float_range(errors, f"ops.thresholds.{field_name}", getattr(thresholds, field_name), min_value=0.0)
    for field_name in (
        "min_turnover",
        "platform_max_turnover",
        "max_self_correlation",
        "max_prod_correlation",
        "max_weight_concentration",
        "sub_universe_sharpe_min_ratio",
        "target_max_turnover",
        "max_drawdown",
    ):
        _require_float_range(
            errors,
            f"ops.thresholds.{field_name}",
            getattr(thresholds, field_name),
            min_value=0.0,
            max_value=1.0,
        )
    _require_float(errors, "ops.thresholds.min_returns", thresholds.min_returns)
    _require_bool(
        errors,
        "ops.thresholds.enforce_target_turnover_as_hard_gate",
        thresholds.enforce_target_turnover_as_hard_gate,
    )
    _require_enum(errors, "ops.thresholds.market_regime", thresholds.market_regime, _VALID_MARKET_REGIMES)
    _validate_regime_adjustments(errors, thresholds.regime_adjustments)
    for field_name in (
        "require_official_pass",
        "require_official_metrics",
        "require_data_compliance",
        "require_economic_logic",
    ):
        _require_bool(errors, f"ops.thresholds.{field_name}", getattr(thresholds, field_name))


def _validate_submission_policy(errors: list[str], policy: SubmissionPolicy) -> None:
    if not isinstance(policy, SubmissionPolicy):
        errors.append("ops.submission_policy must be an object")
        return
    for field_name in (
        "max_auto_submissions_per_day",
        "max_auto_submissions_per_run",
        "min_minutes_between_auto_submissions",
    ):
        _require_int_range(errors, f"ops.submission_policy.{field_name}", getattr(policy, field_name), min_value=0)
    _require_float_range(
        errors,
        "ops.submission_policy.max_expression_similarity",
        policy.max_expression_similarity,
        min_value=0.0,
        max_value=1.0,
    )
    _require_bool(errors, "ops.submission_policy.block_micro_variants", policy.block_micro_variants)
    _require_bool(
        errors,
        "ops.submission_policy.require_pre_submit_check_passed",
        policy.require_pre_submit_check_passed,
    )


def _validate_official_api(errors: list[str], api: OfficialAPIConfig) -> None:
    if not isinstance(api, OfficialAPIConfig):
        errors.append("ops.official_api must be an object")
        return
    _validate_http_url(errors, "ops.official_api.base_url", api.base_url)
    for field_name in (
        "authentication_path",
        "simulations_path",
        "data_sets_path",
        "data_fields_path",
        "operators_path",
        "alpha_path_template",
        "user_alphas_path",
        "alpha_check_path_template",
        "alpha_submit_path_template",
        "alpha_correlations_path",
        "user_profile_path",
    ):
        _require_api_path(errors, f"ops.official_api.{field_name}", getattr(api, field_name))
    for field_name in ("timeout_seconds", "poll_attempts", "rate_limit_retry_attempts", "context_cache_ttl_seconds"):
        _require_int_range(errors, f"ops.official_api.{field_name}", getattr(api, field_name), min_value=0)
    for field_name in (
        "poll_interval_seconds",
        "min_request_interval_seconds",
        "rate_limit_backoff_seconds",
    ):
        _require_float_range(errors, f"ops.official_api.{field_name}", getattr(api, field_name), min_value=0.0)
    _require_str(errors, "ops.official_api.cache_dir", api.cache_dir, allow_empty=False)
    _require_bool(
        errors,
        "ops.official_api.allow_stale_context_on_rate_limit",
        api.allow_stale_context_on_rate_limit,
    )


def _require_str(errors: list[str], name: str, value: Any, *, allow_empty: bool = True) -> None:
    if not isinstance(value, str):
        errors.append(f"{name} must be a string")
        return
    if not allow_empty and not value.strip():
        errors.append(f"{name} must not be empty")


def _require_string_list(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, list):
        errors.append(f"{name} must be a list")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{name}[{index}] must be a non-empty string")


def _require_bool(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, bool):
        errors.append(f"{name} must be a boolean")


def _require_int_range(
    errors: list[str],
    name: str,
    value: Any,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"{name} must be an integer")
        return
    if min_value is not None and value < min_value:
        errors.append(f"{name} must be >= {min_value}")
    if max_value is not None and value > max_value:
        errors.append(f"{name} must be <= {max_value}")


def _require_float(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        errors.append(f"{name} must be a finite number")


def _require_float_range(
    errors: list[str],
    name: str,
    value: Any,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{name} must be a number")
        return
    numeric = float(value)
    if not math.isfinite(numeric):
        errors.append(f"{name} must be finite")
        return
    if min_value is not None and numeric < min_value:
        errors.append(f"{name} must be >= {min_value}")
    if max_value is not None and numeric > max_value:
        errors.append(f"{name} must be <= {max_value}")


def _require_enum(errors: list[str], name: str, value: Any, allowed: set[Any]) -> None:
    if isinstance(value, bool):
        errors.append(f"{name} must be one of {sorted(allowed)}")
        return
    if value not in allowed:
        errors.append(f"{name} must be one of {sorted(allowed)}")


def _validate_generation_mode_ratio(errors: list[str], value: Any) -> None:
    name = "ops.budget.generation_mode_ratio"
    if not isinstance(value, str):
        errors.append(f"{name} must be a string like '70/20/10'")
        return
    parts = value.split("/")
    if len(parts) != 3:
        errors.append(f"{name} must contain three slash-separated non-negative numbers")
        return
    total = 0.0
    for part in parts:
        try:
            numeric = float(part)
        except (TypeError, ValueError):
            errors.append(f"{name} must contain only numbers")
            return
        if not math.isfinite(numeric) or numeric < 0:
            errors.append(f"{name} values must be finite and >= 0")
            return
        total += numeric
    if total <= 0:
        errors.append(f"{name} must have a positive total")


def _validate_weight_group(errors: list[str], group_name: str, weights: dict[str, Any]) -> None:
    total = 0.0
    valid = True
    for field_name, value in weights.items():
        before = len(errors)
        _require_float_range(errors, f"{group_name}.{field_name}", value, min_value=0.0)
        if len(errors) != before:
            valid = False
            continue
        total += float(value)
    if valid and total <= 0:
        errors.append(f"{group_name} must have a positive total weight")


def _validate_regime_adjustments(errors: list[str], value: Any) -> None:
    if not isinstance(value, dict):
        errors.append("ops.thresholds.regime_adjustments must be an object")
        return
    for regime, adjustments in value.items():
        if regime not in _VALID_MARKET_REGIMES:
            errors.append(f"ops.thresholds.regime_adjustments has unsupported regime: {regime}")
            continue
        if not isinstance(adjustments, dict):
            errors.append(f"ops.thresholds.regime_adjustments.{regime} must be an object")
            continue
        for factor_name in ("sharpe_factor", "fitness_factor", "turnover_factor"):
            if factor_name in adjustments:
                _require_float_range(
                    errors,
                    f"ops.thresholds.regime_adjustments.{regime}.{factor_name}",
                    adjustments[factor_name],
                    min_value=0.0,
                )


def _validate_http_url(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{name} must be a non-empty URL")
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append(f"{name} must be an http(s) URL")


def _require_api_path(errors: list[str], name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.startswith("/"):
        errors.append(f"{name} must start with '/'")


def _normalize_runtime_paths(config: RunConfig, base: Path | None = None) -> RunConfig:
    base = (base or runtime_project_root()).resolve()
    config.ops.storage_dir = resolve_runtime_path(config.ops.storage_dir, base=base)
    config.ops.official_api.cache_dir = resolve_runtime_path(config.ops.official_api.cache_dir, base=base)
    if config.ops.budget.hypothesis_library_dir:
        config.ops.budget.hypothesis_library_dir = resolve_runtime_path(
            config.ops.budget.hypothesis_library_dir,
            base=base,
        )
    return config


def _update_dataclass(instance, data: dict[str, Any]):
    if not isinstance(data, dict):
        return instance
    known = {item.name for item in fields(instance)}
    for key, value in data.items():
        if key not in known:
            continue
        current = getattr(instance, key)
        if is_dataclass(current) and isinstance(value, dict):
            setattr(instance, key, _update_dataclass(current, value))
        else:
            setattr(instance, key, value)
    return instance

"""Domain-level validation for runtime configuration models."""

from __future__ import annotations

import os

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
from brain_alpha_ops.config_models import (
    BrainSettings,
    CredentialConfig,
    OfficialAPIConfig,
    OpsConfig,
    QualityThresholds,
    ResearchBudget,
    ScoringConfig,
    SubmissionPolicy,
    WebConfig,
)
from brain_alpha_ops.config_validation_helpers import (
    require_api_path,
    require_bool,
    require_enum,
    require_float,
    require_float_range,
    require_int_range,
    require_str,
    require_string_list,
    validate_decision_thresholds,
    validate_generation_mode_ratio,
    validate_http_url,
    validate_regime_adjustments,
    validate_weight_group,
)

_VALID_ENVIRONMENT = "production"
_VALID_REGIONS = SUPPORTED_REGIONS
_VALID_UNIVERSES = SUPPORTED_UNIVERSES
_VALID_DELAYS = SUPPORTED_DELAYS
_VALID_NEUTRALIZATIONS = SUPPORTED_NEUTRALIZATIONS
_VALID_ALPHA_TYPES = SUPPORTED_ALPHA_TYPES
_VALID_DATASET_STRATEGIES = {"all", "rotate", "random", "specific", "fixed", "locked"}
_VALID_MARKET_REGIMES = {"normal", "low_vol", "high_vol"}
_VALID_ON_OFF = SUPPORTED_PASTEURIZATION
_VALID_UNIT_HANDLING = SUPPORTED_UNIT_HANDLING


def validate_credentials(errors: list[str], credentials: CredentialConfig) -> None:
    if not isinstance(credentials, CredentialConfig):
        errors.append("credentials must be an object")
        return
    for field_name in ("username", "password", "token", "username_env", "password_env", "token_env"):
        require_str(errors, f"credentials.{field_name}", getattr(credentials, field_name))
    _reject_plaintext_credentials(errors, credentials)


def _reject_plaintext_credentials(errors: list[str], credentials: CredentialConfig) -> None:
    """Reject non-empty plaintext credentials unless BRAIN_ALLOW_PLAINTEXT_CREDENTIALS is set."""
    if os.environ.get("BRAIN_ALLOW_PLAINTEXT_CREDENTIALS"):
        return
    for field_name in ("username", "password", "token"):
        value = getattr(credentials, field_name)
        if value:
            errors.append(
                f"credentials.{field_name} contains a non-empty plaintext value; "
                "set it via the *_env field and environment variable instead, "
                "or set BRAIN_ALLOW_PLAINTEXT_CREDENTIALS=1 to override"
            )


def validate_web(errors: list[str], web: WebConfig) -> None:
    if not isinstance(web, WebConfig):
        errors.append("web must be an object")
        return
    require_str(errors, "web.host", web.host, allow_empty=False)
    require_int_range(errors, "web.port", web.port, min_value=1, max_value=65535)
    require_bool(errors, "web.open_browser", web.open_browser)
    require_int_range(errors, "web.session_ttl_seconds", web.session_ttl_seconds, min_value=60)
    require_bool(errors, "web.allow_multiple_sessions", web.allow_multiple_sessions)
    require_bool(errors, "web.allow_remote", web.allow_remote)
    require_bool(errors, "web.secure_cookies", web.secure_cookies)
    require_str(errors, "web.admin_token_env", web.admin_token_env, allow_empty=False)


def validate_ops(errors: list[str], ops: OpsConfig) -> None:
    if not isinstance(ops, OpsConfig):
        errors.append("ops must be an object")
        return
    validate_settings(errors, ops.settings)
    validate_budget(errors, ops.budget)
    validate_scoring(errors, ops.scoring)
    validate_thresholds(errors, ops.thresholds)
    validate_submission_policy(errors, ops.submission_policy)
    validate_official_api(errors, ops.official_api)
    require_str(errors, "ops.storage_dir", ops.storage_dir, allow_empty=False)
    require_str(errors, "ops.source_tag_policy", ops.source_tag_policy, allow_empty=False)


def validate_settings(errors: list[str], settings: BrainSettings) -> None:
    if not isinstance(settings, BrainSettings):
        errors.append("ops.settings must be an object")
        return
    require_enum(errors, "ops.settings.instrumentType", settings.instrumentType, SUPPORTED_INSTRUMENT_TYPES)
    require_enum(errors, "ops.settings.region", settings.region, _VALID_REGIONS)
    require_enum(errors, "ops.settings.universe", settings.universe, _VALID_UNIVERSES)
    require_str(errors, "ops.settings.dataset", settings.dataset, allow_empty=False)
    require_enum(errors, "ops.settings.delay", settings.delay, _VALID_DELAYS)
    require_int_range(errors, "ops.settings.decay", settings.decay, min_value=0)
    require_enum(errors, "ops.settings.neutralization", settings.neutralization, _VALID_NEUTRALIZATIONS)
    require_float_range(errors, "ops.settings.truncation", settings.truncation, min_value=0.0, max_value=1.0)
    require_enum(errors, "ops.settings.pasteurization", settings.pasteurization, _VALID_ON_OFF)
    require_enum(errors, "ops.settings.unitHandling", settings.unitHandling, _VALID_UNIT_HANDLING)
    require_enum(errors, "ops.settings.nanHandling", settings.nanHandling, SUPPORTED_NAN_HANDLING)
    require_enum(errors, "ops.settings.language", settings.language, SUPPORTED_LANGUAGES)
    require_bool(errors, "ops.settings.visualization", settings.visualization)
    require_enum(errors, "ops.settings.type", settings.type, _VALID_ALPHA_TYPES)


def validate_budget(errors: list[str], budget: ResearchBudget) -> None:
    if not isinstance(budget, ResearchBudget):
        errors.append("ops.budget must be an object")
        return
    for field_name in (
        "max_candidates_per_cycle",
        "max_official_concurrent_simulations",
        "retained_alpha_pool_size",
        "official_backtest_batch_size",
    ):
        require_int_range(errors, f"ops.budget.{field_name}", getattr(budget, field_name), min_value=1)
    for field_name in (
        "max_official_validations_per_cycle",
        "max_official_simulations_per_cycle",
        "adaptive_min_official_results",
        "adaptive_min_cycles",
        "max_simulation_retries",
        "max_cycles",
    ):
        require_int_range(errors, f"ops.budget.{field_name}", getattr(budget, field_name), min_value=0)
    for field_name in (
        "min_local_quality_score",
        "min_prior_score_for_official_validation",
        "min_prior_score_for_official_simulation",
        "cycle_pause_seconds",
        "official_retry_pause_seconds",
    ):
        require_float_range(errors, f"ops.budget.{field_name}", getattr(budget, field_name), min_value=0.0)
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
        require_bool(errors, f"ops.budget.{field_name}", getattr(budget, field_name))
    require_float_range(
        errors,
        "ops.budget.adaptive_min_ready_rate",
        budget.adaptive_min_ready_rate,
        min_value=0.0,
        max_value=1.0,
    )
    require_enum(errors, "ops.budget.dataset_strategy", budget.dataset_strategy, _VALID_DATASET_STRATEGIES)
    validate_generation_mode_ratio(errors, budget.generation_mode_ratio)
    require_str(errors, "ops.budget.hypothesis_library_dir", budget.hypothesis_library_dir)
    require_string_list(errors, "ops.budget.strategy_plugin_specs", budget.strategy_plugin_specs)
    require_str(errors, "ops.budget.cloud_sync_range", budget.cloud_sync_range, allow_empty=False)
    require_float_range(
        errors,
        "ops.budget.assistant_guidance_min_confidence",
        budget.assistant_guidance_min_confidence,
        min_value=0.0,
        max_value=1.0,
    )


def validate_scoring(errors: list[str], scoring: ScoringConfig) -> None:
    if not isinstance(scoring, ScoringConfig):
        errors.append("ops.scoring must be an object")
        return
    validate_weight_group(
        errors,
        "ops.scoring.layer_weights",
        {
            "prior_layer_weight": scoring.prior_layer_weight,
            "empirical_layer_weight": scoring.empirical_layer_weight,
            "checklist_layer_weight": scoring.checklist_layer_weight,
        },
    )
    validate_weight_group(
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
                require_str(errors, "ops.scoring.prior_weights_override key", key, allow_empty=False)
                require_float_range(
                    errors,
                    f"ops.scoring.prior_weights_override.{key}",
                    value,
                    min_value=0.0,
                )
    validate_decision_thresholds(errors, scoring.decision_thresholds)
    require_bool(
        errors,
        "ops.scoring.assistant_guidance_score_adjustment_enabled",
        scoring.assistant_guidance_score_adjustment_enabled,
    )
    require_float_range(
        errors,
        "ops.scoring.assistant_guidance_score_min_confidence",
        scoring.assistant_guidance_score_min_confidence,
        min_value=0.0,
        max_value=1.0,
    )
    require_int_range(
        errors,
        "ops.scoring.assistant_guidance_score_min_outcome_count",
        scoring.assistant_guidance_score_min_outcome_count,
        min_value=0,
    )
    require_float_range(
        errors,
        "ops.scoring.assistant_guidance_score_bonus_cap",
        scoring.assistant_guidance_score_bonus_cap,
        min_value=0.0,
    )
    require_float_range(
        errors,
        "ops.scoring.assistant_guidance_score_penalty_cap",
        scoring.assistant_guidance_score_penalty_cap,
        min_value=0.0,
    )
    require_enum(errors, "ops.scoring.market_regime", scoring.market_regime, _VALID_MARKET_REGIMES)


def validate_thresholds(errors: list[str], thresholds: QualityThresholds) -> None:
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
        require_float_range(errors, f"ops.thresholds.{field_name}", getattr(thresholds, field_name), min_value=0.0)
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
        require_float_range(
            errors,
            f"ops.thresholds.{field_name}",
            getattr(thresholds, field_name),
            min_value=0.0,
            max_value=1.0,
        )
    require_float(errors, "ops.thresholds.min_returns", thresholds.min_returns)
    require_bool(
        errors,
        "ops.thresholds.enforce_target_turnover_as_hard_gate",
        thresholds.enforce_target_turnover_as_hard_gate,
    )
    require_enum(errors, "ops.thresholds.market_regime", thresholds.market_regime, _VALID_MARKET_REGIMES)
    validate_regime_adjustments(errors, thresholds.regime_adjustments, _VALID_MARKET_REGIMES)
    for field_name in (
        "require_official_pass",
        "require_official_metrics",
        "require_data_compliance",
        "require_economic_logic",
    ):
        require_bool(errors, f"ops.thresholds.{field_name}", getattr(thresholds, field_name))


def validate_submission_policy(errors: list[str], policy: SubmissionPolicy) -> None:
    if not isinstance(policy, SubmissionPolicy):
        errors.append("ops.submission_policy must be an object")
        return
    for field_name in (
        "max_auto_submissions_per_day",
        "max_auto_submissions_per_run",
        "min_minutes_between_auto_submissions",
    ):
        require_int_range(errors, f"ops.submission_policy.{field_name}", getattr(policy, field_name), min_value=0)
    require_float_range(
        errors,
        "ops.submission_policy.max_expression_similarity",
        policy.max_expression_similarity,
        min_value=0.0,
        max_value=1.0,
    )
    require_bool(errors, "ops.submission_policy.block_micro_variants", policy.block_micro_variants)
    require_bool(
        errors,
        "ops.submission_policy.require_pre_submit_check_passed",
        policy.require_pre_submit_check_passed,
    )


def validate_official_api(errors: list[str], api: OfficialAPIConfig) -> None:
    if not isinstance(api, OfficialAPIConfig):
        errors.append("ops.official_api must be an object")
        return
    validate_http_url(errors, "ops.official_api.base_url", api.base_url, require_https=True)
    for field_name in (
        "authentication_path",
        "simulations_path",
        "data_categories_path",
        "data_sets_path",
        "data_set_path_template",
        "data_fields_path",
        "data_field_path_template",
        "operators_path",
        "alpha_path_template",
        "user_alphas_path",
        "alpha_check_path_template",
        "alpha_submit_path_template",
        "alpha_correlations_path",
        "user_profile_path",
    ):
        require_api_path(errors, f"ops.official_api.{field_name}", getattr(api, field_name))
    for field_name in ("timeout_seconds", "poll_attempts", "rate_limit_retry_attempts", "context_cache_ttl_seconds"):
        require_int_range(errors, f"ops.official_api.{field_name}", getattr(api, field_name), min_value=0)
    for field_name in (
        "poll_interval_seconds",
        "min_request_interval_seconds",
        "rate_limit_backoff_seconds",
    ):
        require_float_range(errors, f"ops.official_api.{field_name}", getattr(api, field_name), min_value=0.0)
    require_str(errors, "ops.official_api.cache_dir", api.cache_dir, allow_empty=False)
    require_str(errors, "ops.official_api.data_fields_dataset_query_key", api.data_fields_dataset_query_key, allow_empty=False)
    if str(api.data_fields_dataset_query_key) not in {"dataset", "dataset.id"}:
        errors.append("ops.official_api.data_fields_dataset_query_key must be 'dataset' or 'dataset.id'")
    require_bool(
        errors,
        "ops.official_api.allow_stale_context_on_rate_limit",
        api.allow_stale_context_on_rate_limit,
    )

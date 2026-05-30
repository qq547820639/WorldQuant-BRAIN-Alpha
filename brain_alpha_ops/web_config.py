"""Payload parsing and validation for the local web console."""

from __future__ import annotations

import math

from typing import Any, Callable

from brain_alpha_ops.brain_api.canonical import (
    SUPPORTED_ALPHA_TYPES,
    SUPPORTED_DELAYS,
    SUPPORTED_NEUTRALIZATIONS,
    SUPPORTED_REGIONS,
    SUPPORTED_UNIVERSES,
)
from brain_alpha_ops.config import (
    BrainSettings,
    OpsConfig,
    ResearchBudget,
    RunConfig,
    load_run_config,
    validate_run_config,
    write_run_config,
)


# Allowed base URLs for user-facing web payloads; production is the only
# runtime environment exposed by the web console.
_ALLOWED_BASE_URLS: dict[str, set[str]] = {
    "production": {"https://api.worldquantbrain.com"},
}

# Upper bounds for web payload numeric parameters.
_MAX_CANDIDATES = 1000
_MAX_VALIDATIONS = 100
_MAX_SIMULATIONS = 100
_MAX_CONCURRENT_SIMULATIONS = 20
_MAX_POOL_SIZE = 5000
_MAX_CYCLES = 10000
_MAX_CYCLE_PAUSE_SECONDS = 3600
_MAX_BACKTEST_BATCH_SIZE = 100

_VALID_REGIONS = SUPPORTED_REGIONS
_VALID_UNIVERSES = SUPPORTED_UNIVERSES
_VALID_DELAYS = SUPPORTED_DELAYS
_VALID_NEUTRALIZATIONS = SUPPORTED_NEUTRALIZATIONS
_VALID_TYPES = SUPPORTED_ALPHA_TYPES


RunConfigLoader = Callable[[], RunConfig]
RunConfigWriter = Callable[[RunConfig], object]


def config_from_payload(payload: dict, *, loader: RunConfigLoader = load_run_config) -> OpsConfig:
    return run_config_from_payload(payload, loader=loader).ops


def public_run_config_dict(config: RunConfig) -> dict[str, Any]:
    data = config.to_dict()
    credentials = data.get("credentials", {})
    data["credentials"] = {
        "username": "",
        "password": "",
        "token": "",
        "username_env": credentials.get("username_env", "BRAIN_USERNAME"),
        "password_env": credentials.get("password_env", "BRAIN_PASSWORD"),
        "token_env": credentials.get("token_env", "BRAIN_TOKEN"),
    }
    return data


def save_run_config_payload(
    payload: dict,
    *,
    loader: RunConfigLoader = load_run_config,
    writer: RunConfigWriter = write_run_config,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    run_config = run_config_from_payload(payload, loader=loader)
    saved_path = writer(run_config)
    return {
        "ok": True,
        "config": public_run_config_dict(run_config),
        "path": str(saved_path),
    }


def payload_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def payload_bool(payload: dict, key: str, default: object = False) -> bool:
    return payload_truthy(payload.get(key, default))


def payload_web_environment(payload: dict) -> str | None:
    if "environment" not in payload:
        return None
    environment = str(payload.get("environment") or "production").strip().lower()
    if environment != "production":
        raise ValueError("web console only supports production environment")
    return "production"


def payload_string_list(payload: dict, key: str, default: list[str] | None = None) -> list[str]:
    raw = payload.get(key, default or [])
    if isinstance(raw, str):
        values: list[Any] = raw.replace("\r", "\n").replace(",", "\n").splitlines()
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = list(default or [])
    return [str(item).strip() for item in values if str(item).strip()]


def bounded_query_int(value: object, lower: int, upper: int) -> int:
    if value is None:
        return lower
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        parsed = lower
    return min(max(parsed, lower), upper)


def bounded_query_float(value: object, lower: float, upper: float) -> float:
    if value is None:
        return lower
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        parsed = lower
    return min(max(parsed, lower), upper)


def run_config_from_payload(payload: dict, *, loader: RunConfigLoader = load_run_config) -> RunConfig:
    run_config = loader()
    settings_data = payload.get("settings") or {}
    alpha_type = settings_data.get("type", settings_data.get("alphaType"))
    current_settings = run_config.ops.settings
    requested_environment = payload_web_environment(payload)
    if requested_environment is not None:
        run_config.environment = requested_environment
    run_config.auto_submit = payload_bool(payload, "autoSubmit", run_config.auto_submit)
    if "continuousMode" in payload:
        run_config.ops.budget.run_forever = payload_bool(
            payload,
            "continuousMode",
            run_config.ops.budget.run_forever,
        )
    validate_settings_enums(settings_data)
    run_config.credentials.username = str(payload.get("username", "")) or run_config.credentials.username
    run_config.credentials.password = str(payload.get("password", "")) or run_config.credentials.password
    run_config.credentials.token = str(payload.get("token", "")) or run_config.credentials.token
    run_config.ops.settings = BrainSettings(
        instrumentType=str(settings_data.get("instrumentType", current_settings.instrumentType)),
        region=str(settings_data.get("region", current_settings.region)),
        universe=str(settings_data.get("universe", current_settings.universe)),
        dataset=str(settings_data.get("dataset", current_settings.dataset)),
        delay=payload_int(
            settings_data,
            "delay",
            current_settings.delay,
            lower=min(_VALID_DELAYS),
            upper=max(_VALID_DELAYS),
            label="settings.delay",
        ),
        decay=payload_int(settings_data, "decay", current_settings.decay, lower=0, label="settings.decay"),
        neutralization=str(settings_data.get("neutralization", current_settings.neutralization)),
        truncation=payload_float(
            settings_data,
            "truncation",
            current_settings.truncation,
            lower=0.0,
            upper=1.0,
            label="settings.truncation",
        ),
        pasteurization=str(settings_data.get("pasteurization", current_settings.pasteurization)),
        unitHandling=str(settings_data.get("unitHandling", current_settings.unitHandling)),
        nanHandling=str(settings_data.get("nanHandling", current_settings.nanHandling)),
        language=str(settings_data.get("language", current_settings.language)),
        visualization=payload_truthy(settings_data.get("visualization", current_settings.visualization)),
        type=str(alpha_type if alpha_type is not None else current_settings.type),
    )
    current_budget = run_config.ops.budget
    run_config.ops.budget = ResearchBudget(
        max_candidates_per_cycle=payload_int(
            payload,
            "candidates",
            current_budget.max_candidates_per_cycle,
            lower=1,
            upper=_MAX_CANDIDATES,
        ),
        max_official_validations_per_cycle=payload_int(
            payload,
            "validations",
            current_budget.max_official_validations_per_cycle,
            lower=1,
            upper=_MAX_VALIDATIONS,
        ),
        max_official_simulations_per_cycle=payload_int(
            payload,
            "simulations",
            current_budget.max_official_simulations_per_cycle,
            lower=1,
            upper=_MAX_SIMULATIONS,
        ),
        max_official_concurrent_simulations=payload_int(
            payload,
            "concurrentSimulations",
            current_budget.max_official_concurrent_simulations,
            lower=1,
            upper=_MAX_CONCURRENT_SIMULATIONS,
        ),
        retained_alpha_pool_size=payload_int(
            payload,
            "poolSize",
            current_budget.retained_alpha_pool_size,
            lower=1,
            upper=_MAX_POOL_SIZE,
        ),
        official_backtest_batch_size=payload_int(
            payload,
            "backtestBatchSize",
            current_budget.official_backtest_batch_size,
            lower=1,
            upper=_MAX_BACKTEST_BATCH_SIZE,
        ),
        min_local_quality_score=current_budget.min_local_quality_score,
        min_prior_score_for_official_validation=payload_float(
            payload,
            "minPriorValidation",
            current_budget.min_prior_score_for_official_validation,
            lower=0.0,
        ),
        min_prior_score_for_official_simulation=payload_float(
            payload,
            "minPriorSimulation",
            current_budget.min_prior_score_for_official_simulation,
            lower=0.0,
        ),
        stop_official_calls_on_rate_limit=payload_bool(
            payload, "stopOnRateLimit", current_budget.stop_official_calls_on_rate_limit
        ),
        run_forever=payload_bool(payload, "continuousMode", current_budget.run_forever),
        cycle_pause_seconds=payload_float(
            payload,
            "cyclePauseSeconds",
            current_budget.cycle_pause_seconds,
            lower=0.0,
            upper=float(_MAX_CYCLE_PAUSE_SECONDS),
        ),
        official_retry_pause_seconds=payload_float(
            payload,
            "officialRetryPauseSeconds",
            current_budget.official_retry_pause_seconds,
            lower=0.0,
        ),
        adaptive_strategy_enabled=payload_bool(
            payload,
            "adaptiveStrategy",
            current_budget.adaptive_strategy_enabled,
        ),
        adaptive_min_official_results=payload_int(
            payload,
            "adaptiveMinOfficialResults",
            current_budget.adaptive_min_official_results,
            lower=1,
        ),
        adaptive_min_cycles=payload_int(
            payload,
            "adaptiveMinCycles",
            current_budget.adaptive_min_cycles,
            lower=1,
        ),
        adaptive_min_ready_rate=payload_float(
            payload,
            "adaptiveMinReadyRate",
            current_budget.adaptive_min_ready_rate,
            lower=0.0,
            upper=1.0,
        ),
        max_simulation_retries=payload_int(
            payload,
            "maxSimulationRetries",
            current_budget.max_simulation_retries,
            lower=0,
        ),
        enable_secondary_fusion=payload_bool(
            payload,
            "enableSecondaryFusion",
            current_budget.enable_secondary_fusion,
        ),
        require_cloud_sync=payload_bool(payload, "requireCloudSync", current_budget.require_cloud_sync),
        cloud_sync_range=str(payload.get("syncRange", current_budget.cloud_sync_range)),
        max_cycles=payload_int(
            payload,
            "cycles" if "cycles" in payload else "max_cycles",
            current_budget.max_cycles,
            lower=0 if run_config.ops.budget.run_forever else 1,
            upper=_MAX_CYCLES,
            label="cycles",
        ),
        dataset_strategy=current_budget.dataset_strategy,
        generation_mode_ratio=current_budget.generation_mode_ratio,
        hypothesis_library_dir=current_budget.hypothesis_library_dir,
        strategy_plugins_enabled=payload_bool(
            payload,
            "strategyPluginsEnabled",
            current_budget.strategy_plugins_enabled,
        ),
        strategy_plugin_specs=payload_string_list(
            payload,
            "strategyPluginSpecs",
            current_budget.strategy_plugin_specs,
        ),
        use_assistant_guidance=payload_bool(
            payload,
            "useAssistantGuidance",
            current_budget.use_assistant_guidance,
        ),
        assistant_guidance_min_confidence=bounded_query_float(
            payload.get("assistantGuidanceMinConfidence", current_budget.assistant_guidance_min_confidence),
            0.0,
            1.0,
        ),
        resume_persisted_backtests=payload_bool(
            payload,
            "resumePersistedBacktests",
            current_budget.resume_persisted_backtests,
        ),
    )
    threshold_payload = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
    current_thresholds = run_config.ops.thresholds
    for top_key, nested_key, attr, upper in (
        ("minSharpe", "min_sharpe", "min_sharpe", None),
        ("minFitness", "min_fitness", "min_fitness", None),
        ("minTurnover", "min_turnover", "min_turnover", 1.0),
        ("platformMaxTurnover", "platform_max_turnover", "platform_max_turnover", 1.0),
        ("maxSelfCorrelation", "max_self_correlation", "max_self_correlation", 1.0),
        ("maxWeightConcentration", "max_weight_concentration", "max_weight_concentration", 1.0),
    ):
        source = payload if top_key in payload else threshold_payload
        source_key = top_key if top_key in payload else nested_key
        if source_key in source:
            setattr(
                current_thresholds,
                attr,
                payload_float(
                    source,
                    source_key,
                    getattr(current_thresholds, attr),
                    lower=0.0,
                    upper=upper,
                    label=f"thresholds.{attr}",
                ),
            )
    current_scoring = run_config.ops.scoring
    current_scoring.assistant_guidance_score_adjustment_enabled = payload_bool(
        payload,
        "assistantGuidanceScoreAdjustment",
        current_scoring.assistant_guidance_score_adjustment_enabled,
    )
    current_scoring.assistant_guidance_score_min_confidence = bounded_query_float(
        payload.get("assistantGuidanceScoreMinConfidence", current_scoring.assistant_guidance_score_min_confidence),
        0.0,
        1.0,
    )
    current_scoring.assistant_guidance_score_min_outcome_count = max(
        0,
        payload_int(
            payload,
            "assistantGuidanceScoreMinOutcomeCount",
            current_scoring.assistant_guidance_score_min_outcome_count,
            lower=0,
        ),
    )
    current_scoring.assistant_guidance_score_bonus_cap = bounded_query_float(
        payload.get("assistantGuidanceScoreBonusCap", current_scoring.assistant_guidance_score_bonus_cap),
        0.0,
        10.0,
    )
    current_scoring.assistant_guidance_score_penalty_cap = bounded_query_float(
        payload.get("assistantGuidanceScorePenaltyCap", current_scoring.assistant_guidance_score_penalty_cap),
        0.0,
        10.0,
    )
    raw_base_url = payload.get("baseUrl") or payload.get("base_url")
    if raw_base_url:
        base_url = str(raw_base_url).rstrip("/")
        allowed = _ALLOWED_BASE_URLS.get(run_config.environment, set())
        if allowed and base_url not in allowed:
            raise ValueError(
                f"baseUrl not allowed for environment '{run_config.environment}'; "
                f"allowed: {sorted(allowed)}"
            )
        run_config.ops.official_api.base_url = base_url
    run_config.ops.official_api.rate_limit_retry_attempts = payload_int(
        payload,
        "rateLimitRetryAttempts",
        run_config.ops.official_api.rate_limit_retry_attempts,
        lower=0,
    )
    validated = validate_run_config(run_config)
    if "continuousMode" in payload:
        validated.ops.budget.run_forever = payload_bool(
            payload,
            "continuousMode",
            validated.ops.budget.run_forever,
        )
    return validated


def payload_int(
    payload: dict,
    key: str,
    default: int,
    *,
    lower: int | None = None,
    upper: int | None = None,
    label: str | None = None,
) -> int:
    display = label or key
    raw = payload.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f"{display} must be an integer")
    try:
        parsed = int(raw)
    except (OverflowError, TypeError, ValueError):
        raise ValueError(f"{display} must be an integer") from None
    if isinstance(raw, float) and (not math.isfinite(raw) or not raw.is_integer()):
        raise ValueError(f"{display} must be an integer")
    if lower is not None and parsed < lower:
        raise ValueError(f"{display} must be >= {lower}")
    if upper is not None and parsed > upper:
        return upper
    return parsed


def payload_float(
    payload: dict,
    key: str,
    default: float,
    *,
    lower: float | None = None,
    upper: float | None = None,
    label: str | None = None,
) -> float:
    display = label or key
    raw = payload.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f"{display} must be a number")
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{display} must be a number") from None
    if not math.isfinite(parsed):
        raise ValueError(f"{display} must be finite")
    if lower is not None and parsed < lower:
        raise ValueError(f"{display} must be >= {lower}")
    if upper is not None and parsed > upper:
        return upper
    return parsed


def validate_settings_enums(settings: dict) -> None:
    """Raise ValueError if any settings field has an invalid enum value."""

    errors = []
    region = str(settings.get("region", "")).strip()
    if region and region not in _VALID_REGIONS:
        errors.append(f"Invalid region: '{region}'. Valid: {sorted(_VALID_REGIONS)}")
    universe = str(settings.get("universe", "")).strip()
    if universe and universe not in _VALID_UNIVERSES:
        errors.append(f"Invalid universe: '{universe}'. Valid: {sorted(_VALID_UNIVERSES)}")
    if "delay" in settings:
        try:
            delay = int(str(settings.get("delay")))
        except (TypeError, ValueError):
            errors.append(f"Invalid delay: '{settings.get('delay')}'. Valid: {sorted(_VALID_DELAYS)}")
        else:
            if delay not in _VALID_DELAYS:
                errors.append(f"Invalid delay: '{delay}'. Valid: {sorted(_VALID_DELAYS)}")
    neutralization = str(settings.get("neutralization", "")).strip()
    if neutralization and neutralization not in _VALID_NEUTRALIZATIONS:
        errors.append(f"Invalid neutralization: '{neutralization}'. Valid: {sorted(_VALID_NEUTRALIZATIONS)}")
    alpha_type = str(settings.get("type", settings.get("alphaType", ""))).strip()
    if alpha_type and alpha_type not in _VALID_TYPES:
        errors.append(f"Invalid alpha type: '{alpha_type}'. Valid: {sorted(_VALID_TYPES)}")
    if errors:
        raise ValueError("; ".join(errors))

"""jsonschema-based strict validation for run_config.json.

Provides a declarative schema that validates every field of the RunConfig
structure before the pipeline or web console can start.  This layer
complements the procedural validators in config.py.

Schema version: config-schema.v1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]


RUN_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "run-config-schema.v1",
    "type": "object",
    "required": ["environment", "auto_submit", "credentials", "web", "ops"],
    "properties": {
        "environment": {"type": "string", "enum": ["mock", "production"]},
        "auto_submit": {"type": "boolean"},
        "credentials": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "password": {"type": "string"},
                "token": {"type": "string"},
                "username_env": {"type": "string", "minLength": 1},
                "password_env": {"type": "string", "minLength": 1},
                "token_env": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        "web": {
            "type": "object",
            "required": ["host", "port"],
            "properties": {
                "host": {"type": "string", "minLength": 1},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                "open_browser": {"type": "boolean"},
                "session_ttl_seconds": {"type": "integer", "minimum": 60},
                "allow_multiple_sessions": {"type": "boolean"},
                "allow_remote": {"type": "boolean"},
                "secure_cookies": {"type": "boolean"},
                "admin_token_env": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        "ops": {
            "type": "object",
            "required": ["settings", "budget", "scoring", "thresholds",
                         "submission_policy", "official_api", "storage_dir"],
            "properties": {
                "storage_dir": {"type": "string", "minLength": 1},
                "source_tag_policy": {"type": "string"},
                "settings": {
                    "type": "object",
                    "required": ["instrumentType", "region", "universe", "delay",
                                 "neutralization", "language"],
                    "properties": {
                        "instrumentType": {"type": "string", "enum": ["EQUITY"]},
                        "region": {"type": "string",
                                   "enum": ["USA", "EUR", "ASI", "GLOBAL", "CHN",
                                            "JPN", "TWN", "HKG"]},
                        "universe": {"type": "string",
                                     "enum": ["TOP500", "TOP1000", "TOP2000",
                                              "TOP3000", "TOP5000"]},
                        "dataset": {"type": "string"},
                        "delay": {"type": "integer", "enum": [0, 1, 2]},
                        "decay": {"type": "integer", "minimum": 0},
                        "neutralization": {"type": "string",
                                           "enum": ["NONE", "MARKET", "SECTOR",
                                                    "SUBINDUSTRY", "INDUSTRY"]},
                        "truncation": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "pasteurization": {"type": "string", "enum": ["ON", "OFF"]},
                        "unitHandling": {"type": "string",
                                         "enum": ["VERIFY", "SCALE"]},
                        "nanHandling": {"type": "string", "enum": ["ON", "OFF"]},
                        "language": {"type": "string",
                                     "enum": ["FASTEXPR"]},
                        "visualization": {"type": "boolean"},
                        "type": {"type": "string",
                                 "enum": ["REGULAR", "SUPER", "FRONTIER"]},
                    },
                    "additionalProperties": False,
                },
                "budget": {
                    "type": "object",
                    "properties": {
                        "max_candidates_per_cycle": {"type": "integer", "minimum": 1},
                        "max_official_validations_per_cycle": {"type": "integer", "minimum": 0},
                        "max_official_simulations_per_cycle": {"type": "integer", "minimum": 0},
                        "max_official_concurrent_simulations": {"type": "integer", "minimum": 1},
                        "retained_alpha_pool_size": {"type": "integer", "minimum": 1},
                        "official_backtest_batch_size": {"type": "integer", "minimum": 1},
                        "min_local_quality_score": {"type": "number", "minimum": 0.0},
                        "min_prior_score_for_official_validation": {"type": "number", "minimum": 0.0},
                        "min_prior_score_for_official_simulation": {"type": "number", "minimum": 0.0},
                        "stop_official_calls_on_rate_limit": {"type": "boolean"},
                        "run_forever": {"type": "boolean"},
                        "cycle_pause_seconds": {"type": "number", "minimum": 0.0},
                        "max_cycles": {"type": "integer", "minimum": 0},
                        "dataset_strategy": {"type": "string",
                                             "enum": ["all", "rotate", "random",
                                                      "specific", "fixed", "locked"]},
                        "require_cloud_sync": {"type": "boolean"},
                        "use_assistant_guidance": {"type": "boolean"},
                        "assistant_guidance_min_confidence": {
                            "type": "number", "minimum": 0.0, "maximum": 1.0,
                        },
                    },
                    "additionalProperties": True,
                },
                "scoring": {
                    "type": "object",
                    "properties": {
                        "prior_layer_weight": {"type": "number", "minimum": 0.0},
                        "empirical_layer_weight": {"type": "number", "minimum": 0.0},
                        "checklist_layer_weight": {"type": "number", "minimum": 0.0},
                        "local_prior_weight": {"type": "number", "minimum": 0.0},
                        "local_quality_weight": {"type": "number", "minimum": 0.0},
                        "market_regime": {"type": "string",
                                          "enum": ["normal", "low_vol", "high_vol"]},
                    },
                    "additionalProperties": True,
                },
                "thresholds": {
                    "type": "object",
                    "properties": {
                        "min_sharpe": {"type": "number", "minimum": 0.0},
                        "min_fitness": {"type": "number", "minimum": 0.0},
                        "min_sharpe_delay0": {"type": "number", "minimum": 0.0},
                        "min_fitness_delay0": {"type": "number", "minimum": 0.0},
                        "min_turnover": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "platform_max_turnover": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "max_self_correlation": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "max_prod_correlation": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "max_weight_concentration": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "sub_universe_sharpe_min_ratio": {"type": "number", "minimum": 0.0},
                        "require_official_pass": {"type": "boolean"},
                    },
                    "additionalProperties": True,
                },
                "submission_policy": {
                    "type": "object",
                    "properties": {
                        "max_auto_submissions_per_day": {"type": "integer", "minimum": 0},
                        "max_auto_submissions_per_run": {"type": "integer", "minimum": 0},
                        "max_expression_similarity": {
                            "type": "number", "minimum": 0.0, "maximum": 1.0,
                        },
                        "block_micro_variants": {"type": "boolean"},
                    },
                    "additionalProperties": True,
                },
                "official_api": {
                    "type": "object",
                    "required": ["base_url"],
                    "properties": {
                        "base_url": {"type": "string", "format": "uri",
                                     "minLength": 1},
                        "timeout_seconds": {"type": "integer", "minimum": 1},
                        "poll_attempts": {"type": "integer", "minimum": 1},
                        "poll_interval_seconds": {"type": "number", "minimum": 0.1},
                        "min_request_interval_seconds": {"type": "number", "minimum": 0.0},
                        "rate_limit_retry_attempts": {"type": "integer", "minimum": 0},
                        "rate_limit_backoff_seconds": {"type": "number", "minimum": 0.0},
                        "cache_dir": {"type": "string", "minLength": 1},
                        "context_cache_ttl_seconds": {"type": "integer", "minimum": 0},
                        "allow_stale_context_on_rate_limit": {"type": "boolean"},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
    },
    "additionalProperties": True,
}


def validate_config_with_jsonschema(
    config_data: dict[str, Any],
    *,
    schema: dict[str, Any] | None = None,
) -> list[str]:
    """Validate a raw config dict against the RUN_CONFIG_SCHEMA.

    Returns a list of validation error messages.  Empty list = valid.
    When jsonschema is not installed, returns an empty list with a
    warning printed to stderr.

    Args:
        config_data: JSON-parsed config dictionary.
        schema: Optional custom schema; defaults to RUN_CONFIG_SCHEMA.

    Returns:
        List of error message strings (empty = valid).
    """
    if jsonschema is None:
        print(
            "jsonschema: jsonschema not installed; skipping structural validation. "
            "Install with: pip install jsonschema>=4.20",
            file=sys.stderr,
        )
        return []

    effective_schema = schema or RUN_CONFIG_SCHEMA
    errors: list[str] = []
    try:
        validator = jsonschema.Draft202012Validator(effective_schema)
        for error in sorted(validator.iter_errors(config_data), key=lambda e: e.path):
            path = ".".join(str(p) for p in error.path) if error.path else "(root)"
            errors.append(f"{path}: {error.message}")
    except jsonschema.SchemaError as exc:
        errors.append(f"schema error: {exc}")
    return errors


def validate_config_file(path: str | Path) -> tuple[bool, list[str]]:
    """Convenience: load a config file and validate with jsonschema.

    Returns (is_valid, error_messages).
    """
    config_path = Path(path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, [f"JSON parse error at {config_path}: {exc}"]
    except OSError as exc:
        return False, [f"File read error at {config_path}: {exc}"]
    errors = validate_config_with_jsonschema(data)
    return len(errors) == 0, errors

"""jsonschema-based strict validation for run_config.json.

Provides a declarative schema that validates every field of the RunConfig
structure before the pipeline or web console can start.  This layer
complements the procedural validators in config.py.

All enum values are sourced from brain_alpha_ops.brain_api.canonical to
ensure zero-deviation alignment with the BRAIN platform specification.

Schema version: config-schema.v2
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]

# ── Canonical enum lists for jsonschema (sorted for deterministic validation) ──
_C_REGIONS = sorted(SUPPORTED_REGIONS)               # ["CHN", "EUR", "GLB", "USA"]
_C_UNIVERSES = sorted(SUPPORTED_UNIVERSES)           # ["TOP1000", "TOP3000", "TOP500"]
_C_DELAYS = sorted(SUPPORTED_DELAYS)                 # [0, 1]
_C_NEUT = sorted(SUPPORTED_NEUTRALIZATIONS)          # ["INDUSTRY", "MARKET", "NONE", "SECTOR", "SUBINDUSTRY"]
_C_UNIT = sorted(SUPPORTED_UNIT_HANDLING)            # ["NONE", "RAW", "VERIFY"]
_C_ALPHA_TYPES = sorted(SUPPORTED_ALPHA_TYPES)       # ["ATOM", "POWER_POOL", "PYRAMID", "REGULAR"]

RUN_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "run-config-schema.v2",
    "type": "object",
    "required": ["environment", "auto_submit", "credentials", "web", "ops"],
    "properties": {
        "environment": {"type": "string", "enum": ["production"]},
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
                        "instrumentType": {
                            "type": "string",
                            "enum": sorted(SUPPORTED_INSTRUMENT_TYPES),
                        },
                        "region": {"type": "string", "enum": _C_REGIONS},
                        "universe": {"type": "string", "enum": _C_UNIVERSES},
                        "dataset": {"type": "string"},
                        "delay": {"type": "integer", "enum": _C_DELAYS},
                        "decay": {"type": "integer", "minimum": 0},
                        "neutralization": {"type": "string", "enum": _C_NEUT},
                        "truncation": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "pasteurization": {
                            "type": "string",
                            "enum": sorted(SUPPORTED_PASTEURIZATION),
                        },
                        "unitHandling": {"type": "string", "enum": _C_UNIT},
                        "nanHandling": {
                            "type": "string",
                            "enum": sorted(SUPPORTED_NAN_HANDLING),
                        },
                        "language": {
                            "type": "string",
                            "enum": sorted(SUPPORTED_LANGUAGES),
                        },
                        "visualization": {"type": "boolean"},
                        "type": {"type": "string", "enum": _C_ALPHA_TYPES},
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
    When jsonschema is not installed, a dependency-free fallback validates the
    critical required, enum, type, and numeric-bound checks.

    Args:
        config_data: JSON-parsed config dictionary.
        schema: Optional custom schema; defaults to RUN_CONFIG_SCHEMA.

    Returns:
        List of error message strings (empty = valid).
    """
    if not isinstance(config_data, dict):
        return _validate_config_without_jsonschema(config_data, schema or RUN_CONFIG_SCHEMA)

    if jsonschema is None:
        print(
            "jsonschema: jsonschema not installed; using built-in limited validation. "
            "Install with: pip install jsonschema>=4.20 for full structural validation.",
            file=sys.stderr,
        )
        return _validate_config_without_jsonschema(config_data, schema or RUN_CONFIG_SCHEMA)

    effective_schema = schema or RUN_CONFIG_SCHEMA
    validation_schema = _partial_schema(effective_schema) if schema is None and config_data else effective_schema
    errors: list[str] = []
    try:
        validator = jsonschema.Draft202012Validator(validation_schema)
        for error in sorted(validator.iter_errors(config_data), key=lambda e: e.path):
            path = ".".join(str(p) for p in error.path) if error.path else "(root)"
            errors.append(f"{path}: {error.message}")
    except jsonschema.SchemaError as exc:
        errors.append(f"schema error: {exc}")
    return errors


def _validate_config_without_jsonschema(
    config_data: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    """Small dependency-free fallback for the schema subset used in tests.

    The production path prefers ``jsonschema``.  This fallback keeps critical
    type/enum/range checks active in minimal runtime environments.

    ``run_config.json`` is allowed to be a partial override file because
    ``load_run_config`` merges it into ``RunConfig()`` defaults before the
    procedural validator runs.  The fallback therefore treats the default run
    config schema as partial-friendly: an entirely empty object is still
    reported as missing required roots, while non-empty partial documents only
    validate fields that are explicitly present.
    """
    errors: list[str] = []
    enforce_required = schema is not RUN_CONFIG_SCHEMA or not config_data

    def path_label(path: tuple[str, ...]) -> str:
        return ".".join(path) if path else "(root)"

    def validate_node(value: Any, node_schema: dict[str, Any], path: tuple[str, ...]) -> None:
        expected_type = node_schema.get("type")
        if expected_type == "object":
            if not isinstance(value, dict):
                errors.append(f"{path_label(path)}: {value!r} is not an object")
                return
            if enforce_required:
                for key in node_schema.get("required", []):
                    if key not in value:
                        errors.append(f"{path_label(path)}: missing required property '{key}'")
            for key, child_schema in node_schema.get("properties", {}).items():
                if key in value and isinstance(child_schema, dict):
                    validate_node(value[key], child_schema, (*path, str(key)))
            return

        if expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"{path_label(path)}: {value!r} is not a string")
                return
            min_length = node_schema.get("minLength")
            if isinstance(min_length, int) and len(value) < min_length:
                errors.append(
                    f"{path_label(path)}: {value!r} is shorter than the minimum length of {min_length}"
                )
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{path_label(path)}: {value!r} is not a boolean")
                return
        elif expected_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"{path_label(path)}: {value!r} is not an integer")
                return
        elif expected_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(f"{path_label(path)}: {value!r} is not a number")
                return

        allowed_values = node_schema.get("enum")
        if allowed_values is not None and value not in allowed_values:
            errors.append(f"{path_label(path)}: {value!r} is not one of {allowed_values!r}")

        if expected_type in {"integer", "number"}:
            numeric = float(value)
            minimum = node_schema.get("minimum")
            maximum = node_schema.get("maximum")
            if minimum is not None and numeric < float(minimum):
                errors.append(f"{path_label(path)}: {value!r} is less than the minimum of {minimum}")
            if maximum is not None and numeric > float(maximum):
                errors.append(f"{path_label(path)}: {value!r} is greater than the maximum of {maximum}")

    validate_node(config_data, schema, ())

    return errors


def _partial_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` that validates explicit override fields only."""
    cloned = dict(schema)
    cloned.pop("required", None)
    properties = cloned.get("properties")
    if isinstance(properties, dict):
        cloned["properties"] = {
            key: _partial_schema(value) if isinstance(value, dict) else value
            for key, value in properties.items()
        }
    return cloned


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

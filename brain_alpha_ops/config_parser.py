"""Unified configuration parser with three-stage pipeline validation.

This module consolidates the previously scattered configuration validation
(jsonschema, dataclass type coercion, domain business rules) into a single
entry point: ``parse_config()``.

Design
------
- **Stage 1** — jsonschema structural validation (``config_schema``).
- **Stage 2** — dataclass type coercion (``config_models`` / ``config_type_validation``).
- **Stage 3** — domain business-rule validation (``config_domain_validation``).

No stage short-circuits on failure — all errors are collected and returned
in a unified ``ConfigValidationError`` format.  The ``validate_update()``
function adds atomic hot-update validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.config_models import OpsConfig
from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigValidationError",
    "parse_config",
    "validate_update",
]


# ── Structured error type ──────────────────────────────────────────────

@dataclass
class ConfigValidationError:
    """Structured configuration validation error.

    Attributes:
        field_path: Dot-separated path to the invalid field
            (e.g. ``"scoring.decision_thresholds.submit"``).
        rule_name: Machine-readable rule identifier.
        failed_value: The rejected value (as a string).
        suggestion: Human-readable fix hint.
        stage: Which stage caught the error (1=jsonschema, 2=type, 3=domain).
    """

    field_path: str
    rule_name: str
    failed_value: Any = ""
    suggestion: str = ""
    stage: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "rule_name": self.rule_name,
            "failed_value": str(self.failed_value),
            "suggestion": self.suggestion,
            "stage": self.stage,
        }


# ── Stage 1: jsonschema ────────────────────────────────────────────────

def _validate_jsonschema(raw: dict[str, Any]) -> list[ConfigValidationError]:
    """Run jsonschema structural validation (no import needed if schema module is absent)."""
    errors: list[ConfigValidationError] = []
    try:
        from brain_alpha_ops.config_schema import validate_config as _jsonschema_validate
        js_errors = _jsonschema_validate(raw)
        if isinstance(js_errors, list):
            for err in js_errors:
                if isinstance(err, dict):
                    errors.append(ConfigValidationError(
                        field_path=str(err.get("path", "")),
                        rule_name=str(err.get("rule", "jsonschema")),
                        failed_value=err.get("value", ""),
                        suggestion=str(err.get("message", "")),
                        stage=1,
                    ))
                elif isinstance(err, str):
                    errors.append(ConfigValidationError(
                        field_path="",
                        rule_name="jsonschema",
                        failed_value="",
                        suggestion=err,
                        stage=1,
                    ))
    except ImportError:
        logger.debug("config_schema.validate_config not available; skipping jsonschema stage")
    except Exception as exc:
        logger.warning("jsonschema validation failed: %s", redact_error_message(exc), exc_info=True)
    return errors


# ── Stage 2: dataclass type coercion ───────────────────────────────────

def _validate_types(raw: dict[str, Any]) -> list[ConfigValidationError]:
    """Coerce raw dict into dataclass instances; collect type errors."""
    errors: list[ConfigValidationError] = []
    try:
        from brain_alpha_ops.config_type_validation import validate_config_types as _type_validate
        type_errors = _type_validate(raw)
        if isinstance(type_errors, list):
            for err in type_errors:
                if isinstance(err, dict):
                    errors.append(ConfigValidationError(
                        field_path=str(err.get("path", err.get("field", ""))),
                        rule_name=str(err.get("rule", err.get("type", "type_error"))),
                        failed_value=err.get("value", ""),
                        suggestion=str(err.get("message", err.get("expected", ""))),
                        stage=2,
                    ))
                elif isinstance(err, str):
                    errors.append(ConfigValidationError(
                        field_path="",
                        rule_name="type_error",
                        failed_value="",
                        suggestion=err,
                        stage=2,
                    ))
    except ImportError:
        logger.debug("config_type_validation not available; skipping type stage")
    except Exception as exc:
        logger.warning("type validation failed: %s", redact_error_message(exc), exc_info=True)
    return errors


# ── Stage 3: domain business rules ─────────────────────────────────────

def _validate_domain(raw: dict[str, Any]) -> list[ConfigValidationError]:
    """Run domain business-rule validation."""
    errors: list[ConfigValidationError] = []
    try:
        from brain_alpha_ops.config_validation_helpers import (
            validate_decision_thresholds,
        )

        # Run decision threshold validation
        scoring = raw.get("scoring", {})
        if isinstance(scoring, dict):
            decision_thresholds = scoring.get("decision_thresholds", {})
            threshold_errors: list[str] = []
            validate_decision_thresholds(threshold_errors, decision_thresholds)
            for msg in threshold_errors:
                errors.append(ConfigValidationError(
                    field_path="scoring.decision_thresholds",
                    rule_name="decision_thresholds_order",
                    failed_value=str(decision_thresholds),
                    suggestion=msg,
                    stage=3,
                ))
    except ImportError:
        logger.debug("config_validation_helpers not available; skipping domain stage")
    except Exception as exc:
        logger.warning("domain validation failed: %s", redact_error_message(exc), exc_info=True)

    # Run full domain validation if available
    try:
        from brain_alpha_ops.config_domain_validation import validate_domain as _domain_validate
        domain_errors = _domain_validate(raw)
        if isinstance(domain_errors, list):
            for err in domain_errors:
                if isinstance(err, dict):
                    errors.append(ConfigValidationError(
                        field_path=str(err.get("path", err.get("field", ""))),
                        rule_name=str(err.get("rule", "domain")),
                        failed_value=err.get("value", ""),
                        suggestion=str(err.get("message", "")),
                        stage=3,
                    ))
                elif isinstance(err, str):
                    errors.append(ConfigValidationError(
                        field_path="",
                        rule_name="domain",
                        failed_value="",
                        suggestion=err,
                        stage=3,
                    ))
    except ImportError:
        logger.debug("config_domain_validation not available; skipping full domain stage")
    except Exception as exc:
        logger.warning("full domain validation failed: %s", redact_error_message(exc), exc_info=True)

    return errors


# ── Public API ─────────────────────────────────────────────────────────

def parse_config(raw_dict: dict[str, Any]) -> tuple[OpsConfig | None, list[ConfigValidationError]]:
    """Parse and validate a raw configuration dictionary.

    Runs the three-stage validation pipeline (jsonschema → types → domain)
    and returns either a valid ``OpsConfig`` or a non-empty error list.

    Args:
        raw_dict: Raw configuration dict (typically from a JSON file).

    Returns:
        A tuple of ``(config, errors)``.  If ``errors`` is non-empty,
        ``config`` is ``None`` and callers should surface the errors.
        Otherwise ``config`` is a valid ``OpsConfig`` instance.
    """
    all_errors: list[ConfigValidationError] = []

    # Stage 1
    all_errors.extend(_validate_jsonschema(raw_dict))

    # Stage 2
    all_errors.extend(_validate_types(raw_dict))

    # Stage 3
    all_errors.extend(_validate_domain(raw_dict))

    if all_errors:
        return None, all_errors

    # All stages passed — build the config
    try:
        config = _build_ops_config(raw_dict)
        return config, []
    except Exception as exc:
        return None, [ConfigValidationError(
            field_path="",
            rule_name="config_construction",
            failed_value=str(exc),
            suggestion="Check that all required fields are present and correctly typed.",
            stage=2,
        )]


def validate_update(
    current: OpsConfig,
    patch: dict[str, Any],
) -> list[ConfigValidationError]:
    """Validate a hot-update patch against the current configuration.

    The patch is merged with the current config and the result is validated
    atomically.  On failure the patch is not applied.

    Args:
        current: The active ``OpsConfig``.
        patch: Partial dict with fields to update.

    Returns:
        Empty list if the patch is valid; otherwise a non-empty list of
        ``ConfigValidationError`` instances.
    """
    # Merge current + patch
    merged: dict[str, Any] = {}
    try:
        if hasattr(current, "to_dict"):
            merged = current.to_dict()
        else:
            merged = _ops_config_to_dict(current)
    except Exception as exc:
        return [ConfigValidationError(
            field_path="",
            rule_name="config_serialization",
            failed_value=str(exc),
            suggestion="Cannot serialize current config for validation.",
            stage=2,
        )]

    # Apply patch
    _deep_update(merged, patch)

    # Validate merged
    _, errors = parse_config(merged)
    return errors


# ── Helpers ────────────────────────────────────────────────────────────

def _build_ops_config(raw: dict[str, Any]) -> OpsConfig:
    """Construct an ``OpsConfig`` from a flat config dict.

    Maps dict keys to the nested dataclass structure used by ``OpsConfig``:
    ``settings`` → ``BrainSettings``, ``thresholds`` → ``QualityThresholds``,
    ``scoring`` → ``ScoringConfig``, etc.
    """
    from brain_alpha_ops.config_models import (
        BrainSettings,
        OfficialAPIConfig,
        QualityThresholds,
        ResearchBudget,
        ScoringConfig,
        SubmissionPolicy,
    )
    from dataclasses import fields

    def _populate(cls, src: dict[str, Any]) -> dict[str, Any]:
        """Extract fields belonging to *cls* from *src*."""
        field_names = {f.name for f in fields(cls)}
        return {k: v for k, v in src.items() if k in field_names and v is not None}

    settings_kw = _populate(BrainSettings, raw)
    budget_kw = _populate(ResearchBudget, raw)
    scoring_kw = _populate(ScoringConfig, raw)
    thresholds_kw = _populate(QualityThresholds, raw)
    submission_kw = _populate(SubmissionPolicy, raw)
    api_kw = _populate(OfficialAPIConfig, raw)

    # Nested dict resolution: if the raw dict has a top-level key matching
    # a sub-struct, prefer that (e.g. raw["scoring"] overrides flat keys)
    for prefix, target_kw in [
        ("scoring", scoring_kw),
        ("thresholds", thresholds_kw),
        ("budget", budget_kw),
        ("settings", settings_kw),
        ("submission_policy", submission_kw),
        ("official_api", api_kw),
    ]:
        nested = raw.get(prefix)
        if isinstance(nested, dict):
            target_kw.update({k: v for k, v in nested.items() if v is not None})

    return OpsConfig(
        settings=BrainSettings(**settings_kw),
        budget=ResearchBudget(**budget_kw),
        scoring=ScoringConfig(**scoring_kw),
        thresholds=QualityThresholds(**thresholds_kw),
        submission_policy=SubmissionPolicy(**submission_kw),
        official_api=OfficialAPIConfig(**api_kw),
        storage_dir=str(raw.get("storage_dir", "data") or "data"),
        source_tag_policy=str(raw.get("source_tag_policy", "official/experience/inference/manual") or "official/experience/inference/manual"),
    )


def _ops_config_to_dict(config: OpsConfig) -> dict[str, Any]:
    """Best-effort conversion of OpsConfig to dict."""
    result: dict[str, Any] = {}
    for field_name in dir(config):
        if field_name.startswith("_"):
            continue
        try:
            value = getattr(config, field_name)
        except AttributeError:
            continue
        if callable(value) or isinstance(value, type):
            continue
        if hasattr(value, "to_dict"):
            result[field_name] = value.to_dict()
        elif hasattr(value, "__dataclass_fields__"):
            result[field_name] = {
                f: getattr(value, f) for f in value.__dataclass_fields__
            }
        elif isinstance(value, (str, int, float, bool, list, dict, type(None))):
            result[field_name] = value
    return result


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Recursively update *target* with *source*."""
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value

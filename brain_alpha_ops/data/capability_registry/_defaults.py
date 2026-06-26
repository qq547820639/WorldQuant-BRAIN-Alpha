"""Default BRAIN capability entries derived from BrainSettings and canonical enums.

These entries back the BrainSettings-shaped capabilities (region, universe,
delay, decay, neutralization, truncation, pasteurization, nanHandling,
unitHandling, language, visualization). They are intentionally aligned with
``brain_alpha_ops.brain_api.canonical.CANONICAL_SETTINGS`` and
``brain_alpha_ops.config_models.BrainSettings`` so the registry's view of
"what is a valid setting" matches what configuration validation already
enforces.

Logger name is hardcoded to preserve module identity after the split.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from brain_alpha_ops.brain_api.canonical import (
    SUPPORTED_DELAYS,
    SUPPORTED_NAN_HANDLING,
    SUPPORTED_NEUTRALIZATIONS,
    SUPPORTED_PASTEURIZATION,
    SUPPORTED_REGIONS,
    SUPPORTED_UNIT_HANDLING,
    SUPPORTED_UNIVERSES,
)
from brain_alpha_ops.config_models import BrainSettings
from brain_alpha_ops.data.capability_registry._types import (
    CapabilityEntry,
    CapabilityKind,
)

logger = logging.getLogger("brain_alpha_ops.data.capability_registry._defaults")


def build_default_capability_entries() -> list[CapabilityEntry]:
    """Return CapabilityEntry objects for the BrainSettings-shaped capabilities.

    Covers: region, universe, delay, decay, neutralization, truncation,
    pasteurization, unitHandling, nanHandling, visualization, language.
    Operator/field/dataset entries are sourced separately from the
    official_*.json cache via ``_loaders``.

    The "test_period" kind slot is used for the language capability since
    BrainSettings does not have a dedicated test_period field and the kind
    enum does not include "language".
    """
    settings = BrainSettings()
    now = _now()
    source = "brain_alpha_ops.config_models.BrainSettings"
    entries: list[CapabilityEntry] = []

    enum_specs: list[tuple[CapabilityKind, frozenset[Any], Any]] = [
        ("region", _to_frozenset(SUPPORTED_REGIONS), settings.region),
        ("universe", _to_frozenset(SUPPORTED_UNIVERSES), settings.universe),
        ("delay", _to_frozenset(SUPPORTED_DELAYS), settings.delay),
        ("neutralization", _to_frozenset(SUPPORTED_NEUTRALIZATIONS), settings.neutralization),
        ("pasteurization", _to_frozenset(SUPPORTED_PASTEURIZATION), settings.pasteurization),
        ("unit_handling", _to_frozenset(SUPPORTED_UNIT_HANDLING), settings.unitHandling),
        ("nan_handling", _to_frozenset(SUPPORTED_NAN_HANDLING), settings.nanHandling),
        ("visualization", frozenset({False, True}), settings.visualization),
    ]
    for kind, allowed, default_value in enum_specs:
        entries.append(CapabilityEntry(
            name=str(default_value),
            kind=kind,
            source=source,
            updated_at=now,
            scope=(),
            default_value=default_value,
            allowed_values=allowed,
            forbidden_values=(),
            validation_rule=f"canonical.CANONICAL_SETTINGS:{kind}",
            error_hint=f"{kind} value is outside the canonical BRAIN set",
        ))

    # Numeric ranges with no fixed enum (decay, truncation)
    entries.append(CapabilityEntry(
        name=str(settings.decay),
        kind="decay",
        source=source,
        updated_at=now,
        scope=(),
        default_value=settings.decay,
        allowed_values=frozenset(),
        forbidden_values=(),
        validation_rule="config_domain_validation.validate_settings:decay>=0",
        error_hint="decay must be a non-negative integer",
    ))
    entries.append(CapabilityEntry(
        name=str(settings.truncation),
        kind="truncation",
        source=source,
        updated_at=now,
        scope=(),
        default_value=settings.truncation,
        allowed_values=frozenset(),
        forbidden_values=(),
        validation_rule="config_domain_validation.validate_settings:0.0<=truncation<=1.0",
        error_hint="truncation must be a float in [0.0, 1.0]",
    ))

    # Language capability mapped to the test_period kind slot.
    from brain_alpha_ops.brain_api.canonical import SUPPORTED_LANGUAGES
    entries.append(CapabilityEntry(
        name=settings.language,
        kind="test_period",
        source=source,
        updated_at=now,
        scope=(),
        default_value=settings.language,
        allowed_values=_to_frozenset(SUPPORTED_LANGUAGES),
        forbidden_values=(),
        validation_rule="canonical.CANONICAL_SETTINGS:language",
        error_hint="language must be one of the canonical BRAIN supported languages",
    ))

    return entries


def _to_frozenset(values: Any) -> frozenset[Any]:
    if isinstance(values, (frozenset, set)):
        return frozenset(values)
    if isinstance(values, (list, tuple)):
        return frozenset(values)
    return frozenset({values})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["build_default_capability_entries"]

"""Configuration presets for common use cases.

This module provides pre-configured settings for common research scenarios.
BrainSettings defaults are sourced from the BRAIN capability registry
(:func:`brain_alpha_ops.data.capability_registry.get_registry`); each preset
only overrides the values that diverge from the registry defaults.

Usage:
    from brain_alpha_ops.presets import get_preset

    # Get a preset configuration
    config = get_preset("momentum_research")

    # Or use a specific preset
    from brain_alpha_ops.presets import PRESETS
    config = PRESETS["momentum_research"].config
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from brain_alpha_ops.config import (
    BrainSettings,
    OpsConfig,
    ResearchBudget,
    ScoringConfig,
)
from brain_alpha_ops.redaction import redact_error_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PresetConfig:
    """A named configuration preset."""
    name: str
    description: str
    config: OpsConfig


# ═══════════════════════════════════════════════════════════════════════
# Registry-derived BrainSettings builder
# ═══════════════════════════════════════════════════════════════════════

def _registry_default(kind: str, fallback: Any) -> Any:
    """Read a default value for ``kind`` from the capability registry.

    Returns ``fallback`` when the registry is unavailable or the capability
    is missing (preserves prior behavior). The lookup is intentionally
    defensive so presets stay importable in minimal test environments.
    """
    try:
        from brain_alpha_ops.data.capability_registry import (
            CapabilityResolutionError,
            get_registry,
        )
        return get_registry().default_value(kind)
    except CapabilityResolutionError:
        logger.debug("preset default for %s unresolved; using fallback", kind)
    except Exception as exc:  # pragma: no cover - defensive import guard
        logger.debug("capability registry unavailable for preset default %s: %s", kind, redact_error_message(exc))
    return fallback


def _build_settings(**overrides: Any) -> BrainSettings:
    """Build a BrainSettings from registry defaults + preset overrides.

    Each non-overridden field is sourced from the capability registry's
    default value for the corresponding kind; ``BrainSettings`` defaults
    act as the final fallback when the registry cannot resolve a kind.
    """
    defaults: dict[str, Any] = {
        "instrumentType": "EQUITY",
        "region": _registry_default("region", "USA"),
        "universe": _registry_default("universe", "TOP3000"),
        "delay": _registry_default("delay", 1),
        "decay": _registry_default("decay", 10),
        "neutralization": _registry_default("neutralization", "SUBINDUSTRY"),
        "truncation": _registry_default("truncation", 0.05),
        "pasteurization": _registry_default("pasteurization", "ON"),
        "unitHandling": _registry_default("unit_handling", "VERIFY"),
        "nanHandling": _registry_default("nan_handling", "ON"),
        "language": _registry_default("language", "FASTEXPR"),
    }
    defaults.update(overrides)
    return BrainSettings(**defaults)


# ═══════════════════════════════════════════════════════════════════════
# Preset Configurations
# ═══════════════════════════════════════════════════════════════════════

def _momentum_research() -> OpsConfig:
    """Preset for momentum factor research."""
    config = OpsConfig()
    config.settings = _build_settings()
    config.budget = ResearchBudget(
        max_cycles=100,
        max_candidates_per_cycle=20,
        retained_alpha_pool_size=50,
    )
    config.scoring = ScoringConfig(
        prior_layer_weight=0.30,
        empirical_layer_weight=0.45,
        checklist_layer_weight=0.25,
    )
    return config


def _value_research() -> OpsConfig:
    """Preset for value factor research."""
    config = OpsConfig()
    config.settings = _build_settings()
    config.budget = ResearchBudget(
        max_cycles=150,
        max_candidates_per_cycle=15,
        retained_alpha_pool_size=40,
    )
    config.scoring = ScoringConfig(
        prior_layer_weight=0.35,
        empirical_layer_weight=0.40,
        checklist_layer_weight=0.25,
    )
    return config


def _low_volatility_research() -> OpsConfig:
    """Preset for low volatility factor research (TOP1000 universe override)."""
    config = OpsConfig()
    config.settings = _build_settings(universe="TOP1000")
    config.budget = ResearchBudget(
        max_cycles=80,
        max_candidates_per_cycle=10,
        retained_alpha_pool_size=30,
    )
    config.scoring = ScoringConfig(
        prior_layer_weight=0.25,
        empirical_layer_weight=0.50,
        checklist_layer_weight=0.25,
    )
    return config


def _quality_research() -> OpsConfig:
    """Preset for quality/profitability factor research."""
    config = OpsConfig()
    config.settings = _build_settings()
    config.budget = ResearchBudget(
        max_cycles=120,
        max_candidates_per_cycle=25,
        retained_alpha_pool_size=60,
    )
    config.scoring = ScoringConfig(
        prior_layer_weight=0.30,
        empirical_layer_weight=0.45,
        checklist_layer_weight=0.25,
    )
    return config


def _aggressive_research() -> OpsConfig:
    """Preset for aggressive/high-turnover research (delay=0 override)."""
    config = OpsConfig()
    config.settings = _build_settings(delay=0)
    config.budget = ResearchBudget(
        max_cycles=200,
        max_candidates_per_cycle=30,
        retained_alpha_pool_size=80,
    )
    config.scoring = ScoringConfig(
        prior_layer_weight=0.20,
        empirical_layer_weight=0.55,
        checklist_layer_weight=0.25,
    )
    return config


# ═══════════════════════════════════════════════════════════════════════
# Preset Registry
# ═══════════════════════════════════════════════════════════════════════

_PRESETS: dict[str, PresetConfig] = {
    "momentum_research": PresetConfig(
        name="momentum_research",
        description="Momentum factor research with standard settings",
        config=_momentum_research(),
    ),
    "value_research": PresetConfig(
        name="value_research",
        description="Value factor research with longer cycles",
        config=_value_research(),
    ),
    "low_volatility_research": PresetConfig(
        name="low_volatility_research",
        description="Low volatility factor research with TOP1000 universe",
        config=_low_volatility_research(),
    ),
    "quality_research": PresetConfig(
        name="quality_research",
        description="Quality/profitability factor research",
        config=_quality_research(),
    ),
    "aggressive_research": PresetConfig(
        name="aggressive_research",
        description="Aggressive research with high candidate count",
        config=_aggressive_research(),
    ),
}


def get_preset(name: str) -> OpsConfig:
    """Get a preset configuration by name.

    Args:
        name: Preset name (e.g., "momentum_research")

    Returns:
        OpsConfig instance with preset settings

    Raises:
        ValueError: If preset name is not found
    """
    if name not in _PRESETS:
        available = ", ".join(sorted(_PRESETS.keys()))
        raise ValueError(f"Unknown preset '{name}'. Available presets: {available}")
    return _PRESETS[name].config


def list_presets() -> list[dict[str, str]]:
    """List all available presets.

    Returns:
        List of dicts with name and description
    """
    return [
        {"name": p.name, "description": p.description}
        for p in _PRESETS.values()
    ]


# Backward-compatible public alias. External callers (and the spec's
# verification command) import ``PRESETS`` directly; the underscore-prefixed
# ``_PRESETS`` is preserved for any internal references.
PRESETS: dict[str, PresetConfig] = _PRESETS


__all__ = [
    "PRESETS",
    "PresetConfig",
    "get_preset",
    "list_presets",
]

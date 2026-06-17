"""Configuration presets for common use cases.

This module provides pre-configured settings for common research scenarios.

Usage:
    from brain_alpha_ops.presets import get_preset

    # Get a preset configuration
    config = get_preset("momentum_research")
    
    # Or use a specific preset
    from brain_alpha_ops.presets import MOMENTUM_RESEARCH
    config = MOMENTUM_RESEARCH
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brain_alpha_ops.config import OpsConfig, BrainSettings, ResearchBudget, ScoringConfig, QualityThresholds


@dataclass(frozen=True)
class PresetConfig:
    """A named configuration preset."""
    name: str
    description: str
    config: OpsConfig


# ═══════════════════════════════════════════════════════════════════════
# Preset Configurations
# ═══════════════════════════════════════════════════════════════════════

def _momentum_research() -> OpsConfig:
    """Preset for momentum factor research."""
    config = OpsConfig()
    config.settings = BrainSettings(
        instrumentType="EQUITY",
        region="USA",
        delay=1,
        universe="TOP3000",
    )
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
    config.settings = BrainSettings(
        instrumentType="EQUITY",
        region="USA",
        delay=1,
        universe="TOP3000",
    )
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
    """Preset for low volatility factor research."""
    config = OpsConfig()
    config.settings = BrainSettings(
        instrumentType="EQUITY",
        region="USA",
        delay=1,
        universe="TOP1000",
    )
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
    config.settings = BrainSettings(
        instrumentType="EQUITY",
        region="USA",
        delay=1,
        universe="TOP3000",
    )
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
    """Preset for aggressive/high-turnover research."""
    config = OpsConfig()
    config.settings = BrainSettings(
        instrumentType="EQUITY",
        region="USA",
        delay=0,
        universe="TOP3000",
    )
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

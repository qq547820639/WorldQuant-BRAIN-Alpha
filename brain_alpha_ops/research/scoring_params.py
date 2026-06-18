"""Parameterized prior scoring system with persistence and calibration hooks.

This module moves the 8 hard-coded prior_score dimensions in scoring.py behind
tunable parameters. Parameters are persisted as JSON in
data/scoring_calibration.json and can be calibrated by AutoCalibrator.

Usage::

    from brain_alpha_ops.research.scoring_params import ScoringParams

    # Defaults matching the current hard-coded behavior.
    params = ScoringParams.defaults()

    # Load from the calibration file.
    params = ScoringParams.load("data")

    # Persist the parameters.
    params.save("data")

    # Apply to prior_score.
    from brain_alpha_ops.research.scoring import prior_score
    result = prior_score(candidate, params=params)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

# ═══════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DimensionParam:
    """Tunable parameters for one scoring dimension.

    Different dimension types use different parameter subsets:
    - linear penalty (structure, field_operator_support): base_score, penalty_per_unit, penalty_threshold, floor, cap
    - threshold (horizon_turnover_proxy): threshold_low, threshold_high, score_in_range, score_out_range, score_no_data
    - categorical (diversity, data_compliance, explainability, risk_control_proxy): high_value_set, high_score, low_score
    - keyword-based (economic_logic): concept_scores dictionary
    """
    name: str                                    # Dimension name, such as "structure".
    enabled: bool = True                         # Whether this dimension is enabled.
    weight: float = 0.12                         # Weight inside prior_score.

    # Common parameters.
    floor: float = 0.0                           # Score floor.
    cap: float = 100.0                           # Score cap.

    # Linear-penalty parameters.
    base_score: float = 90.0                     # Base score.
    penalty_per_unit: float = 8.0                # Penalty for each unit above threshold.
    penalty_threshold: float = 4.0               # Penalty starts above this threshold.
    bonus_per_unit: float = 0.0                  # Per-unit bonus for positive dimensions.
    bonus_base: float = 0.0                      # Bonus base value.

    # Threshold parameters.
    threshold_low: float = 0.0                   # Lower window bound.
    threshold_high: float = 0.0                  # Upper window bound.
    score_in_range: float = 82.0                 # Score when inside range.
    score_out_range: float = 68.0                # Score when outside range.
    score_no_data: float = 50.0                  # Score when data is unavailable.

    # Categorical parameters.
    high_value_set: list[str] | None = None   # High-value set.
    high_score: float = 80.0                     # Score on high-value match.
    low_score: float = 60.0                      # Score when not matched.

    # Multi-condition parameters for risk_control_proxy.
    tier_3_score: float = 84.0                   # Three conditions met.
    tier_2_score: float = 66.0                   # Two conditions met.
    tier_1_score: float = 48.0                   # One or zero conditions met.

    # Keyword-based parameters for economic_logic.
    concept_scores: dict[int, int] | None = None  # {concept_count: score}
    fallback_length_threshold: int = 60           # Fallback hypothesis length threshold.
    fallback_length_score: int = 52               # Score when fallback length is sufficient.
    fallback_insufficient_score: int = 40         # Score when fallback length is insufficient.


@dataclass
class ScoringParams:
    """Complete calibratable scoring parameter set.

    Includes DimensionParam values for 8 dimensions plus layer weights and
    metadata.
    """
    schema_version: str = "scoring_calibration-v1.0"
    dimensions: dict[str, DimensionParam] = field(default_factory=dict)
    layer_weights: dict[str, float] = field(default_factory=lambda: {
        "prior": 0.30, "empirical": 0.45, "checklist": 0.25
    })
    calibration_quality: dict[str, float] = field(default_factory=lambda: {
        "r_squared": 0.0, "mean_abs_error": 0.0, "sample_size": 0
    })
    calibrated_at: str = ""

    @classmethod
    def defaults(cls) -> "ScoringParams":
        """Return defaults matching the current hard-coded prior scoring behavior."""
        dims = {}

        # 1. economic_logic: keyword-concept detection.
        dims["economic_logic"] = DimensionParam(
            name="economic_logic",
            weight=0.18,
            floor=40.0, cap=92.0,
            concept_scores={4: 92, 3: 85, 2: 78, 1: 68},
            fallback_length_threshold=60,
            fallback_length_score=52,
            fallback_insufficient_score=40,
        )

        # 2. structure: linear penalty for operator count.
        # Original formula: max(25, 90 - max(0, len(operators) - 4) * 8)
        dims["structure"] = DimensionParam(
            name="structure",
            weight=0.14,
            floor=25.0, cap=90.0,
            base_score=90.0,
            penalty_per_unit=8.0,
            penalty_threshold=4.0,
        )

        # 3. field_operator_support: field and operator bonus configuration.
        # Original formula: min(92, 42 + len(fields) * 8 + len(set(operators)) * 4)
        dims["field_operator_support"] = DimensionParam(
            name="field_operator_support",
            weight=0.16,
            floor=42.0, cap=92.0,
            base_score=42.0,
            bonus_per_unit=8.0,  # Field bonus.
            # Operator bonus is handled separately during scoring (4 points/operator).
        )

        # 4. data_compliance: binary score.
        # Original formula: 82 if fields else 35
        dims["data_compliance"] = DimensionParam(
            name="data_compliance",
            weight=0.12,
            high_score=82.0,
            low_score=35.0,
        )

        # 5. horizon_turnover_proxy: window threshold.
        # Original formula: 82 if 5 <= median_window <= 90 else 68 if median_window else 50
        dims["horizon_turnover_proxy"] = DimensionParam(
            name="horizon_turnover_proxy",
            weight=0.14,
            threshold_low=5.0,
            threshold_high=90.0,
            score_in_range=82.0,
            score_out_range=68.0,
            score_no_data=50.0,
        )

        # 6. risk_control_proxy: three-condition tiering.
        # Original formula: 84 if has_cs and has_ts and has_rc else 66 if has_cs and has_ts else 48
        dims["risk_control_proxy"] = DimensionParam(
            name="risk_control_proxy",
            weight=0.14,
            tier_3_score=84.0,
            tier_2_score=66.0,
            tier_1_score=48.0,
        )

        # 7. diversity: category match.
        # Original formula: 80 if family in {"Liquidity", "Volatility", "Hybrid"} else 65
        dims["diversity"] = DimensionParam(
            name="diversity",
            weight=0.07,
            high_value_set=["Liquidity", "Volatility", "Hybrid"],
            high_score=80.0,
            low_score=65.0,
        )

        # 8. explainability: expression length.
        # Original formula: 85 if len(expression) < 140 else 60
        dims["explainability"] = DimensionParam(
            name="explainability",
            weight=0.05,
            threshold_high=140.0,
            score_in_range=85.0,
            score_out_range=60.0,
        )

        return cls(dimensions=dims)

    # Persistence

    def save(self, storage_dir: str = "data") -> str:
        """Persist to data/scoring_calibration.json."""
        os.makedirs(storage_dir, exist_ok=True)
        filepath = os.path.join(storage_dir, "scoring_calibration.json")
        data = {
            "schema_version": self.schema_version,
            "calibrated_at": self.calibrated_at,
            "layer_weights": self.layer_weights,
            "calibration_quality": self.calibration_quality,
            "dimensions": {
                name: _dimension_to_dict(d) for name, d in self.dimensions.items()
            },
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return filepath

    @classmethod
    def load(cls, storage_dir: str = "data") -> "ScoringParams | None":
        """Load parameters from data/scoring_calibration.json, or None if absent."""
        filepath = os.path.join(storage_dir, "scoring_calibration.json")
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        dims = {}
        for name, d in data.get("dimensions", {}).items():
            dims[name] = _dimension_from_dict(d)
            dims[name].name = name  # Keep name aligned with the dict key.

        return cls(
            schema_version=data.get("schema_version", "scoring_calibration-v1.0"),
            dimensions=dims,
            layer_weights=data.get("layer_weights", {"prior": 0.30, "empirical": 0.45, "checklist": 0.25}),
            calibration_quality=data.get("calibration_quality", {"r_squared": 0.0, "mean_abs_error": 0.0, "sample_size": 0}),
            calibrated_at=data.get("calibrated_at", ""),
        )

    def get_weights_override(self) -> dict[str, float]:
        """Return dimension weights suitable for prior_score weights_override."""
        return {name: d.weight for name, d in self.dimensions.items() if d.enabled}

    def get_layer_weights(self) -> dict[str, float]:
        """Return the three-layer weight mapping."""
        return dict(self.layer_weights)

    def get_dimension(self, name: str) -> DimensionParam | None:
        """Return parameters for one dimension."""
        return self.dimensions.get(name)


# Serialization helpers

def _dimension_to_dict(d: DimensionParam) -> dict[str, Any]:
    """Convert DimensionParam to a JSON-serializable dict."""
    result = asdict(d)
    # Remove fields that should not be persisted.
    result.pop("name", None)
    return result


def _dimension_from_dict(d: dict[str, Any]) -> DimensionParam:
    """Restore DimensionParam from a dict, filling missing fields with defaults."""
    return DimensionParam(
        name=d.get("name", ""),
        enabled=d.get("enabled", True),
        weight=d.get("weight", 0.12),
        floor=d.get("floor", 0.0),
        cap=d.get("cap", 100.0),
        base_score=d.get("base_score", 90.0),
        penalty_per_unit=d.get("penalty_per_unit", 8.0),
        penalty_threshold=d.get("penalty_threshold", 4.0),
        bonus_per_unit=d.get("bonus_per_unit", 0.0),
        bonus_base=d.get("bonus_base", 0.0),
        threshold_low=d.get("threshold_low", 0.0),
        threshold_high=d.get("threshold_high", 0.0),
        score_in_range=d.get("score_in_range", 82.0),
        score_out_range=d.get("score_out_range", 68.0),
        score_no_data=d.get("score_no_data", 50.0),
        high_value_set=d.get("high_value_set"),
        high_score=d.get("high_score", 80.0),
        low_score=d.get("low_score", 60.0),
        tier_3_score=d.get("tier_3_score", 84.0),
        tier_2_score=d.get("tier_2_score", 66.0),
        tier_1_score=d.get("tier_1_score", 48.0),
        concept_scores=d.get("concept_scores"),
        fallback_length_threshold=d.get("fallback_length_threshold", 60),
        fallback_length_score=d.get("fallback_length_score", 52),
        fallback_insufficient_score=d.get("fallback_insufficient_score", 40),
    )

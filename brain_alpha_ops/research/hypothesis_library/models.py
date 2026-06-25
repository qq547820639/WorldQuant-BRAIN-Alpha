"""Data models for the Hypothesis Library.

Extracted from the original ``hypothesis_library.py`` monolith. Defines
the dataclasses used to represent market hypotheses, their expression
families, field categories, failure modes, adaptation config, experience
weights, and generation traceability metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Rationale:
    """Economics / behavioural finance theory underpinning a hypothesis."""
    theory: str
    academic_refs: list[str] = field(default_factory=list)
    behavioral_bias: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rationale":
        return cls(
            theory=data.get("theory", ""),
            academic_refs=[str(r) for r in data.get("academic_refs", [])],
            behavioral_bias=str(data.get("behavioral_bias", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"theory": self.theory}
        if self.academic_refs:
            result["academic_refs"] = self.academic_refs
        if self.behavioral_bias:
            result["behavioral_bias"] = self.behavioral_bias
        return result


@dataclass
class FieldCategoryDef:
    """Semantic field category — not a concrete field name, but a grouping label."""
    category: str
    priority: str = "P1"           # "P0" | "P1"
    examples: list[str] = field(default_factory=list)
    weight: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldCategoryDef":
        return cls(
            category=str(data.get("category", "")),
            priority=str(data.get("priority", "P1")),
            examples=[str(e) for e in data.get("examples", [])],
            weight=float(data.get("weight", 1.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "category": self.category,
            "priority": self.priority,
            "weight": self.weight,
        }
        if self.examples:
            result["examples"] = self.examples
        return result


@dataclass
class ExpressionFamily:
    """A structural variant of an expression within a hypothesis."""
    id: str
    structure: str
    description: str = ""
    windows: list[int] = field(default_factory=list)
    windows_short: list[int] = field(default_factory=list)
    windows_long: list[int] = field(default_factory=list)
    weight: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExpressionFamily":
        return cls(
            id=str(data.get("id", "")),
            structure=str(data.get("structure", "")),
            description=str(data.get("description", "")),
            windows=[int(w) for w in data.get("windows", [])],
            windows_short=[int(w) for w in data.get("windows_short", [])],
            windows_long=[int(w) for w in data.get("windows_long", [])],
            weight=float(data.get("weight", 1.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "structure": self.structure,
            "description": self.description,
            "weight": self.weight,
        }
        if self.windows:
            result["windows"] = self.windows
        if self.windows_short:
            result["windows_short"] = self.windows_short
        if self.windows_long:
            result["windows_long"] = self.windows_long
        return result

    def get_all_windows(self) -> list[int]:
        """Return all window sizes (regular + short + long, deduplicated)."""
        all_win: list[int] = list(self.windows) if self.windows else []
        all_win.extend(self.windows_short)
        all_win.extend(self.windows_long)
        if not all_win:
            all_win = [3, 6, 12]  # sensible defaults
        return sorted(set(all_win))


@dataclass
class FailureMode:
    """Expected failure mode with mitigation guidance."""
    gate: str
    reason: str = ""
    mitigation: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FailureMode":
        return cls(
            gate=str(data.get("gate", "")),
            reason=str(data.get("reason", "")),
            mitigation=str(data.get("mitigation", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"gate": self.gate}
        if self.reason:
            result["reason"] = self.reason
        if self.mitigation:
            result["mitigation"] = self.mitigation
        return result


@dataclass
class AdaptationConfig:
    """Context adaptation configuration for a hypothesis."""
    preferred_regions: list[str] = field(default_factory=list)
    preferred_universes: list[str] = field(default_factory=list)
    preferred_delays: list[int] = field(default_factory=list)
    unsuitable_regions: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AdaptationConfig":
        return cls(
            preferred_regions=[str(r) for r in data.get("preferred_regions", [])],
            preferred_universes=[str(u) for u in data.get("preferred_universes", [])],
            preferred_delays=[int(d) for d in data.get("preferred_delays", [])],
            unsuitable_regions=[str(r) for r in data.get("unsuitable_regions", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "preferred_regions": self.preferred_regions,
            "preferred_universes": self.preferred_universes,
            "preferred_delays": self.preferred_delays,
        }
        if self.unsuitable_regions:
            result["unsuitable_regions"] = self.unsuitable_regions
        return result


@dataclass
class ExperienceWeights:
    """Runtime-updated experience weights for adaptive selection."""
    overall: float = 1.0
    field_category_weights: dict[str, float] = field(default_factory=dict)
    expression_family_weights: dict[str, float] = field(default_factory=dict)
    window_weights: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperienceWeights":
        data = data if isinstance(data, dict) else {}

        def weight_map(value: Any) -> dict[str, float]:
            if not isinstance(value, dict):
                return {}
            return {str(k): float(v) for k, v in value.items()}

        return cls(
            overall=float(data.get("overall", 1.0)),
            field_category_weights=weight_map(data.get("field_category_weights")),
            expression_family_weights=weight_map(data.get("expression_family_weights")),
            window_weights=weight_map(data.get("window_weights")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "field_category_weights": dict(self.field_category_weights),
            "expression_family_weights": dict(self.expression_family_weights),
            "window_weights": dict(self.window_weights),
        }

    def _ensure_window_key(self, w: int) -> str:
        return str(w)


@dataclass
class Hypothesis:
    """A complete market hypothesis definition."""
    id: str = ""
    name: str = ""
    category: str = ""
    version: str = "1.0.0"
    rationale: Rationale = field(default_factory=Rationale)
    field_categories: list[FieldCategoryDef] = field(default_factory=list)
    expression_families: list[ExpressionFamily] = field(default_factory=list)
    expected_failure_modes: list[FailureMode] = field(default_factory=list)
    adaptation: AdaptationConfig = field(default_factory=AdaptationConfig)
    experience_weights: ExperienceWeights = field(default_factory=ExperienceWeights)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hypothesis":
        h_data = data.get("hypothesis", data)
        rationale = Rationale.from_dict(h_data.get("rationale", {}))
        field_cats = [FieldCategoryDef.from_dict(fc) for fc in h_data.get("field_categories", [])]
        expr_fams = [ExpressionFamily.from_dict(ef) for ef in h_data.get("expression_families", [])]
        failures = [FailureMode.from_dict(fm) for fm in h_data.get("expected_failure_modes", [])]
        adaptation = AdaptationConfig.from_dict(h_data.get("adaptation", {}))
        weights = ExperienceWeights.from_dict(h_data.get("experience_weights", {}))
        return cls(
            id=str(h_data.get("id", "")),
            name=str(h_data.get("name", "")),
            category=str(h_data.get("category", "")),
            version=str(h_data.get("version", "1.0.0")),
            rationale=rationale,
            field_categories=field_cats,
            expression_families=expr_fams,
            expected_failure_modes=failures,
            adaptation=adaptation,
            experience_weights=weights,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "version": self.version,
            "rationale": self.rationale.to_dict(),
            "field_categories": [fc.to_dict() for fc in self.field_categories],
            "expression_families": [ef.to_dict() for ef in self.expression_families],
            "expected_failure_modes": [fm.to_dict() for fm in self.expected_failure_modes],
            "adaptation": self.adaptation.to_dict(),
            "experience_weights": self.experience_weights.to_dict(),
        }


@dataclass
class GenerationMeta:
    """Traceability metadata attached to each generated Candidate."""
    mode: str = ""                           # "hypothesis_driven" | "experience_feedback" | "random_exploration"
    hypothesis_id: str = ""
    hypothesis_name: str = ""
    expression_family_id: str = ""
    field_category: str = ""
    selected_fields: list[str] = field(default_factory=list)
    region: str = ""
    universe: str = ""
    delay: int = 0
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GenerationMeta":
        return cls(
            mode=str(data.get("mode", "")),
            hypothesis_id=str(data.get("hypothesis_id", "")),
            hypothesis_name=str(data.get("hypothesis_name", "")),
            expression_family_id=str(data.get("expression_family_id", "")),
            field_category=str(data.get("field_category", "")),
            selected_fields=[str(f) for f in data.get("selected_fields", [])],
            region=str(data.get("region", "")),
            universe=str(data.get("universe", "")),
            delay=int(data.get("delay", 0)),
            timestamp=str(data.get("timestamp", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_name": self.hypothesis_name,
            "expression_family_id": self.expression_family_id,
            "field_category": self.field_category,
            "selected_fields": list(self.selected_fields),
            "region": self.region,
            "universe": self.universe,
            "delay": self.delay,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Serialize to JSON string for storage in Candidate.template_source."""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)

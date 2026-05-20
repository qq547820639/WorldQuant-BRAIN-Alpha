"""Hypothesis Library — structured market hypothesis definitions and experience-weighted management.

Provides:
  - Dataclasses: Hypothesis, ExpressionFamily, FieldCategoryDef, AdaptationConfig,
    FailureMode, Rationale, ExperienceWeights, GenerationMeta
  - HypothesisLibrary: YAML-based loading, querying, and experience weight management

Usage::

    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary

    library = HypothesisLibrary("brain_alpha_ops/research/hypotheses").load_all()
    all_h = library.get_all()
    momentum_h = library.get_by_id("earnings_revision_momentum")
    library.update_weights("earnings_revision_momentum",
                           field_cat_weights={"earnings_estimate_revision": 1.5},
                           expr_fam_weights={"revision_diff": 1.3},
                           window_weights={3: 1.2})
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Rationale:
    """Economics / behavioural finance theory underpinning a hypothesis."""
    theory: str
    academic_refs: List[str] = field(default_factory=list)
    behavioral_bias: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rationale":
        return cls(
            theory=data.get("theory", ""),
            academic_refs=[str(r) for r in data.get("academic_refs", [])],
            behavioral_bias=str(data.get("behavioral_bias", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"theory": self.theory}
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
    examples: List[str] = field(default_factory=list)
    weight: float = 1.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldCategoryDef":
        return cls(
            category=str(data.get("category", "")),
            priority=str(data.get("priority", "P1")),
            examples=[str(e) for e in data.get("examples", [])],
            weight=float(data.get("weight", 1.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
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
    windows: List[int] = field(default_factory=list)
    windows_short: List[int] = field(default_factory=list)
    windows_long: List[int] = field(default_factory=list)
    weight: float = 1.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpressionFamily":
        return cls(
            id=str(data.get("id", "")),
            structure=str(data.get("structure", "")),
            description=str(data.get("description", "")),
            windows=[int(w) for w in data.get("windows", [])],
            windows_short=[int(w) for w in data.get("windows_short", [])],
            windows_long=[int(w) for w in data.get("windows_long", [])],
            weight=float(data.get("weight", 1.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
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

    def get_all_windows(self) -> List[int]:
        """Return all window sizes (regular + short + long, deduplicated)."""
        all_win: List[int] = list(self.windows) if self.windows else []
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
    def from_dict(cls, data: Dict[str, Any]) -> "FailureMode":
        return cls(
            gate=str(data.get("gate", "")),
            reason=str(data.get("reason", "")),
            mitigation=str(data.get("mitigation", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"gate": self.gate}
        if self.reason:
            result["reason"] = self.reason
        if self.mitigation:
            result["mitigation"] = self.mitigation
        return result


@dataclass
class AdaptationConfig:
    """Context adaptation configuration for a hypothesis."""
    preferred_regions: List[str] = field(default_factory=list)
    preferred_universes: List[str] = field(default_factory=list)
    preferred_delays: List[int] = field(default_factory=list)
    unsuitable_regions: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdaptationConfig":
        return cls(
            preferred_regions=[str(r) for r in data.get("preferred_regions", [])],
            preferred_universes=[str(u) for u in data.get("preferred_universes", [])],
            preferred_delays=[int(d) for d in data.get("preferred_delays", [])],
            unsuitable_regions=[str(r) for r in data.get("unsuitable_regions", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
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
    field_category_weights: Dict[str, float] = field(default_factory=dict)
    expression_family_weights: Dict[str, float] = field(default_factory=dict)
    window_weights: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperienceWeights":
        data = data or {}
        return cls(
            overall=float(data.get("overall", 1.0)),
            field_category_weights={str(k): float(v) for k, v in data.get("field_category_weights", {}).items()},
            expression_family_weights={str(k): float(v) for k, v in data.get("expression_family_weights", {}).items()},
            window_weights={str(k): float(v) for k, v in data.get("window_weights", {}).items()},
        )

    def to_dict(self) -> Dict[str, Any]:
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
    field_categories: List[FieldCategoryDef] = field(default_factory=list)
    expression_families: List[ExpressionFamily] = field(default_factory=list)
    expected_failure_modes: List[FailureMode] = field(default_factory=list)
    adaptation: AdaptationConfig = field(default_factory=AdaptationConfig)
    experience_weights: ExperienceWeights = field(default_factory=ExperienceWeights)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Hypothesis":
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

    def to_dict(self) -> Dict[str, Any]:
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
    selected_fields: List[str] = field(default_factory=list)
    region: str = ""
    universe: str = ""
    delay: int = 0
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GenerationMeta":
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

    def to_dict(self) -> Dict[str, Any]:
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


# ═══════════════════════════════════════════════════════════════════════
# HypothesisLibrary
# ═══════════════════════════════════════════════════════════════════════

class HypothesisLibrary:
    """Loads, indexes, and manages hypothesis definitions from YAML files.

    Usage::

        lib = HypothesisLibrary("brain_alpha_ops/research/hypotheses").load_all()
        all_h = lib.get_all()
        h = lib.get_by_id("earnings_revision_momentum")
        lib.update_weights("earnings_revision_momentum",
                           field_cat_weights={"earnings_estimate_revision": 1.5})
    """

    def __init__(self, directory: str | Path) -> None:
        self._directory: Path = Path(directory)
        self._hypotheses: Dict[str, Hypothesis] = {}
        self._by_category: Dict[str, List[Hypothesis]] = {}
        self._file_paths: Dict[str, Path] = {}

    # ── Loading ──────────────────────────────────────────────────────

    def load_all(self) -> "HypothesisLibrary":
        """Scan the hypothesis directory and load all .yaml files.

        Skips _schema.yaml and files starting with '_'.
        Returns self for method chaining.
        """
        if not self._directory.exists():
            logger.warning("HypothesisLibrary: directory %s does not exist.", self._directory)
            return self

        self._hypotheses.clear()
        self._by_category.clear()
        self._file_paths.clear()

        yaml_files = sorted(
            p for p in self._directory.rglob("*.yaml")
            if not p.name.startswith("_")
        )
        for path in yaml_files:
            try:
                hypothesis = self._load_file(path)
                if hypothesis and hypothesis.id:
                    self._hypotheses[hypothesis.id] = hypothesis
                    self._file_paths[hypothesis.id] = path
                    cat = hypothesis.category.lower()
                    self._by_category.setdefault(cat, []).append(hypothesis)
            except Exception as exc:
                logger.error("HypothesisLibrary: failed to load %s: %s", path, exc)

        self._validate_weights()
        logger.info(
            "HypothesisLibrary: loaded %d hypotheses from %s",
            len(self._hypotheses), self._directory,
        )
        return self

    def reload(self) -> "HypothesisLibrary":
        """Re-load all hypothesis files from disk, discarding runtime weight changes."""
        return self.load_all()

    # ── Query ────────────────────────────────────────────────────────

    def get_all(self) -> List[Hypothesis]:
        """Return all loaded hypotheses."""
        return list(self._hypotheses.values())

    def get_by_id(self, hypothesis_id: str) -> Optional[Hypothesis]:
        """Return a hypothesis by its unique ID, or None."""
        return self._hypotheses.get(hypothesis_id)

    def get_by_category(self, category: str) -> List[Hypothesis]:
        """Return all hypotheses matching *category* (case-insensitive)."""
        return list(self._by_category.get(category.lower(), []))

    def get_ids(self) -> List[str]:
        """Return all hypothesis IDs."""
        return list(self._hypotheses.keys())

    @property
    def count(self) -> int:
        """Number of loaded hypotheses."""
        return len(self._hypotheses)

    # ── Weight Management ────────────────────────────────────────────

    def update_weights(
        self,
        hypothesis_id: str,
        field_cat_weights: Optional[Dict[str, float]] = None,
        expr_fam_weights: Optional[Dict[str, float]] = None,
        window_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        """Update experience weights using EMA smoothing::

            new = 0.8 * old + 0.2 * update

        Parameters
        ----------
        hypothesis_id:
            ID of the hypothesis to update.
        field_cat_weights:
            Mapping of field category name → winner ratio (0.0–1.0).
        expr_fam_weights:
            Mapping of expression family ID → winner ratio (0.0–1.0).
        window_weights:
            Mapping of window (as int key) → winner ratio (0.0–1.0).
            Keys are automatically converted to str for internal storage.
        """
        hyp = self._hypotheses.get(hypothesis_id)
        if hyp is None:
            logger.warning("HypothesisLibrary.update_weights: hypothesis '%s' not found.", hypothesis_id)
            return

        alpha = 0.2  # EMA smoothing factor

        # Update field category weights
        if field_cat_weights:
            for fc in hyp.field_categories:
                update = field_cat_weights.get(fc.category)
                if update is not None:
                    fc.weight = 0.8 * fc.weight + 0.2 * max(0.0, min(1.0, float(update)))
                    hyp.experience_weights.field_category_weights[fc.category] = fc.weight

        # Update expression family weights
        if expr_fam_weights:
            for ef in hyp.expression_families:
                update = expr_fam_weights.get(ef.id)
                if update is not None:
                    ef.weight = 0.8 * ef.weight + 0.2 * max(0.0, min(1.0, float(update)))
                    hyp.experience_weights.expression_family_weights[ef.id] = ef.weight

        # Update window weights
        if window_weights:
            raw_windows: Dict[int, float] = {}
            for k, v in window_weights.items():
                w_val = int(k) if isinstance(k, str) else k
                raw_windows[w_val] = max(0.0, min(1.0, float(v)))
            for ef in hyp.expression_families:
                for w in ef.windows:
                    update = window_weights.get(w) or window_weights.get(str(w))
                    if update is not None:
                        key = str(w)
                        old = hyp.experience_weights.window_weights.get(key, 1.0)
                        new_val = 0.8 * old + 0.2 * max(0.0, min(1.0, float(update)))
                        hyp.experience_weights.window_weights[key] = new_val

        # Update overall weight as average of expression family weights
        if hyp.expression_families:
            avg_weight = sum(ef.weight for ef in hyp.expression_families) / len(hyp.expression_families)
            hyp.experience_weights.overall = 0.8 * hyp.experience_weights.overall + 0.2 * avg_weight

        self._validate_weights()

    # ── Internals ────────────────────────────────────────────────────

    def _load_file(self, path: Path) -> Optional[Hypothesis]:
        """Load a single hypothesis YAML file and return a Hypothesis object."""
        with open(path, "r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}

        if not isinstance(raw, dict) or "hypothesis" not in raw:
            logger.warning("HypothesisLibrary._load_file: %s missing top-level 'hypothesis' key.", path)
            return None

        hyp = Hypothesis.from_dict(raw)
        if not hyp.id:
            logger.warning("HypothesisLibrary._load_file: %s has empty 'id'.", path)
            return None
        return hyp

    def _validate_weights(self) -> None:
        """Ensure all experience weights are non-negative."""
        for hyp in self._hypotheses.values():
            ew = hyp.experience_weights
            ew.overall = max(0.0, ew.overall)
            for fc in hyp.field_categories:
                fc.weight = max(0.0, fc.weight)
            for ef in hyp.expression_families:
                ef.weight = max(0.0, ef.weight)
            ew.field_category_weights = {k: max(0.0, v) for k, v in ew.field_category_weights.items()}
            ew.expression_family_weights = {k: max(0.0, v) for k, v in ew.expression_family_weights.items()}
            ew.window_weights = {k: max(0.0, v) for k, v in ew.window_weights.items()}

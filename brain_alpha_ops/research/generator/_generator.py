"""``CandidateGenerator`` class core — main public API and small methods.

Heavy method bodies (fallback/dynamic generation, field-pool building,
expression filtering, guidance configuration) are split into sibling
modules (``_helpers.py``, ``_filters.py``) and attached as class
attributes — matching the existing ``expression_builder`` pattern that
keeps each sub-module focused.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
    expression_similarity,
    ordered_operators,
    profile_expression,
)
from brain_alpha_ops.research.fallback_generation import (
    high_turnover_generation_risk_reasons,
    is_high_turnover_generation_risk,
)
from brain_alpha_ops.research.field_quality import (
    filter_generation_fields,
    generation_field_ids,
)
from brain_alpha_ops.research.generator_metadata import (
    _expression_operators_are_official,
    _load_official_operator_names,
    _load_operators_windows,
    expression_windows_within_constraints,
)
from brain_alpha_ops.scoring.local_quality import (
    LocalQualityConfig,
    extract_fields,
    extract_operators,
    local_quality,
    nesting_depth,
)

# Imports of split method bodies (attached as class attributes below).
from brain_alpha_ops.research.generator._filters import (
    FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD,
    _build_official_field_pool,
    _expression_forbidden,
    _expression_satisfies_strict_preferred_constraints,
    _is_observability_avoided,
    _official_preferred_fields,
    set_experience_guidance,
    set_knowledge_constraints,
    set_observability_guidance,
)
from brain_alpha_ops.research.generator._helpers import (
    _BUILTIN_FALLBACK_TEMPLATES,
    _generate_dynamic,
    _generate_fallback,
    _load_fallback_templates,
    _MAX_EXPRESSION_LENGTH,
    _safe_float,
    update_known_fields,
)

# ---- Backward-compat re-export for Phase 3.x migration ----
from brain_alpha_ops.research.generator_mutation import mutate_expression  # noqa: F401
# Backward-compat: _get_default_windows moved to generator_metadata
from brain_alpha_ops.research.generator_metadata import _get_default_windows  # noqa: F401

if TYPE_CHECKING:
    from brain_alpha_ops.data import FieldDatasetMapper, OfficialDataLoader


# Hardcoded logger name — preserves original ``brain_alpha_ops.research.generator``
# identity for test caplog filtering.
logger = logging.getLogger("brain_alpha_ops.research.generator")


class CandidateGenerator:
    """Generates alpha candidates using official fields & operators.

    Usage::

        from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
        from brain_alpha_ops.research.theme_engine import DynamicThemeEngine
        from brain_alpha_ops.research.dataset_selector import DatasetSelector

        loader = OfficialDataLoader.instance()
        mapper = FieldDatasetMapper(); mapper.build(loader)
        engine = DynamicThemeEngine(loader); engine.build_categories()
        selector = DatasetSelector(); selector.initialize(loader)

        gen = CandidateGenerator(loader, mapper, engine, selector)
        candidates = gen.generate(20, dataset_id="analyst4")
    """

    def __init__(
        self,
        loader: "OfficialDataLoader | None" = None,
        mapper: "FieldDatasetMapper | None" = None,
        theme_engine: "DynamicThemeEngine | None" = None,
        selector: "DatasetSelector | None" = None,
        *,
        max_field_pool_size: int = 50,
        local_quality_config: LocalQualityConfig | None = None,
    ) -> None:
        self._cursor = 0
        self._loader = loader
        self._mapper = mapper
        self._theme_engine = theme_engine
        self._selector = selector
        self._max_field_pool_size = max(10, int(max_field_pool_size))
        self._local_quality_config = local_quality_config
        self._windows, self._winsor_stds = _load_operators_windows(loader)
        self._official_operators = _load_official_operator_names(loader)

        # Lazy init fields/operators from loader
        self._fields: set[str] = set()
        self._operators: set[str] = set()
        self._dataset_id: str = ""

        # P2-2: Experience-guided generation
        self._experience_operators: list[str] = []
        self._experience_windows: list[int] = []
        self._experience_fields: list[str] = []
        self._observability_diversity_boost = False
        self._observability_avoid_keys: set[str] = set()
        self._observability_guidance: dict = {}
        self._knowledge_constraints: dict[str, Any] = {
            "preferred_fields": [],
            "preferred_operators": [],
            "forbidden_patterns": [],
            "strict_preferred_fields": False,
            "strict_preferred_operators": False,
        }

    @property
    def windows(self) -> list[int]:
        return list(self._windows)

    @property
    def winsor_stds(self) -> list[int]:
        return list(self._winsor_stds)

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    def update_context(self, fields: list[dict], operators: list[dict]) -> None:
        """Update known fields/operators (backward-compat, now sourced from loader)."""
        if fields:
            self._fields = set(generation_field_ids(fields))
        if operators:
            names = {str(item.get("name", "")).lower() for item in operators if item.get("name")}
            self._operators = names & self._official_operators if self._official_operators else set()

    def set_dataset(self, dataset_id: str) -> None:
        """Set the active dataset for generation."""
        self._dataset_id = dataset_id
        if self._mapper:
            self._fields = set(generation_field_ids(self._mapper.fields_for(dataset_id)))

    # ------------------------------------------------------------------
    # B-05: Public API for hypothesis weight adjustment from experience feedback
    # ------------------------------------------------------------------
    def adjust_hypothesis_weight(self, hypothesis: str, factor: float) -> None:
        """Public method to adjust hypothesis weight from experience feedback.

        Previously accessed via cross-class private attribute
        (self._generator._library.adjust_weight). This public method
        provides a clean API that callers can use without knowing
        internal library details.
        """
        library = getattr(self, "_library", None)
        if library is not None and hasattr(library, "adjust_weight"):
            library.adjust_weight(hypothesis, factor)

    def generate(self, count: int, dataset_id: str = "") -> list[Candidate]:
        """Generate *count* alpha candidates for *dataset_id*."""
        ds = dataset_id or self._dataset_id

        # If we have theme_engine, use dynamic generation
        if self._theme_engine and ds:
            return self._generate_dynamic(count, ds)

        # Fallback: use existing fields-based generation
        return self._generate_fallback(count, ds)

    # ------------------------------------------------------------------
    # Heavy method bodies — imported from sibling modules and attached
    # as class attributes.  Defined as module-level functions taking
    # ``self`` as the first argument (see ``expression_builder`` pattern).
    # ------------------------------------------------------------------
    _build_official_field_pool = _build_official_field_pool
    _official_preferred_fields = _official_preferred_fields
    set_experience_guidance = set_experience_guidance
    set_observability_guidance = set_observability_guidance
    set_knowledge_constraints = set_knowledge_constraints
    _expression_satisfies_strict_preferred_constraints = _expression_satisfies_strict_preferred_constraints
    _is_observability_avoided = _is_observability_avoided
    _expression_forbidden = _expression_forbidden
    _generate_dynamic = _generate_dynamic
    _generate_fallback = _generate_fallback

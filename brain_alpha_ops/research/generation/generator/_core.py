"""HypothesisDrivenGenerator — main hypothesis-driven alpha generation engine.

The class is defined here with its core public API (``__init__``, ``generate``,
context setters).  Heavy method groups (generation modes, constraints, guidance)
are split into sibling modules and attached as class attributes — matching the
existing ``expression_builder`` pattern that keeps each file focused.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.expression_ast import (
    expression_key,
)
from brain_alpha_ops.research.fallback_generation import (
    is_generated_duplicate,
    is_high_turnover_generation_risk,
)
from brain_alpha_ops.research.field_quality import generation_field_ids
from brain_alpha_ops.research.hypothesis_expression_support import (
    HypothesisExpressionSupport,
)

from .. import expression_builder
from ..context_adapter import ContextAdapter
from ..field_selector import FieldSelector
from ..mode_router import GenerationModeRouter
from ..selectors import ExpressionFamilySelector, HypothesisSelector
from ._constraints import (
    _expression_forbidden,
    _expression_satisfies_strict_preferred_constraints,
    _extract_fields,
    _extract_operators,
    _is_observability_avoided,
    _mark_observability_candidate,
    _prioritize_knowledge_fields,
)
from ._guidance import (
    set_experience_guidance,
    set_knowledge_constraints,
    set_observability_guidance,
)
from ._modes import (
    _generate_bare_fallback,
    _generate_experience_feedback,
    _generate_hypothesis_driven,
    _generate_random_exploration,
    _normalize_generated_expression,
)

if TYPE_CHECKING:
    from brain_alpha_ops.data import FieldDatasetMapper, OfficialDataLoader
    from brain_alpha_ops.research.dataset_selector import DatasetSelector
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

logger = logging.getLogger(__name__)


class HypothesisDrivenGenerator:
    """Generates Alpha candidates using hypothesis-driven strategies.

    Implements the same public API as CandidateGenerator:
      - generate(count, dataset_id) → list[Candidate]
      - update_context(fields, operators)
      - set_dataset(dataset_id)
      - set_experience_guidance(patterns)

    Candidate.template_source stores GenerationMeta as JSON.
    Candidate.source_tags are appended with the generation mode tag.
    """

    def __init__(
        self,
        loader: "OfficialDataLoader | None" = None,
        mapper: "FieldDatasetMapper | None" = None,
        theme_engine: "DynamicThemeEngine | None" = None,
        selector: "DatasetSelector | None" = None,
        library: "HypothesisLibrary | None" = None,
        ratio_str: str = "70/20/10",
    ) -> None:
        self._loader = loader
        self._mapper = mapper
        self._theme_engine = theme_engine
        self._selector = selector
        self._library = library

        # Fields / operators context (mirrors CandidateGenerator)
        self._fields: set[str] = set()
        self._operators: set[str] = set()
        self._dataset_id: str = ""

        # Sub-components
        self._router = GenerationModeRouter(ratio_str)
        self._hyp_selector = (
            HypothesisSelector(library) if library else None
        )
        self._expr_selector = ExpressionFamilySelector()
        self._field_selector = (
            FieldSelector(selector) if selector else None
        )
        self._adapter = ContextAdapter()

        # Experience guidance (from experience.py)
        self._experience_operators: list[str] = []
        self._experience_windows: list[int] = []
        self._experience_fields: list[str] = []
        self._experience_patterns: dict[str, Any] | None = None
        self._observability_diversity_boost: bool = False
        self._observability_avoid_keys: set[str] = set()
        self._observability_guidance: dict[str, Any] = {}
        self._warned_empty_hypothesis_library: bool = False
        self._fallback_cursor: int = 0
        self._knowledge_constraints: dict[str, Any] = {
            "preferred_fields": [],
            "preferred_operators": [],
            "forbidden_patterns": [],
            "strict_preferred_fields": False,
            "strict_preferred_operators": False,
        }

    # ── Public API (CandidateGenerator-compatible) ──────────────────

    def update_context(self, fields: list[Any], operators: list[Any]) -> None:
        """Update known fields/operators."""
        if fields:
            self._fields = set(generation_field_ids(fields))
        if operators:
            if isinstance(operators[0], dict):
                self._operators = {
                    str(item.get("name", "")).lower()
                    for item in operators
                    if item.get("name")
                }
            else:
                self._operators = {str(o).lower() for o in operators}

    def set_dataset(self, dataset_id: str) -> None:
        """Set the active dataset for generation."""
        self._dataset_id = dataset_id
        if self._mapper:
            mapper_fields = self._mapper.fields_for(dataset_id)
            self._fields = set(generation_field_ids(mapper_fields))
        if self._loader:
            try:
                eligible_fields = generation_field_ids(
                    self._loader.get_fields(dataset_id)
                )
                if eligible_fields:
                    self._fields = set(eligible_fields)
            except Exception as exc:
                logger.warning(
                    "generation field eligibility metadata unavailable for dataset_id=%s",
                    dataset_id,
                    exc_info=True,
                )

    def _official_preferred_fields(self, fields: list[str]) -> list[str]:
        if not fields:
            return []
        official_fields = {
            str(field).lower()
            for field in self._fields
            if str(field)
        }
        if not official_fields and self._loader:
            try:
                loaded_fields = self._loader.get_fields(self._dataset_id)
                official_fields = {
                    str(field).lower()
                    for field in generation_field_ids(loaded_fields)
                }
            except Exception as exc:
                logger.warning(
                    "official preferred-field filtering failed closed",
                    exc_info=True,
                )
                official_fields = set()
        return [field for field in fields if field in official_fields]

    def _expression_support(self) -> HypothesisExpressionSupport:
        return HypothesisExpressionSupport(
            fields=self._fields,
            operators=self._operators,
            loader=self._loader,
            dataset_id=self._dataset_id,
            logger=logger,
        )

    def generate(
        self, count: int, dataset_id: str = ""
    ) -> list[Candidate]:
        """Generate *count* alpha candidates for *dataset_id*."""
        ds = dataset_id or self._dataset_id
        candidates: list[Candidate] = []
        attempts = 0
        attempt_limit = max(
            count,
            count
            * (8 if self._observability_diversity_boost else 5),
        )
        seen_keys: set[str] = set()
        seen_expressions: list[str] = []

        while len(candidates) < count and attempts < attempt_limit:
            i = attempts
            attempts += 1
            mode = self._router.route()

            try:
                if mode == "hypothesis_driven":
                    candidate = self._generate_hypothesis_driven(ds)
                elif mode == "experience_feedback":
                    candidate = self._generate_experience_feedback(ds)
                else:
                    candidate = self._generate_random_exploration(ds)

                if candidate is not None:
                    self._try_accept_candidate(
                        candidate, candidates, seen_keys, seen_expressions
                    )
            except Exception as exc:
                logger.warning(
                    "HypothesisDrivenGenerator: %s mode failed for candidate %d: %s",
                    mode,
                    i,
                    redact_error_message(exc),
                )
                # Fallback: try random exploration
                try:
                    fallback = self._generate_random_exploration(ds)
                    if fallback is not None:
                        self._try_accept_candidate(
                            fallback,
                            candidates,
                            seen_keys,
                            seen_expressions,
                        )
                except Exception as exc:
                    logger.warning(
                        "random exploration fallback generation failed",
                        exc_info=True,
                    )
                    continue

        # Log generation summary
        actual = self._router.actual_ratios
        logger.info(
            "HypothesisDrivenGenerator: generated %d/%d candidates. "
            "Mode ratios: H=%.1f%% E=%.1f%% R=%.1f%%",
            len(candidates),
            count,
            actual["hypothesis_driven"] * 100,
            actual["experience_feedback"] * 100,
            actual["random_exploration"] * 100,
        )

        return candidates

    def _try_accept_candidate(
        self,
        candidate: Candidate,
        candidates: list[Candidate],
        seen_keys: set[str],
        seen_expressions: list[str],
    ) -> bool:
        if not self._expression_satisfies_strict_preferred_constraints(
            candidate.expression
        ):
            candidate.lifecycle_status = (
                "strict_preferred_constraints_skipped"
            )
            return False
        if is_high_turnover_generation_risk(candidate.expression):
            candidate.lifecycle_status = "generation_risk_skipped"
            return False
        if is_generated_duplicate(
            candidate.expression, seen_keys, seen_expressions
        ):
            candidate.lifecycle_status = "duplicate_expression_skipped"
            return False
        key = expression_key(candidate.expression)
        if self._observability_diversity_boost:
            if key in seen_keys or self._is_observability_avoided(
                candidate.expression
            ):
                return False
            self._mark_observability_candidate(candidate)
        seen_keys.add(key)
        seen_expressions.append(candidate.expression)
        candidates.append(candidate)
        return True

    # ── Expression Building (attached from expression_builder) ──────

    _build_expression = expression_builder._build_expression
    _normalize_wq_expression_shape = (
        expression_builder._normalize_wq_expression_shape
    )
    _operator_available = expression_builder._operator_available
    _normalize_field_function_calls = (
        expression_builder._normalize_field_function_calls
    )
    _rewrite_field_function_node = (
        expression_builder._rewrite_field_function_node
    )
    _is_field_function_name = expression_builder._is_field_function_name
    _replacement_for_field_function = (
        expression_builder._replacement_for_field_function
    )
    _sanitize_expression = expression_builder._sanitize_expression
    _find_best_field_match = expression_builder._find_best_field_match
    _validate_dataset_fields = expression_builder._validate_dataset_fields
    _resolve_named_field = expression_builder._resolve_named_field

    # ── Generation Modes (attached from _modes) ────────────────────

    _generate_hypothesis_driven = _generate_hypothesis_driven
    _generate_experience_feedback = _generate_experience_feedback
    _generate_random_exploration = _generate_random_exploration
    _generate_bare_fallback = _generate_bare_fallback
    _normalize_generated_expression = _normalize_generated_expression

    # ── Guidance (attached from _guidance) ─────────────────────────

    set_experience_guidance = set_experience_guidance
    set_observability_guidance = set_observability_guidance
    set_knowledge_constraints = set_knowledge_constraints

    # ── Constraints & Helpers (attached from _constraints) ─────────

    _expression_forbidden = _expression_forbidden
    _expression_satisfies_strict_preferred_constraints = (
        _expression_satisfies_strict_preferred_constraints
    )
    _prioritize_knowledge_fields = _prioritize_knowledge_fields
    _extract_fields = _extract_fields
    _extract_operators = _extract_operators
    _is_observability_avoided = _is_observability_avoided
    _mark_observability_candidate = _mark_observability_candidate


__all__ = ["HypothesisDrivenGenerator"]

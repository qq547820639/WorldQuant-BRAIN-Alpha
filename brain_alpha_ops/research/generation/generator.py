"""HypothesisDrivenGenerator — main hypothesis-driven alpha generation engine."""

from __future__ import annotations

import json
import logging
import random
from typing import Any, TYPE_CHECKING

from brain_alpha_ops.models import Candidate, new_id
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
    expression_similarity,
    profile_expression,
)
from brain_alpha_ops.research.fallback_generation import (
    DEFAULT_WINDOWS,
    build_bare_fallback_spec,
    is_generated_duplicate,
    is_high_turnover_generation_risk,
    normalize_operator_aliases,
)
from brain_alpha_ops.research.field_quality import generation_field_ids
from brain_alpha_ops.research.generator_metadata import (
    expression_windows_within_constraints,
)
from brain_alpha_ops.research.hypothesis_expression_support import (
    HypothesisExpressionSupport,
)
from brain_alpha_ops.research.hypothesis_generator_helpers import (
    safe_float as _safe_float,
)
from brain_alpha_ops.research.hypothesis_library import (
    GenerationMeta,
)

from . import expression_builder
from .context_adapter import ContextAdapter
from .field_selector import FieldSelector
from .mode_router import GenerationModeRouter
from .selectors import ExpressionFamilySelector, HypothesisSelector

if TYPE_CHECKING:
    from brain_alpha_ops.data import FieldDatasetMapper, OfficialDataLoader
    from brain_alpha_ops.research.dataset_selector import DatasetSelector
    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine

logger = logging.getLogger(__name__)

_FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD = 0.90


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
            except Exception:
                logger.warning(
                    "generation field eligibility metadata unavailable for dataset_id=%s",
                    dataset_id,
                    exc_info=True,
                )

    def set_experience_guidance(self, patterns: dict[str, Any]) -> None:
        """Apply winning alpha patterns to bias future generation."""
        if not patterns or patterns.get("sample_size", 0) < 3:
            return
        self._experience_patterns = patterns
        self._experience_operators = patterns.get("top_operators", [])
        self._experience_windows = [
            int(w) for w in patterns.get("preferred_windows", []) if w
        ]
        field_combos = patterns.get("field_combinations", [])
        seen: set[str] = set()
        for combo in field_combos:
            for f in combo.get("fields", []):
                seen.add(str(f).lower())
        self._experience_fields = list(seen)

    def set_observability_guidance(self, guidance: dict) -> None:
        """Apply research-health diagnostics to diversify future generation."""
        guidance = dict(guidance or {})
        flags = {
            str(flag) for flag in guidance.get("health_flags") or []
        }
        duplicate_ratio = _safe_float(guidance.get("duplicate_ratio"))
        avoid_keys: set[str] = set()
        for row in (
            guidance.get("avoid_expressions")
            or guidance.get("top_duplicates")
            or []
        ):
            if isinstance(row, dict):
                for key in (
                    "expression_canonical",
                    "expression_fingerprint",
                    "expression",
                ):
                    value = str(row.get(key) or "").strip()
                    if value:
                        avoid_keys.add(value)
                expression = str(
                    row.get("expression")
                    or row.get("expression_canonical")
                    or ""
                ).strip()
            else:
                expression = str(row or "").strip()
            if expression:
                avoid_keys.add(expression_key(expression))
                avoid_keys.add(expression_fingerprint(expression))
        self._observability_avoid_keys = {
            item for item in avoid_keys if item
        }
        self._observability_diversity_boost = bool(
            self._observability_avoid_keys
            or duplicate_ratio >= 0.25
            or {
                "duplicate_expression_history",
                "high_duplicate_expression_ratio",
            }
            & flags
        )
        self._observability_guidance = {
            "risk_level": guidance.get("risk_level", "unknown"),
            "health_flags": sorted(flags),
            "duplicate_ratio": duplicate_ratio,
            "avoid_expression_count": len(self._observability_avoid_keys),
            "diversity_boost": self._observability_diversity_boost,
        }

    def set_knowledge_constraints(
        self, constraints: dict[str, Any] | None
    ) -> None:
        """Bias generation using structured knowledge-base constraints."""
        constraints = dict(constraints or {})
        requested_fields = [
            str(item).lower()
            for item in constraints.get("preferred_fields") or []
            if str(item)
        ]
        preferred_fields = self._official_preferred_fields(requested_fields)
        preferred_operators = [
            str(item).lower()
            for item in constraints.get("preferred_operators") or []
            if str(item)
        ]
        forbidden_patterns = [
            str(item).strip()
            for item in constraints.get("forbidden_patterns") or []
            if str(item)
        ]
        strict_preferred_fields = bool(
            constraints.get("strict_preferred_fields")
        )
        strict_preferred_operators = bool(
            constraints.get("strict_preferred_operators")
        )
        self._knowledge_constraints = {
            "preferred_fields": preferred_fields,
            "preferred_operators": preferred_operators,
            "forbidden_patterns": forbidden_patterns,
            "strict_preferred_fields": strict_preferred_fields,
            "strict_preferred_operators": strict_preferred_operators,
        }
        if preferred_fields:
            self._fields.update(preferred_fields)
        if preferred_operators:
            self._operators.update(preferred_operators)

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
            except Exception:
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
                except Exception:
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

    # ── Generation Modes ────────────────────────────────────────────

    def _generate_hypothesis_driven(
        self, dataset_id: str
    ) -> Candidate | None:
        """Execute the 6-step hypothesis-driven generation pipeline.

        Steps:
          1. Mode routing (already done by generate())
          2. Hypothesis selection
          3. Expression family selection + window selection
          4. Field selection
          5. Context adaptation
          6. Alpha assembly
        """
        if not self._library or self._library.count == 0:
            if not self._warned_empty_hypothesis_library:
                logger.warning(
                    "_generate_hypothesis_driven: no hypotheses loaded; "
                    "falling back to random exploration for this run."
                )
                self._warned_empty_hypothesis_library = True
            return self._generate_random_exploration(dataset_id)

        # Step 2: Hypothesis selection
        if self._hyp_selector is None:
            return self._generate_random_exploration(dataset_id)
        hypothesis = self._hyp_selector.select()
        if hypothesis is None:
            return self._generate_random_exploration(dataset_id)

        # Step 3: Expression family + window selection
        expr_family = self._expr_selector.select(hypothesis)
        if expr_family is None:
            return self._generate_random_exploration(dataset_id)

        window_weights = hypothesis.experience_weights.window_weights
        window = self._expr_selector.select_window(
            expr_family, window_weights
        )

        # Step 4: Field selection
        if self._field_selector is None:
            return self._generate_random_exploration(dataset_id)
        selected_fields = self._field_selector.select_fields(
            hypothesis, dataset_id, count=2
        )
        selected_fields = self._prioritize_knowledge_fields(selected_fields)
        if not selected_fields:
            return self._generate_random_exploration(dataset_id)

        # Step 5: Context adaptation
        context = self._adapter.adapt(hypothesis)

        # Step 6: Alpha assembly
        expression = self._build_expression(
            expr_family,
            selected_fields,
            window,
            field_categories=hypothesis.field_categories,
        )
        if not expression_windows_within_constraints(expression):
            return self._generate_random_exploration(dataset_id)

        # Determine which field category was used
        field_category_used = ""
        for fc in hypothesis.field_categories:
            if fc.examples and any(
                ex in selected_fields for ex in fc.examples
            ):
                field_category_used = fc.category
                break
        if not field_category_used:
            field_category_used = (
                hypothesis.field_categories[0].category
                if hypothesis.field_categories
                else ""
            )

        meta = GenerationMeta(
            mode="hypothesis_driven",
            hypothesis_id=hypothesis.id,
            hypothesis_name=hypothesis.name,
            expression_family_id=expr_family.id,
            field_category=field_category_used,
            selected_fields=selected_fields,
            region=context["region"],
            universe=context["universe"],
            delay=context["delay"],
        )
        candidate = Candidate(
            alpha_id=new_id("alpha"),
            expression=expression,
            family=hypothesis.category,
            hypothesis=f"Hypothesis-driven: {hypothesis.name} — {expr_family.description}",
            data_fields=self._extract_fields(expression)
            or sorted(selected_fields),
            operators=self._extract_operators(expression),
            source_tags=["hypothesis_driven"],
            dataset_id=dataset_id or self._dataset_id,
            template_source=meta.to_json(),
        )
        if self._expression_forbidden(candidate.expression):
            return self._generate_random_exploration(dataset_id)
        return candidate

    def _generate_experience_feedback(
        self, dataset_id: str
    ) -> Candidate | None:
        """Generate a candidate biased by experience-winning patterns.

        Uses DynamicThemeEngine with experience operator/window preferences.
        """
        if self._theme_engine is None:
            return self._generate_random_exploration(dataset_id)

        ds = dataset_id or self._dataset_id
        try:
            # Apply experience bias to theme engine
            if self._experience_windows and hasattr(
                self._theme_engine, "_windows"
            ):
                self._theme_engine._windows = list(  # type: ignore[union-attr]
                    self._experience_windows
                    if self._experience_windows
                    else DEFAULT_WINDOWS
                )

            themes = self._theme_engine.generate(ds, n=1)  # type: ignore[union-attr]
            if not themes:
                return self._generate_random_exploration(dataset_id)

            tmpl = themes[0]
            mutated = self._theme_engine.mutate_expression(  # type: ignore[union-attr]
                tmpl.expression, ds, seed=random.randint(0, 1000)
            )
            mutated = self._normalize_generated_expression(mutated)
            if not expression_windows_within_constraints(mutated):
                return self._generate_random_exploration(dataset_id)

            meta = GenerationMeta(
                mode="experience_feedback",
                hypothesis_id=tmpl.category,
                hypothesis_name=f"Experience-biased {tmpl.category}",
                expression_family_id="experience_pattern",
                field_category="experience_feedback",
                selected_fields=tmpl.field_slots
                if tmpl.field_slots
                else [],
                region="USA",
                universe="TOP3000",
                delay=1,
            )

            candidate = Candidate(
                alpha_id=new_id("alpha"),
                expression=mutated,
                family=tmpl.category,
                hypothesis=f"Experience-feedback: {tmpl.name or tmpl.category} alpha from {ds}",
                data_fields=self._extract_fields(mutated),
                operators=self._extract_operators(mutated),
                source_tags=["experience_feedback"],
                dataset_id=ds,
                template_source=meta.to_json(),
            )
            if self._expression_forbidden(candidate.expression):
                return self._generate_random_exploration(dataset_id)
            return candidate
        except Exception as exc:
            logger.warning(
                "_generate_experience_feedback failed: %s",
                redact_error_message(exc, max_length=160),
            )
            return self._generate_random_exploration(dataset_id)

    def _generate_random_exploration(
        self, dataset_id: str
    ) -> Candidate | None:
        """Fallback to DynamicThemeEngine for pure random exploration."""
        if self._theme_engine is None:
            return self._generate_bare_fallback(dataset_id)

        ds = dataset_id or self._dataset_id
        try:
            themes = self._theme_engine.generate(ds, n=1)  # type: ignore[union-attr]
            if not themes:
                return self._generate_bare_fallback(dataset_id)

            tmpl = themes[0]
            mutated = self._theme_engine.mutate_expression(  # type: ignore[union-attr]
                tmpl.expression, ds, seed=random.randint(0, 10000)
            )
            mutated = self._normalize_generated_expression(mutated)
            if not expression_windows_within_constraints(mutated):
                return self._generate_bare_fallback(dataset_id)

            meta = GenerationMeta(
                mode="random_exploration",
                hypothesis_id="random",
                hypothesis_name="Random Exploration",
                expression_family_id=tmpl.category,
                field_category="random_exploration",
                selected_fields=tmpl.field_slots
                if tmpl.field_slots
                else [],
                region="USA",
                universe="TOP3000",
                delay=1,
            )

            candidate = Candidate(
                alpha_id=new_id("alpha"),
                expression=mutated,
                family=tmpl.category,
                hypothesis=f"Random exploration {tmpl.category} alpha from {ds}",
                data_fields=self._extract_fields(mutated),
                operators=self._extract_operators(mutated),
                source_tags=["random_exploration"],
                dataset_id=ds,
                template_source=meta.to_json(),
            )
            if self._expression_forbidden(candidate.expression):
                return self._generate_bare_fallback(dataset_id)
            return candidate
        except Exception as exc:
            logger.warning(
                "_generate_random_exploration: ThemeEngine failed: %s",
                redact_error_message(exc, max_length=160),
            )
            return self._generate_bare_fallback(dataset_id)

    def _generate_bare_fallback(
        self, dataset_id: str
    ) -> Candidate | None:
        """Absolute last-resort fallback when ThemeEngine is unavailable."""
        ds = dataset_id or self._dataset_id or "default"
        fields = sorted(self._fields)
        fields = self._prioritize_knowledge_fields(fields)
        if not fields:
            logger.warning(
                "HypothesisDrivenGenerator: bare fallback blocked because official field context is empty "
                "for dataset_id=%s",
                ds,
            )
            return None
        operators = {
            str(item).lower()
            for item in self._operators
            if str(item)
        }
        if self._knowledge_constraints.get("strict_preferred_operators"):
            operators &= {
                str(item).lower()
                for item in self._knowledge_constraints.get(
                    "preferred_operators"
                )
                or []
                if str(item)
            }
        windows = self._experience_windows or DEFAULT_WINDOWS
        attempt_limit = max(1, len(fields) * len(windows))
        for _ in range(attempt_limit):
            spec = build_bare_fallback_spec(
                fields=fields,
                operators=operators,
                windows=windows,
                cursor=self._fallback_cursor,
            )
            self._fallback_cursor = spec.next_cursor
            expression = normalize_operator_aliases(spec.expression)
            if not expression_windows_within_constraints(expression):
                continue
            if self._expression_forbidden(expression):
                continue

            meta = GenerationMeta(
                mode="random_exploration",
                hypothesis_id="fallback",
                hypothesis_name="Bare Fallback",
                expression_family_id="fallback",
                field_category="fallback",
                selected_fields=spec.data_fields,
                region="USA",
                universe="TOP3000",
                delay=1,
            )

            return Candidate(
                alpha_id=new_id("alpha"),
                expression=expression,
                family=spec.family,
                hypothesis=f"Bare fallback alpha from {ds}",
                data_fields=spec.data_fields,
                operators=self._extract_operators(expression),
                source_tags=["random_exploration", "fallback"],
                dataset_id=ds,
                template_source=meta.to_json(),
            )
        return None

    def _normalize_generated_expression(self, expression: str) -> str:
        fallback_fields = self._prioritize_knowledge_fields(
            sorted(self._fields)
        )
        normalized = normalize_operator_aliases(expression)
        if fallback_fields:
            normalized = self._sanitize_expression(
                normalized, fallback_fields
            )
            normalized = self._validate_dataset_fields(
                normalized, fallback_fields
            )
            normalized = self._normalize_wq_expression_shape(normalized)
        return normalize_operator_aliases(normalized)

    def _expression_forbidden(self, expression: str) -> bool:
        expression_text = str(expression or "").strip()
        if not expression_text:
            return False
        expression_lower = expression_text.lower()
        if is_high_turnover_generation_risk(expression_text):
            return True
        try:
            current_key = expression_key(expression_text)
            current_fingerprint = expression_fingerprint(expression_text)
        except Exception:
            current_key = ""
            current_fingerprint = ""
        for pattern in (
            self._knowledge_constraints.get("forbidden_patterns") or []
        ):
            pattern_text = str(pattern or "").strip()
            if not pattern_text:
                continue
            needle = pattern_text.lower()
            if needle and needle in expression_lower:
                return True
            if pattern_text in {
                expression_text,
                current_key,
                current_fingerprint,
            }:
                return True
            try:
                pattern_key = expression_key(pattern_text)
                pattern_fingerprint = expression_fingerprint(pattern_text)
            except Exception:
                pattern_key = ""
                pattern_fingerprint = ""
            if current_key and pattern_key and current_key == pattern_key:
                return True
            if (
                current_fingerprint
                and pattern_fingerprint
                and current_fingerprint == pattern_fingerprint
            ):
                return True
            try:
                if (
                    expression_similarity(expression_text, pattern_text)
                    >= _FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD
                ):
                    return True
            except Exception:
                logger.debug(
                    "failed to compare forbidden expression pattern",
                    exc_info=True,
                )
        return False

    def _expression_satisfies_strict_preferred_constraints(
        self, expression: str
    ) -> bool:
        if not (
            self._knowledge_constraints.get("strict_preferred_fields")
            or self._knowledge_constraints.get(
                "strict_preferred_operators"
            )
        ):
            return True
        profile = profile_expression(expression)
        if not profile.parsed:
            return False
        if self._knowledge_constraints.get("strict_preferred_fields"):
            allowed_fields = {
                str(field).lower()
                for field in self._knowledge_constraints.get(
                    "preferred_fields"
                )
                or []
                if str(field)
            }
            if not allowed_fields:
                return False
            expression_fields = {
                str(field).lower()
                for field in profile.fields
                if str(field)
            }
            expression_fields -= {
                "market",
                "sector",
                "industry",
                "subindustry",
            }
            if not expression_fields or not expression_fields <= allowed_fields:
                return False
        if self._knowledge_constraints.get("strict_preferred_operators"):
            allowed_operators = {
                str(operator).lower()
                for operator in self._knowledge_constraints.get(
                    "preferred_operators"
                )
                or []
                if str(operator)
            }
            if not allowed_operators:
                return False
            expression_operators = {
                str(operator).lower()
                for operator in profile.operators
                if str(operator)
            }
            if expression_operators - allowed_operators:
                return False
        return True

    def _prioritize_knowledge_fields(self, fields: list[str]) -> list[str]:
        preferred = set(
            self._knowledge_constraints.get("preferred_fields") or []
        )
        if not preferred:
            return list(fields)
        front = [field for field in fields if field.lower() in preferred]
        if self._knowledge_constraints.get("strict_preferred_fields"):
            return front
        rest = [
            field for field in fields if field.lower() not in preferred
        ]
        return front + rest

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

    # ── Helpers ─────────────────────────────────────────────────────

    def _extract_fields(self, expression: str) -> list[str]:
        return self._expression_support().extract_fields(expression)

    def _extract_operators(self, expression: str) -> list[str]:
        return self._expression_support().extract_operators(expression)

    def _is_observability_avoided(self, expression: str) -> bool:
        if not self._observability_avoid_keys:
            return False
        markers = {
            str(expression or "").strip(),
            expression_key(expression),
            expression_fingerprint(expression),
        }
        return bool(markers & self._observability_avoid_keys)

    def _mark_observability_candidate(self, candidate: Candidate) -> None:
        tags = list(candidate.source_tags or [])
        if "observability_diversified" not in tags:
            tags.append("observability_diversified")
        candidate.source_tags = tags
        if not candidate.template_source:
            candidate.template_source = "observability"
            return
        try:
            meta = json.loads(candidate.template_source)
        except (TypeError, json.JSONDecodeError):
            if ":observability" not in candidate.template_source:
                candidate.template_source = (
                    f"{candidate.template_source}:observability"
                )
            return
        if isinstance(meta, dict):
            meta["observability_diversified"] = True
            candidate.template_source = json.dumps(
                meta, ensure_ascii=False
            )


__all__ = ["HypothesisDrivenGenerator"]

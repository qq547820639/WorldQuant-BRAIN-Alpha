"""Generation mode methods for ``HypothesisDrivenGenerator``.

These module-level functions implement the three generation modes
(hypothesis-driven, experience-feedback, random-exploration) plus the
bare-fallback path.  They are attached as methods on ``HypothesisDrivenGenerator``
and receive ``self`` as the first argument — matching the existing
``expression_builder`` pattern.
"""

from __future__ import annotations

import logging
import random

from brain_alpha_ops.models import Candidate, new_id
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.fallback_generation import (
    DEFAULT_WINDOWS,
    build_bare_fallback_spec,
    normalize_operator_aliases,
)
from brain_alpha_ops.research.generator_metadata import (
    expression_windows_within_constraints,
)
from brain_alpha_ops.research.hypothesis_library import (
    GenerationMeta,
)

logger = logging.getLogger(__name__)


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

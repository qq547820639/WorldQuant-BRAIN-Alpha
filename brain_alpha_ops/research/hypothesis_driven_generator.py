"""Hypothesis-Driven Alpha Generator — structured generation from market hypotheses.

Implements a 3-mode generation strategy:
  - hypothesis_driven (70% default): 6-step pipeline from hypothesis to Candidate
  - experience_feedback (20% default): biased ThemeEngine using winning patterns
  - random_exploration (10% default): pure fallback to DynamicThemeEngine

Usage::

    from brain_alpha_ops.research.hypothesis_library import HypothesisLibrary
    from brain_alpha_ops.research.hypothesis_driven_generator import HypothesisDrivenGenerator

    library = HypothesisLibrary("brain_alpha_ops/research/hypotheses").load_all()
    gen = HypothesisDrivenGenerator(loader, mapper, theme_engine, selector, library)
    candidates = gen.generate(20, dataset_id="analyst4")
"""

from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from brain_alpha_ops.models import Candidate, new_id
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
    expression_similarity,
)
from brain_alpha_ops.research.hypothesis_expression_support import HypothesisExpressionSupport
from brain_alpha_ops.research.field_quality import generation_field_ids
from brain_alpha_ops.research.fallback_generation import (
    DEFAULT_WINDOWS,
    build_bare_fallback_spec,
    is_high_turnover_generation_risk,
    is_generated_duplicate,
    normalize_operator_aliases,
)
from brain_alpha_ops.research.hypothesis_library import (
    Hypothesis,
    ExpressionFamily,
    FieldCategoryDef,
    GenerationMeta,
    HypothesisLibrary,
)

if TYPE_CHECKING:
    from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
    from brain_alpha_ops.research.theme_engine import DynamicThemeEngine
    from brain_alpha_ops.research.dataset_selector import DatasetSelector

logger = logging.getLogger(__name__)

_FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD = 0.90


# ═══════════════════════════════════════════════════════════════════════
# Component 1: GenerationModeRouter
# ═══════════════════════════════════════════════════════════════════════

class GenerationModeRouter:
    """Routes generation requests to one of three modes based on configured ratios.

    Uses weighted random sampling. Internal counters track actual proportions.
    The ratio converges to the target over many calls (law of large numbers).

    Usage::

        router = GenerationModeRouter("70/20/10")
        mode = router.route()  # → "hypothesis_driven" (70% of the time)
    """

    VALID_MODES: tuple[str, ...] = ("hypothesis_driven", "experience_feedback", "random_exploration")

    def __init__(self, ratio_str: str = "70/20/10") -> None:
        """Parse ratio string like "70/20/10" into per-mode weights."""
        self._hypothesis_ratio: float = 0.70
        self._experience_ratio: float = 0.20
        self._random_ratio: float = 0.10

        parts = ratio_str.strip().split("/")
        if len(parts) == 3:
            try:
                h, e, r = [float(p) for p in parts]
                total = h + e + r
                if total > 0:
                    self._hypothesis_ratio = h / total
                    self._experience_ratio = e / total
                    self._random_ratio = r / total
            except (ValueError, ZeroDivisionError):
                logger.warning("GenerationModeRouter: invalid ratio '%s', using default 70/20/10.", ratio_str)

        # Counters for monitoring actual proportions
        self._hypothesis_count: int = 0
        self._experience_count: int = 0
        self._random_count: int = 0

    def route(self) -> str:
        """Return the mode for the next generation call."""
        population = list(self.VALID_MODES)
        weights = [self._hypothesis_ratio, self._experience_ratio, self._random_ratio]
        chosen: str = random.choices(population, weights=weights, k=1)[0]

        if chosen == "hypothesis_driven":
            self._hypothesis_count += 1
        elif chosen == "experience_feedback":
            self._experience_count += 1
        else:
            self._random_count += 1

        return chosen

    def reset(self) -> None:
        """Reset internal counters."""
        self._hypothesis_count = 0
        self._experience_count = 0
        self._random_count = 0

    @property
    def actual_ratios(self) -> dict[str, float]:
        """Return observed ratios from counters."""
        total = self._hypothesis_count + self._experience_count + self._random_count
        if total == 0:
            return {"hypothesis_driven": 0.0, "experience_feedback": 0.0, "random_exploration": 0.0}
        return {
            "hypothesis_driven": self._hypothesis_count / total,
            "experience_feedback": self._experience_count / total,
            "random_exploration": self._random_count / total,
        }


# ═══════════════════════════════════════════════════════════════════════
# Component 2: HypothesisSelector
# ═══════════════════════════════════════════════════════════════════════

class HypothesisSelector:
    """Selects a hypothesis weighted by experience weights.

    Higher experience_weights.overall → higher selection probability.
    Maintains a recently-used exclusion set to avoid repetition.
    """

    DEFAULT_RECENCY_SIZE: int = 3

    def __init__(self, library: "HypothesisLibrary") -> None:
        self._library = library
        self._recently_used: list[str] = []
        self._max_recency: int = self.DEFAULT_RECENCY_SIZE

    def select(self) -> "Hypothesis | None":
        """Select a hypothesis by weighted random choice.

        Returns None if no hypotheses are available.
        """
        all_h = self._library.get_all()
        if not all_h:
            return None

        # Build candidate pool, excluding recently used if possible
        excluded_ids: set[str] = set(self._recently_used[-self._max_recency:])
        pool = [h for h in all_h if h.id not in excluded_ids]
        if not pool:
            # All hypotheses recently used — fall back to full pool
            pool = all_h
            excluded_ids.clear()

        # Weighted random selection by experience_weights.overall
        weights = [max(0.01, h.experience_weights.overall) for h in pool]
        chosen: Hypothesis = random.choices(pool, weights=weights, k=1)[0]

        # Update recency tracker
        self._recently_used.append(chosen.id)
        if len(self._recently_used) > self._max_recency * 3:
            self._recently_used = self._recently_used[-self._max_recency:]

        return chosen

    def exclude_recently_used(self, max_recency: int) -> None:
        """Set the number of recently-used hypotheses to exclude."""
        self._max_recency = max(1, max_recency)


# ═══════════════════════════════════════════════════════════════════════
# Component 3: ExpressionFamilySelector
# ═══════════════════════════════════════════════════════════════════════

class ExpressionFamilySelector:
    """Selects an expression family and window from a hypothesis.

    Weighted by expression_family_weights and window_weights respectively.
    """

    def __init__(self) -> None:
        pass

    def select(self, hypothesis: "Hypothesis") -> "ExpressionFamily | None":
        """Select an expression family weighted by its experience weight."""
        families = hypothesis.expression_families
        if not families:
            return None
        weights = [max(0.01, ef.weight) for ef in families]
        chosen: ExpressionFamily = random.choices(families, weights=weights, k=1)[0]
        return chosen

    def select_window(self, expr_family: "ExpressionFamily",
                      window_weights: dict[str, float] | None = None) -> int:
        """Select a window size from the expression family's window list.

        Window selection is weighted by *window_weights* (from experience_weights)
        if provided, otherwise uniform random.
        """
        windows = expr_family.get_all_windows()
        if not windows:
            return 12  # sensible default

        if window_weights:
            weights = [max(0.01, window_weights.get(str(w), 1.0)) for w in windows]
        else:
            weights = None

        if weights is not None and sum(weights) > 0:
            chosen: int = random.choices(windows, weights=weights, k=1)[0]
        else:
            chosen = random.choice(windows)
        return chosen


# ═══════════════════════════════════════════════════════════════════════
# Component 4: FieldSelector
# ═══════════════════════════════════════════════════════════════════════

class FieldSelector:
    """Selects concrete field names from a hypothesis's field category definitions.

    Delegates category-to-field resolution to DatasetSelector.get_fields_by_category().
    """

    def __init__(self, selector: "DatasetSelector") -> None:
        self._selector = selector
        self._field_cache: dict[str, list[str]] = {}
        self._dataset_field_cache: dict[str, set[str]] = {}

    def select_fields(
        self,
        hypothesis: "Hypothesis",
        dataset_id: str = "",
        count: int = 2,
    ) -> list[str]:
        """Select *count* concrete field names for *hypothesis*.

        Strategy:
          1. Sort field_categories by priority (P0 first), then by weight
          2. Pick a category using weighted random selection
          3. Resolve category to concrete fields via DatasetSelector
          4. Randomly pick *count* fields from the resolved list
        """
        if not hypothesis.field_categories:
            return []

        dataset_fields = self._dataset_field_set(dataset_id)

        # Sort: P0 first, then by weight descending
        sorted_cats = sorted(
            hypothesis.field_categories,
            key=lambda fc: (0 if fc.priority == "P0" else 1, -fc.weight),
        )

        # Try weighted categories, but never fall back to example field names
        # unless they are present in the active official dataset.
        remaining = list(sorted_cats)
        while remaining:
            weights = [max(0.01, fc.weight) for fc in remaining]
            chosen_cat: FieldCategoryDef = random.choices(remaining, weights=weights, k=1)[0]
            remaining.remove(chosen_cat)

            fields = self._resolve_category(chosen_cat.category, dataset_id, examples=chosen_cat.examples)

            if fields:
                k = min(count, len(fields))
                return random.sample(fields, k)

        return []

    def _resolve_category(
        self,
        category_name: str,
        dataset_id: str = "",
        *,
        examples: list[str] | None = None,
    ) -> list[str]:
        """Resolve a semantic field category to concrete field name list."""
        examples_key = ",".join(str(item).lower() for item in (examples or []))
        cache_key = f"{dataset_id}::{category_name}::{examples_key}"
        if cache_key in self._field_cache:
            return self._field_cache[cache_key]

        # Try get_fields_by_category if dataset_selector supports it
        fields: list[str] = []
        if hasattr(self._selector, 'get_fields_by_category'):
            try:
                fields = self._selector.get_fields_by_category(category_name, dataset_id)  # type: ignore[attr-defined]
            except TypeError:
                fields = self._selector.get_fields_by_category(category_name)  # type: ignore[attr-defined]

        dataset_fields = self._dataset_field_set(dataset_id)
        if dataset_fields:
            fields = [field for field in fields if field.lower() in dataset_fields]
        if not fields and dataset_fields:
            fields = self._resolve_semantic_dataset_fields(
                category_name,
                examples=examples or [],
                dataset_fields=dataset_fields,
            )

        self._field_cache[cache_key] = fields
        return fields

    def _dataset_field_set(self, dataset_id: str) -> set[str]:
        if not dataset_id:
            return set()
        if dataset_id in self._dataset_field_cache:
            return self._dataset_field_cache[dataset_id]
        loader = getattr(self._selector, "_loader", None)
        if loader is None:
            return set()
        try:
            fields = set(generation_field_ids(loader.get_fields(dataset_id)))
            if not fields:
                fields = {field.id.lower() for field in loader.get_fields(dataset_id)}
            self._dataset_field_cache[dataset_id] = fields
            return fields
        except Exception:
            logger.warning(
                "dataset field metadata unavailable for dataset_id=%s",
                dataset_id,
                exc_info=True,
            )
            return set()

    def _resolve_semantic_dataset_fields(
        self,
        category_name: str,
        *,
        examples: list[str],
        dataset_fields: set[str],
        limit: int = 60,
    ) -> list[str]:
        """Map hypothesis semantic categories to real official dataset fields.

        Official context often exposes only coarse categories such as
        ``analyst`` while the hypothesis library uses finer concepts such as
        ``earnings_estimate_revision``.  This fallback never invents names; it
        ranks fields already present in the active dataset by semantic tokens
        from the hypothesis category and its examples.
        """
        weighted_tokens = _semantic_field_tokens(category_name, examples)
        if not weighted_tokens:
            return []
        scored: list[tuple[float, str]] = []
        for field in sorted(dataset_fields):
            field_key = field.lower()
            score = 0.0
            for token, weight in weighted_tokens.items():
                if token in field_key:
                    score += weight
            if score >= 5.0:
                scored.append((score, field))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [field for _score, field in scored[:limit]]


_SEMANTIC_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "accruals": ("accrual",),
    "analyst": ("anl4",),
    "beta": ("beta",),
    "cash": ("cash", "cfo", "cff", "cfi"),
    "consensus": ("consensus", "mean", "median"),
    "coverage": ("numest", "number", "num"),
    "dispersion": ("dispersion", "std", "stddev", "high", "low"),
    "dividend": ("div", "dividend"),
    "earnings": ("eps", "earnings", "income", "netincome", "net_income"),
    "estimate": ("estimate", "est", "mean", "median"),
    "float": ("float", "shares"),
    "growth": ("growth", "sales", "revenue"),
    "margin": ("margin", "gross", "operating"),
    "price": ("price", "value"),
    "profitability": ("profit", "income", "roe", "roa"),
    "rating": ("rating", "rec"),
    "recommendation": ("rec", "rating"),
    "revenue": ("sales", "revenue"),
    "revision": ("revision", "revisions", "previosestimate", "previous", "preest", "chg", "change"),
    "sales": ("sales", "revenue"),
    "surprise": ("surprise", "actual"),
    "target": ("target", "tp"),
}

_SEMANTIC_STOP_TOKENS = {
    "and",
    "change",
    "count",
    "history",
    "historical",
    "long",
    "ratio",
    "short",
    "term",
    "the",
    "to",
}


def _semantic_field_tokens(category_name: str, examples: list[str]) -> dict[str, float]:
    tokens: dict[str, float] = {}
    for token in _split_semantic_tokens(category_name):
        _add_semantic_token(tokens, token, 2.0)
        for alias in _SEMANTIC_TOKEN_ALIASES.get(token, ()):
            _add_semantic_token(tokens, alias, 2.5)
    for example in examples:
        for token in _split_semantic_tokens(example):
            _add_semantic_token(tokens, token, 3.0)
            for alias in _SEMANTIC_TOKEN_ALIASES.get(token, ()):
                _add_semantic_token(tokens, alias, 3.0)
    return tokens


def _split_semantic_tokens(value: str) -> list[str]:
    raw_tokens = re.split(r"[^a-zA-Z0-9]+", str(value or "").lower())
    return [
        token
        for token in raw_tokens
        if len(token) >= 3 and token not in _SEMANTIC_STOP_TOKENS
    ]


def _add_semantic_token(tokens: dict[str, float], token: str, weight: float) -> None:
    token = str(token or "").lower().strip()
    if len(token) < 3 or token in _SEMANTIC_STOP_TOKENS:
        return
    tokens[token] = max(tokens.get(token, 0.0), weight)


# ═══════════════════════════════════════════════════════════════════════
# Component 5: ContextAdapter
# ═══════════════════════════════════════════════════════════════════════

class ContextAdapter:
    """Adapts a hypothesis to available region/universe/delay context.

    Cross-filters hypothesis.adaptation preferences against what's actually
    available, producing a concrete context dict for Candidate construction.
    """

    # Default available context — used when no external info is provided
    DEFAULT_REGIONS: list[str] = ["USA", "EUROPE", "DEV", "ASIA", "DEV_EX_US", "FRONTIER"]
    DEFAULT_UNIVERSES: list[str] = ["TOP3000", "TOP1000", "MID_LARGE_CAP", "SMID_CAP",
                                     "SMALL_CAP", "MICRO_CAP", "ALL_CAP"]
    DEFAULT_DELAYS: list[int] = [1, 2, 3, 4, 5]

    def __init__(self) -> None:
        self._available_regions: list[str] = list(self.DEFAULT_REGIONS)
        self._available_universes: list[str] = list(self.DEFAULT_UNIVERSES)
        self._available_delays: list[int] = list(self.DEFAULT_DELAYS)

    def set_available_context(
        self,
        regions: list[str] | None = None,
        universes: list[str] | None = None,
        delays: list[int] | None = None,
    ) -> None:
        """Override the default available context."""
        if regions is not None:
            self._available_regions = list(regions)
        if universes is not None:
            self._available_universes = list(universes)
        if delays is not None:
            self._available_delays = list(delays)

    def adapt(self, hypothesis: "Hypothesis") -> dict[str, Any]:
        """Generate a concrete context dict for *hypothesis*.

        Returns:
            Dict with keys: region, universe, delay.
        """
        adapt = hypothesis.adaptation

        # Region: prefer hypothesis preferences, filter by availability
        preferred_regions = adapt.preferred_regions or self.DEFAULT_REGIONS
        suitable_regions = [r for r in preferred_regions
                           if r in self._available_regions
                           and r not in adapt.unsuitable_regions]
        region = random.choice(suitable_regions) if suitable_regions else (self._available_regions[0] if self._available_regions else self.DEFAULT_REGIONS[0])

        # Universe: prefer hypothesis preferences
        preferred_universes = adapt.preferred_universes or self.DEFAULT_UNIVERSES
        suitable_universes = [u for u in preferred_universes if u in self._available_universes]
        universe = random.choice(suitable_universes) if suitable_universes else (self._available_universes[0] if self._available_universes else self.DEFAULT_UNIVERSES[0])

        # Delay: prefer hypothesis preferences
        preferred_delays = adapt.preferred_delays or self.DEFAULT_DELAYS
        suitable_delays = [d for d in preferred_delays if d in self._available_delays]
        delay = random.choice(suitable_delays) if suitable_delays else 1

        return {"region": region, "universe": universe, "delay": delay}


def _pick_unused(fields: list[str], index: int, used: set[str]) -> str:
    """Pick fields[index] if available and unused; otherwise pick the first unused field.

    BUG-10: prevents the same field being assigned to multiple placeholders
    (e.g. {f1} and {f2} both resolving to the same field), which would produce
    redundant expressions.
    """
    default = fields[index] if index < len(fields) else (fields[0] if fields else "returns")
    if default not in used:
        return default
    for f in fields:
        if f not in used:
            return f
    return default  # all used — duplicate is unavoidable


# ═══════════════════════════════════════════════════════════════════════
# Component 6: HypothesisDrivenGenerator (main)
# ═══════════════════════════════════════════════════════════════════════

def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
        self._hyp_selector = HypothesisSelector(library) if library else None
        self._expr_selector = ExpressionFamilySelector()
        self._field_selector = FieldSelector(selector) if selector else None
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
        }

    # ── Public API (CandidateGenerator-compatible) ──────────────────

    def update_context(self, fields: list[Any], operators: list[Any]) -> None:
        """Update known fields/operators."""
        if fields:
            if isinstance(fields[0], dict):
                self._fields = {str(item.get("name", "")).lower() for item in fields if item.get("name")}
            else:
                self._fields = {str(f).lower() for f in fields}
        if operators:
            if isinstance(operators[0], dict):
                self._operators = {str(item.get("name", "")).lower() for item in operators if item.get("name")}
            else:
                self._operators = {str(o).lower() for o in operators}

    def set_dataset(self, dataset_id: str) -> None:
        """Set the active dataset for generation."""
        self._dataset_id = dataset_id
        if self._mapper:
            mapper_fields = self._mapper.fields_for(dataset_id)
            self._fields = set(mapper_fields)
        if self._loader:
            try:
                eligible_fields = generation_field_ids(self._loader.get_fields(dataset_id))
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
        self._experience_windows = [int(w) for w in patterns.get("preferred_windows", []) if w]
        field_combos = patterns.get("field_combinations", [])
        seen: set[str] = set()
        for combo in field_combos:
            for f in combo.get("fields", []):
                seen.add(str(f).lower())
        self._experience_fields = list(seen)

    def set_observability_guidance(self, guidance: dict) -> None:
        """Apply research-health diagnostics to diversify future generation."""
        guidance = dict(guidance or {})
        flags = {str(flag) for flag in guidance.get("health_flags") or []}
        duplicate_ratio = _safe_float(guidance.get("duplicate_ratio"))
        avoid_keys: set[str] = set()
        for row in guidance.get("avoid_expressions") or guidance.get("top_duplicates") or []:
            if isinstance(row, dict):
                for key in ("expression_canonical", "expression_fingerprint", "expression"):
                    value = str(row.get(key) or "").strip()
                    if value:
                        avoid_keys.add(value)
                expression = str(row.get("expression") or row.get("expression_canonical") or "").strip()
            else:
                expression = str(row or "").strip()
            if expression:
                avoid_keys.add(expression_key(expression))
                avoid_keys.add(expression_fingerprint(expression))
        self._observability_avoid_keys = {item for item in avoid_keys if item}
        self._observability_diversity_boost = bool(
            self._observability_avoid_keys
            or duplicate_ratio >= 0.25
            or {"duplicate_expression_history", "high_duplicate_expression_ratio"} & flags
        )
        self._observability_guidance = {
            "risk_level": guidance.get("risk_level", "unknown"),
            "health_flags": sorted(flags),
            "duplicate_ratio": duplicate_ratio,
            "avoid_expression_count": len(self._observability_avoid_keys),
            "diversity_boost": self._observability_diversity_boost,
        }

    def set_knowledge_constraints(self, constraints: dict[str, Any] | None) -> None:
        """Bias generation using structured knowledge-base constraints."""
        constraints = dict(constraints or {})
        preferred_fields = [str(item).lower() for item in constraints.get("preferred_fields") or [] if str(item)]
        preferred_operators = [str(item).lower() for item in constraints.get("preferred_operators") or [] if str(item)]
        forbidden_patterns = [str(item).strip() for item in constraints.get("forbidden_patterns") or [] if str(item)]
        self._knowledge_constraints = {
            "preferred_fields": preferred_fields,
            "preferred_operators": preferred_operators,
            "forbidden_patterns": forbidden_patterns,
        }
        if preferred_fields:
            self._fields.update(preferred_fields)
        if preferred_operators:
            self._operators.update(preferred_operators)

    def _expression_support(self) -> HypothesisExpressionSupport:
        return HypothesisExpressionSupport(
            fields=self._fields,
            operators=self._operators,
            loader=self._loader,
            dataset_id=self._dataset_id,
            logger=logger,
        )

    def generate(self, count: int, dataset_id: str = "") -> list[Candidate]:
        """Generate *count* alpha candidates for *dataset_id*."""
        ds = dataset_id or self._dataset_id
        candidates: list[Candidate] = []
        attempts = 0
        attempt_limit = max(count, count * (8 if self._observability_diversity_boost else 5))
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
                    if is_high_turnover_generation_risk(candidate.expression):
                        candidate.lifecycle_status = "generation_risk_skipped"
                        continue
                    if is_generated_duplicate(candidate.expression, seen_keys, seen_expressions):
                        candidate.lifecycle_status = "duplicate_expression_skipped"
                        continue
                    key = expression_key(candidate.expression)
                    if self._observability_diversity_boost:
                        if key in seen_keys or self._is_observability_avoided(candidate.expression):
                            continue
                        self._mark_observability_candidate(candidate)
                    seen_keys.add(key)
                    seen_expressions.append(candidate.expression)
                    candidates.append(candidate)
            except Exception as exc:
                logger.warning(
                    "HypothesisDrivenGenerator: %s mode failed for candidate %d: %s",
                    mode, i, redact_error_message(exc),
                )
                # Fallback: try random exploration
                try:
                    fallback = self._generate_random_exploration(ds)
                    if fallback is not None:
                        if is_high_turnover_generation_risk(fallback.expression):
                            fallback.lifecycle_status = "generation_risk_skipped"
                            continue
                        if is_generated_duplicate(fallback.expression, seen_keys, seen_expressions):
                            fallback.lifecycle_status = "duplicate_expression_skipped"
                            continue
                        key = expression_key(fallback.expression)
                        if self._observability_diversity_boost:
                            if key in seen_keys or self._is_observability_avoided(fallback.expression):
                                continue
                            self._mark_observability_candidate(fallback)
                        seen_keys.add(key)
                        seen_expressions.append(fallback.expression)
                        candidates.append(fallback)
                except Exception:
                    logger.warning("random exploration fallback generation failed", exc_info=True)
                    continue

        # Log generation summary
        actual = self._router.actual_ratios
        logger.info(
            "HypothesisDrivenGenerator: generated %d/%d candidates. "
            "Mode ratios: H=%.1f%% E=%.1f%% R=%.1f%%",
            len(candidates), count,
            actual["hypothesis_driven"] * 100,
            actual["experience_feedback"] * 100,
            actual["random_exploration"] * 100,
        )

        return candidates

    # ── Generation Modes ────────────────────────────────────────────

    def _generate_hypothesis_driven(self, dataset_id: str) -> Candidate | None:
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
        window = self._expr_selector.select_window(expr_family, window_weights)

        # Step 4: Field selection
        if self._field_selector is None:
            return self._generate_random_exploration(dataset_id)
        selected_fields = self._field_selector.select_fields(hypothesis, dataset_id, count=2)
        selected_fields = self._prioritize_knowledge_fields(selected_fields)
        if not selected_fields:
            return self._generate_random_exploration(dataset_id)

        # Step 5: Context adaptation
        context = self._adapter.adapt(hypothesis)

        # Step 6: Alpha assembly
        expression = self._build_expression(
            expr_family, selected_fields, window,
            field_categories=hypothesis.field_categories,
        )

        # Determine which field category was used
        field_category_used = ""
        for fc in hypothesis.field_categories:
            if fc.examples and any(ex in selected_fields for ex in fc.examples):
                field_category_used = fc.category
                break
        if not field_category_used:
            field_category_used = hypothesis.field_categories[0].category if hypothesis.field_categories else ""

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
            data_fields=self._extract_fields(expression) or sorted(selected_fields),
            operators=self._extract_operators(expression),
            source_tags=["hypothesis_driven"],
            dataset_id=dataset_id or self._dataset_id,
            template_source=meta.to_json(),
        )
        if self._expression_forbidden(candidate.expression):
            return self._generate_random_exploration(dataset_id)
        return candidate

    def _generate_experience_feedback(self, dataset_id: str) -> Candidate | None:
        """Generate a candidate biased by experience-winning patterns.

        Uses DynamicThemeEngine with experience operator/window preferences.
        """
        if self._theme_engine is None:
            return self._generate_random_exploration(dataset_id)

        ds = dataset_id or self._dataset_id
        try:
            # Apply experience bias to theme engine
            if self._experience_windows and hasattr(self._theme_engine, '_windows'):
                self._theme_engine._windows = list(  # type: ignore[union-attr]
                    self._experience_windows if self._experience_windows
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

            meta = GenerationMeta(
                mode="experience_feedback",
                hypothesis_id=tmpl.category,
                hypothesis_name=f"Experience-biased {tmpl.category}",
                expression_family_id="experience_pattern",
                field_category="experience_feedback",
                selected_fields=tmpl.field_slots if tmpl.field_slots else [],
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

    def _generate_random_exploration(self, dataset_id: str) -> Candidate | None:
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

            meta = GenerationMeta(
                mode="random_exploration",
                hypothesis_id="random",
                hypothesis_name="Random Exploration",
                expression_family_id=tmpl.category,
                field_category="random_exploration",
                selected_fields=tmpl.field_slots if tmpl.field_slots else [],
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

    def _generate_bare_fallback(self, dataset_id: str) -> Candidate | None:
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
        operators = {str(item).lower() for item in self._operators if str(item)}
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
        fallback_fields = sorted(self._fields)
        normalized = normalize_operator_aliases(expression)
        if fallback_fields:
            normalized = self._sanitize_expression(normalized, fallback_fields)
            normalized = self._validate_dataset_fields(normalized, fallback_fields)
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
        for pattern in self._knowledge_constraints.get("forbidden_patterns") or []:
            pattern_text = str(pattern or "").strip()
            if not pattern_text:
                continue
            needle = pattern_text.lower()
            if needle and needle in expression_lower:
                return True
            if pattern_text in {expression_text, current_key, current_fingerprint}:
                return True
            try:
                pattern_key = expression_key(pattern_text)
                pattern_fingerprint = expression_fingerprint(pattern_text)
            except Exception:
                pattern_key = ""
                pattern_fingerprint = ""
            if current_key and pattern_key and current_key == pattern_key:
                return True
            if current_fingerprint and pattern_fingerprint and current_fingerprint == pattern_fingerprint:
                return True
            try:
                if (
                    expression_similarity(expression_text, pattern_text)
                    >= _FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD
                ):
                    return True
            except Exception:
                logger.debug("failed to compare forbidden expression pattern", exc_info=True)
        return False

    def _prioritize_knowledge_fields(self, fields: list[str]) -> list[str]:
        preferred = set(self._knowledge_constraints.get("preferred_fields") or [])
        if not preferred:
            return list(fields)
        front = [field for field in fields if field.lower() in preferred]
        rest = [field for field in fields if field.lower() not in preferred]
        return front + rest

    # ── Expression Building ─────────────────────────────────────────

    def _build_expression(
        self,
        family: "ExpressionFamily",
        fields: list[str],
        window: int,
        field_categories: list["FieldCategoryDef"] | None = None,
    ) -> str:
        """Build a concrete expression from an ExpressionFamily template.

        Placeholders resolved (in order):
          {field_xxx}   → matched via field_categories (e.g. {field_illiq} → analyst4_illiq)
          {field}       → replaced with fields[0]
          {f1}, {f2}    → replaced with fields[0], fields[1]
          {window}, {w} → replaced with window size
          {window_short}, {window_long} → replaced from family window pairs

        For {field_xxx}: looks up *xxx* in the hypothesis's field_categories,
        and picks a concrete field from that category's examples.
        Falls back to the first field in *fields* if no match found.
        """
        expr = family.structure
        used_fields: set[str] = set()  # BUG-10: track assigned fields to avoid same-field duplication

        # ── Phase 1: named field placeholders {field_xxx} ──
        named_matches = re.findall(r"\{field_(\w+)\}", expr)
        if named_matches and field_categories:
            for placeholder_name in named_matches:
                concrete_field = self._resolve_named_field(
                    placeholder_name, field_categories, fields, exclude=used_fields
                )
                expr = expr.replace(f"{{field_{placeholder_name}}}", concrete_field)
                used_fields.add(concrete_field)
        elif named_matches:
            # No field_categories available — use sequential fields
            for i, placeholder_name in enumerate(named_matches):
                fallback = fields[i] if i < len(fields) else (fields[0] if fields else "returns")
                expr = expr.replace(f"{{field_{placeholder_name}}}", fallback)
                used_fields.add(fallback)

        # ── Phase 2: generic field placeholders ──
        if "{field}" in expr:
            f = _pick_unused(fields, 0, used_fields)
            expr = expr.replace("{field}", f)
            used_fields.add(f)
        if "{f1}" in expr:
            f = _pick_unused(fields, 0, used_fields)
            expr = expr.replace("{f1}", f)
            used_fields.add(f)
        if "{f2}" in expr:
            f = _pick_unused(fields, 1, used_fields)
            expr = expr.replace("{f2}", f)
            used_fields.add(f)

        # ── Phase 3: window placeholders ──
        if "{window}" in expr:
            expr = expr.replace("{window}", str(window))
        if "{w}" in expr:
            expr = expr.replace("{w}", str(window))
        # Handle bare (window) syntax used in some YAML files
        expr = re.sub(r'\(window\)', f'({window})', expr)

        # Window pairs for acceleration-type families
        if "{window_short}" in expr and family.windows_short:
            expr = expr.replace("{window_short}", str(family.windows_short[0]))
        elif "{window_short}" in expr:
            expr = expr.replace("{window_short}", str(window))
        if "{window_long}" in expr and family.windows_long:
            expr = expr.replace("{window_long}", str(family.windows_long[0]))
        elif "{window_long}" in expr:
            expr = expr.replace("{window_long}", str(window * 4))

        # ── Phase 4: sanitize remaining semantic tokens ──
        expr = self._sanitize_expression(expr, fields, already_used=used_fields)

        # ── Phase 5: validate all fields exist in dataset ──
        expr = self._validate_dataset_fields(expr, fields)

        # ── Phase 6: normalize semantic YAML shorthands into real operators ──
        expr = self._normalize_wq_expression_shape(expr, window)

        return normalize_operator_aliases(expr)

    def _normalize_wq_expression_shape(self, expr: str, window: int | None = None) -> str:
        return self._expression_support().normalize_wq_expression_shape(expr, window)

    def _operator_available(self, name: str) -> bool:
        return self._expression_support().operator_available(name)

    def _normalize_field_function_calls(self, expr: str, window: int | None = None) -> str:
        return self._expression_support().normalize_field_function_calls(expr, window)

    def _rewrite_field_function_node(self, node, window: int | None = None):
        return self._expression_support().rewrite_field_function_node(node, window)

    def _is_field_function_name(self, name: str) -> bool:
        return self._expression_support().is_field_function_name(name)

    def _replacement_for_field_function(
        self,
        field_name: str,
        args,
        window: int | None = None,
    ):
        return self._expression_support().replacement_for_field_function(field_name, args, window)

    def _sanitize_expression(
        self,
        expr: str,
        fields: list[str],
        already_used: set[str] | None = None,
    ) -> str:
        return self._expression_support().sanitize_expression(expr, fields, already_used)

    def _find_best_field_match(
        self,
        token: str,
        dataset_fields: list[str],
        used_fields: set[str],
    ) -> str | None:
        return self._expression_support().find_best_field_match(token, dataset_fields, used_fields)

    def _validate_dataset_fields(self, expr: str, fallback_fields: list[str]) -> str:
        return self._expression_support().validate_dataset_fields(expr, fallback_fields)

    def _resolve_named_field(
        self,
        name: str,
        field_categories: list["FieldCategoryDef"],
        selected_fields: list[str],
        exclude: set[str] | None = None,
    ) -> str:
        return self._expression_support().resolve_named_field(
            name,
            field_categories,
            selected_fields,
            exclude,
        )

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
                candidate.template_source = f"{candidate.template_source}:observability"
            return
        if isinstance(meta, dict):
            meta["observability_diversified"] = True
            candidate.template_source = json.dumps(meta, ensure_ascii=False)

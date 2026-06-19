"""FieldSelector — semantic category → concrete field name resolution."""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from brain_alpha_ops.research.field_quality import generation_field_ids
from brain_alpha_ops.research.hypothesis_generator_helpers import (
    semantic_field_tokens as _semantic_field_tokens,
)

if TYPE_CHECKING:
    from brain_alpha_ops.research.dataset_selector import DatasetSelector
    from brain_alpha_ops.research.hypothesis_library import (
        FieldCategoryDef,
        Hypothesis,
    )

logger = logging.getLogger(__name__)


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
            chosen_cat: "FieldCategoryDef" = random.choices(
                remaining, weights=weights, k=1
            )[0]
            remaining.remove(chosen_cat)

            fields = self._resolve_category(
                chosen_cat.category, dataset_id, examples=chosen_cat.examples
            )

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
        examples_key = ",".join(
            str(item).lower() for item in (examples or [])
        )
        cache_key = f"{dataset_id}::{category_name}::{examples_key}"
        if cache_key in self._field_cache:
            return self._field_cache[cache_key]

        # Try get_fields_by_category if dataset_selector supports it
        fields: list[str] = []
        if hasattr(self._selector, "get_fields_by_category"):
            try:
                fields = self._selector.get_fields_by_category(
                    category_name, dataset_id
                )  # type: ignore[attr-defined]
            except TypeError:
                fields = self._selector.get_fields_by_category(
                    category_name
                )  # type: ignore[attr-defined]

        dataset_fields = self._dataset_field_set(dataset_id)
        if dataset_fields:
            fields = [
                field for field in fields if field.lower() in dataset_fields
            ]
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
        limit: int = 200,  # wider field pool (was 60)
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


__all__ = ["FieldSelector"]

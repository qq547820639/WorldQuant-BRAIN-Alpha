"""BRAIN Alpha Template registry — loads predefined templates, supports dataset instantiation."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from brain_alpha_ops.redaction import redact_error_message

if TYPE_CHECKING:
    from brain_alpha_ops.data import FieldDatasetMapper, OfficialDataLoader


logger = logging.getLogger(__name__)

_FIELD_TYPE_ALIASES: dict[str, set[str]] = {
    "fundamental": {
        "analyst",
        "fundamental",
        "growth",
        "model",
        "profitability",
        "profitability_ratio",
        "quality",
        "valuation",
    },
    "quality": {"fundamental", "margin", "profitability", "profitability_ratio", "quality", "roa", "roe"},
    "valuation": {"fundamental", "valuation", "value"},
    "price": {"close", "open", "price", "returns"},
    "volume": {"adv", "liquidity", "volume"},
}


@dataclass
class AlphaTemplate:
    """A pre-defined alpha expression template."""
    id: str
    name: str
    description: str
    expression_template: str           # contains {FIELD_*} / {WINDOW} placeholders
    required_field_types: list[str] = field(default_factory=list)
    applicable_datasets: list[str] = field(default_factory=list)  # empty = all
    tags: list[str] = field(default_factory=list)


# Built-in minimal template set (used when data/alpha_templates.json is absent)
_BUILTIN_TEMPLATES = [
    AlphaTemplate(
        id="momentum_price",
        name="Price Momentum",
        description="Risk-adjusted price strength over medium horizon.",
        expression_template="ts_rank({FIELD_1}, {WINDOW})",
        required_field_types=["price"],
        tags=["momentum", "price"],
    ),
    AlphaTemplate(
        id="value_fundamental",
        name="Fundamental Value",
        description="Undervalued based on fundamental ratio.",
        expression_template="rank(-{FIELD_1})",
        required_field_types=["fundamental", "valuation"],
        tags=["value", "fundamental"],
    ),
    AlphaTemplate(
        id="quality_composite",
        name="Quality Composite",
        description="Composite of two quality metrics.",
        expression_template="rank(zscore({FIELD_1})) * rank(zscore({FIELD_2}))",
        required_field_types=["fundamental", "quality"],
        tags=["quality", "composite"],
    ),
    AlphaTemplate(
        id="reversal_short_term",
        name="Short-term Reversal",
        description="Short-term overreaction reversal.",
        expression_template="-1 * ts_rank({FIELD_1}, {WINDOW})",
        required_field_types=["price"],
        tags=["reversal", "price"],
    ),
    AlphaTemplate(
        id="liquidity_volume",
        name="Volume Liquidity",
        description="Abnormal volume activity.",
        expression_template="rank(ts_mean({FIELD_1}, {WINDOW}))",
        required_field_types=["volume"],
        tags=["liquidity", "volume"],
    ),
    AlphaTemplate(
        id="cross_sectional",
        name="Cross-Sectional",
        description="Group-relative ranking.",
        expression_template="group_rank({FIELD_1}, {GROUP})",
        required_field_types=["fundamental", "price", "analyst"],
        tags=["cross_sectional"],
    ),
]


class AlphaTemplateRegistry:
    """Registry of alpha templates, supporting dataset-aware instantiation.

    Usage::

        from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper
        registry = AlphaTemplateRegistry(loader, mapper)
        templates = registry.get_for_dataset("analyst4")
        expr = registry.instantiate("momentum_price", dataset_id="analyst4")
    """

    def __init__(
        self,
        loader: "OfficialDataLoader",
        mapper: "FieldDatasetMapper",
    ) -> None:
        self._loader = loader
        self._mapper = mapper
        self._templates: dict[str, AlphaTemplate] = {}
        self._dataset_field_cache: dict[str, tuple[tuple[str, ...], set[str]]] = {}
        self._dataset_template_cache: dict[str, tuple[AlphaTemplate, ...]] = {}

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def load_templates(self, template_file: str = "data/alpha_templates.json") -> None:
        """Load templates from a JSON file. Falls back to built-in set."""
        self._dataset_template_cache.clear()
        path = Path(__file__).resolve().parents[2] / template_file
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                for item in raw:
                    tmpl = AlphaTemplate(
                        id=str(item.get("id", "")),
                        name=str(item.get("name", "")),
                        description=str(item.get("description", "")),
                        expression_template=str(item.get("expression_template", "")),
                        required_field_types=list(item.get("required_field_types", [])),
                        applicable_datasets=list(item.get("applicable_datasets", [])),
                        tags=list(item.get("tags", [])),
                    )
                    self._templates[tmpl.id] = tmpl
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "failed to load alpha template JSON; using built-in templates: %s",
                    redact_error_message(exc),
                )

        if not self._templates:
            for tmpl in _BUILTIN_TEMPLATES:
                self._templates[tmpl.id] = tmpl

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def get_for_dataset(self, dataset_id: str) -> list[AlphaTemplate]:
        """Return templates applicable to *dataset_id*."""
        cache_key = str(dataset_id or "")
        cached = self._dataset_template_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        result = []
        _, available_types = self._dataset_field_info(dataset_id)
        for tmpl in self._templates.values():
            if not tmpl.applicable_datasets or dataset_id in tmpl.applicable_datasets:
                if not tmpl.required_field_types:
                    result.append(tmpl)
                elif _required_field_types_available(tmpl.required_field_types, available_types):
                    result.append(tmpl)
        self._dataset_template_cache[cache_key] = tuple(result)
        return result

    def get(self, template_id: str) -> AlphaTemplate | None:
        return self._templates.get(template_id)

    def get_all(self) -> list[AlphaTemplate]:
        return list(self._templates.values())

    # ------------------------------------------------------------------
    # Instantiate
    # ------------------------------------------------------------------
    def instantiate(
        self,
        template_id: str,
        dataset_id: str,
        seed: int | None = None,
    ) -> str:
        """Fill template placeholders with concrete fields from *dataset_id*."""
        tmpl = self._templates.get(template_id)
        if tmpl is None:
            raise KeyError(f"Unknown template: {template_id}")

        rng = random.Random(seed) if seed is not None else random

        field_names, _ = self._dataset_field_info(dataset_id)
        if not field_names:
            raise ValueError(f"Dataset {dataset_id!r} has no fields for template {template_id!r}")

        expr = tmpl.expression_template
        windows = [3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252]
        groups = ["sector", "industry", "subindustry"]

        # Replace {FIELD_1}, {FIELD_2}, ...
        for i in range(1, 5):
            placeholder = f"{{FIELD_{i}}}"
            if placeholder in expr:
                expr = expr.replace(placeholder, rng.choice(field_names), 1)

        # Replace {WINDOW}
        if "{WINDOW}" in expr:
            expr = expr.replace("{WINDOW}", str(rng.choice(windows)))

        # Replace {GROUP}
        if "{GROUP}" in expr:
            expr = expr.replace("{GROUP}", rng.choice(groups))

        return expr

    def _dataset_field_info(self, dataset_id: str) -> tuple[tuple[str, ...], set[str]]:
        cache_key = str(dataset_id or "")
        cached = self._dataset_field_cache.get(cache_key)
        if cached is not None:
            return cached

        field_names_list: list[str] = []
        for field in self._mapper.fields_for(dataset_id):
            field_text = str(field or "").strip()
            if field_text:
                field_names_list.append(field_text)
        field_names = tuple(field_names_list)
        field_name_tokens = {field.lower() for field in field_names}
        dataset_fields = self._loader.get_fields(dataset_id)
        available_types = _available_field_types(dataset_fields, field_name_tokens)
        result = (field_names, available_types)
        self._dataset_field_cache[cache_key] = result
        return result


def _available_field_types(dataset_fields: list[object], field_names: set[str]) -> set[str]:
    available = set(field_names)
    for field in dataset_fields:
        field_id = str(getattr(field, "id", "") or "").lower().strip()
        category = str(getattr(field, "category", "") or "").lower().strip()
        if field_id:
            available.add(field_id)
            available.update(part for part in field_id.replace("-", "_").split("_") if part)
        if category:
            available.add(category)
            available.update(part for part in category.replace("-", "_").split("_") if part)
    return available


def _required_field_types_available(required_types: list[str], available_types: set[str]) -> bool:
    for required in required_types:
        required_key = str(required or "").lower().strip()
        if not required_key:
            continue
        aliases = {required_key, *(_FIELD_TYPE_ALIASES.get(required_key, set()))}
        if not aliases.intersection(available_types):
            return False
    return True

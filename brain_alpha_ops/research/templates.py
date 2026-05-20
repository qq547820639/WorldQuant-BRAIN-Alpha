"""BRAIN Alpha Template registry — loads predefined templates, supports dataset instantiation."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from brain_alpha_ops.data import OfficialDataLoader, FieldDatasetMapper


@dataclass
class AlphaTemplate:
    """A pre-defined alpha expression template."""
    id: str
    name: str
    description: str
    expression_template: str           # contains {FIELD_*} / {WINDOW} placeholders
    required_field_types: List[str] = field(default_factory=list)
    applicable_datasets: List[str] = field(default_factory=list)  # empty = all
    tags: List[str] = field(default_factory=list)


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
        self._templates: Dict[str, AlphaTemplate] = {}

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def load_templates(self, template_file: str = "data/alpha_templates.json") -> None:
        """Load templates from a JSON file. Falls back to built-in set."""
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
            except (json.JSONDecodeError, OSError):
                pass

        if not self._templates:
            for tmpl in _BUILTIN_TEMPLATES:
                self._templates[tmpl.id] = tmpl

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def get_for_dataset(self, dataset_id: str) -> List[AlphaTemplate]:
        """Return templates applicable to *dataset_id*."""
        result = []
        for tmpl in self._templates.values():
            if not tmpl.applicable_datasets or dataset_id in tmpl.applicable_datasets:
                # Check that at least one required field type exists in dataset
                fields = set(self._mapper.fields_for(dataset_id))
                if not tmpl.required_field_types:
                    result.append(tmpl)
                elif any(
                    any(f.id.lower() in fields for f in self._loader.get_fields(dataset_id))
                    for _ in tmpl.required_field_types  # simplified: any field exists
                ):
                    result.append(tmpl)
        return result

    def get(self, template_id: str) -> Optional[AlphaTemplate]:
        return self._templates.get(template_id)

    def get_all(self) -> List[AlphaTemplate]:
        return list(self._templates.values())

    # ------------------------------------------------------------------
    # Instantiate
    # ------------------------------------------------------------------
    def instantiate(
        self,
        template_id: str,
        dataset_id: str,
        seed: Optional[int] = None,
    ) -> str:
        """Fill template placeholders with concrete fields from *dataset_id*."""
        tmpl = self._templates.get(template_id)
        if tmpl is None:
            raise KeyError(f"Unknown template: {template_id}")

        if seed is not None:
            random.seed(seed)

        field_names = self._mapper.fields_for(dataset_id)
        if not field_names:
            return tmpl.expression_template

        expr = tmpl.expression_template
        windows = [3, 5, 8, 10, 12, 15, 20, 30, 40, 60, 90, 120, 180, 252]
        groups = ["sector", "industry", "subindustry"]

        # Replace {FIELD_1}, {FIELD_2}, ...
        for i in range(1, 5):
            placeholder = f"{{FIELD_{i}}}"
            if placeholder in expr:
                expr = expr.replace(placeholder, random.choice(field_names), 1)

        # Replace {WINDOW}
        if "{WINDOW}" in expr:
            expr = expr.replace("{WINDOW}", str(random.choice(windows)))

        # Replace {GROUP}
        if "{GROUP}" in expr:
            expr = expr.replace("{GROUP}", random.choice(groups))

        return expr

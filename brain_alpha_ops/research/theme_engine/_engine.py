"""Dynamic Alpha theme engine — ``DynamicThemeEngine`` class.

Generates Alpha expression templates from official fields & operators.
"""
from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING

from brain_alpha_ops.research.field_quality import filter_generation_fields
from brain_alpha_ops.research.generator_metadata import (
    expression_windows_within_constraints,
)
from brain_alpha_ops.research.theme_engine._helpers import (
    _build_auto_skeletons_impl,
    _build_category_map,
    _normalize_operator_aliases,
)
from brain_alpha_ops.research.theme_engine._skeletons import TEMPLATE_SKELETONS
from brain_alpha_ops.research.theme_engine._template import (
    DEFAULT_GROUPS,
    DEFAULT_WINDOWS,
    PRODUCTION_STRUCTURE_SKELETONS,
    ThemeTemplate,
)

if TYPE_CHECKING:
    from brain_alpha_ops.data import OfficialDataLoader, OfficialField


class DynamicThemeEngine:
    """Generates Alpha expression templates from official fields and operators.

    Usage::

        from brain_alpha_ops.data import OfficialDataLoader
        engine = DynamicThemeEngine(OfficialDataLoader.instance())
        engine.build_categories()
        themes = engine.generate(dataset_id="analyst4", n=50)
    """

    def __init__(self, loader: "OfficialDataLoader") -> None:
        self._loader = loader
        self._categories: dict[str, list["OfficialField"]] = {}
        self._windows = list(DEFAULT_WINDOWS)
        self._groups = list(DEFAULT_GROUPS)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build_categories(self) -> None:
        """Group all official fields by their category string."""
        self._categories.clear()
        for f in self._loader.get_fields():
            cat = (f.category or "unknown").lower()
            self._categories.setdefault(cat, []).append(f)
        # P0-3: Auto-generate additional skeletons from official operators
        self._auto_generated_skeletons = self._build_auto_skeletons()

    # ------------------------------------------------------------------
    # P0-3: Auto-generate skeletons from BRAIN official operators
    # ------------------------------------------------------------------
    def _build_auto_skeletons(self) -> dict[str, list[str]]:
        """Generate expression skeletons by combining BRAIN official operators.

        Delegates to ``_build_auto_skeletons_impl`` so the heavy body can live
        in ``_helpers`` while preserving the original method signature.
        """
        return _build_auto_skeletons_impl(self._loader)

    # P1-7: Skeleton diversity tracker — counts per skeleton-normalized form
    _skeleton_usage: dict[str, int] = {}

    def record_skeleton_usage(self, expression: str, category: str, blocked: bool = False) -> None:
        """Track skeleton usage frequency. Blocked skeletons get deprioritized."""
        import re
        normalized = re.sub(r'\b[a-z][a-z0-9_]*\b', 'FIELD', expression)
        normalized = re.sub(r'\b\d+\b', 'W', normalized)
        key = f"{category}:{normalized}"
        if blocked:
            self._skeleton_usage[key] = self._skeleton_usage.get(key, 0) + 10  # heavy penalty for blocked
        else:
            self._skeleton_usage[key] = self._skeleton_usage.get(key, 0) + 1

    def get_blocked_skeleton_count(self) -> int:
        """Count skeletons marked as blocked (score >= 10)."""
        return sum(1 for v in self._skeleton_usage.values() if v >= 10)

    def is_skeleton_overused(self, expression: str, category: str, max_usage: int = 5) -> bool:
        """Check if a skeleton has been overused."""
        import re
        normalized = re.sub(r'\b[a-z][a-z0-9_]*\b', 'FIELD', expression)
        normalized = re.sub(r'\b\d+\b', 'W', normalized)
        key = f"{category}:{normalized}"
        return self._skeleton_usage.get(key, 0) >= max_usage

    @property
    def auto_skeletons(self) -> dict[str, list[str]]:
        """Return auto-generated skeletons (available after build_categories)."""
        return getattr(self, '_auto_generated_skeletons', {})

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    def generate(
        self,
        dataset_id: str,
        n: int = 50,
        seed: int | None = None,
    ) -> list[ThemeTemplate]:
        """Generate *n* expression templates for *dataset_id*."""
        if seed is not None:
            random.seed(seed)

        raw_fields = self._loader.get_fields(dataset_id)
        fields = filter_generation_fields(raw_fields)
        if not fields:
            return []

        # Build per-category field pools for this dataset
        cat_fields: dict[str, list[str]] = {}
        for f in fields:
            cat = (f.category or "unknown").lower()
            cat_fields.setdefault(cat, []).append(f.id)

        # Map category→skeleton category
        category_map = _build_category_map()

        # Merge proven TEMPLATE_SKELETONS with auto-generated skeletons
        auto_skel = self.auto_skeletons
        official_ops = self._official_operator_names()
        production_skeletons = [
            skeleton
            for skeleton in PRODUCTION_STRUCTURE_SKELETONS
            if self._skeleton_uses_only_official_operators(skeleton, official_ops)
        ]
        filtered_auto_skel = {
            cat: [
                skeleton
                for skeleton in skeletons
                if self._skeleton_uses_only_official_operators(skeleton, official_ops)
            ]
            for cat, skeletons in auto_skel.items()
        }
        filtered_auto_skel = {cat: skeletons for cat, skeletons in filtered_auto_skel.items() if skeletons}
        merged_skeletons: dict[str, list[str]] = {}
        for cat in set(list(TEMPLATE_SKELETONS.keys()) + list(auto_skel.keys())):
            candidates = TEMPLATE_SKELETONS.get(cat, []) + filtered_auto_skel.get(cat, [])
            filtered = [
                skeleton
                for skeleton in candidates
                if self._skeleton_uses_only_official_operators(skeleton, official_ops)
            ]
            if filtered:
                merged_skeletons[cat] = filtered
        if not merged_skeletons and not production_skeletons:
            return []

        templates: list[ThemeTemplate] = []
        attempts = 0
        while len(templates) < n and attempts < n * 3:
            attempts += 1

            field_universe = {field for values in cat_fields.values() for field in values}

            # Seed each batch with structurally complete hybrid templates when
            # possible. This improves actual expression quality without changing
            # scoring or submit thresholds.
            if len(field_universe) >= 4 and len(templates) < min(n, len(production_skeletons)):
                skeleton_cat = "hybrid"
                skeleton = production_skeletons[len(templates) % len(production_skeletons)]
            # Pick a skeleton category (70% auto-generated, 30% proven templates for exploration)
            elif random.random() < 0.7 and filtered_auto_skel:
                skeleton_cat = random.choice(list(filtered_auto_skel.keys()))
                skeletons = filtered_auto_skel[skeleton_cat]
                skeleton = random.choice(skeletons)
            else:
                skeleton_cat = random.choice(list(merged_skeletons.keys()))
                skeletons = merged_skeletons[skeleton_cat]
                skeleton = random.choice(skeletons)

            # Map to field categories
            mapped_cats = category_map.get(skeleton_cat, [skeleton_cat])
            available_cats = [c for c in mapped_cats if c in cat_fields and cat_fields[c]]
            if not available_cats:
                # Fallback: use any category that has fields
                available_cats = [c for c in cat_fields if cat_fields[c]]
            if not available_cats:
                continue

            # Fill placeholders
            expression = self._fill_placeholders(skeleton, available_cats, cat_fields)
            if not expression_windows_within_constraints(expression):
                continue
            field_slots = self._extract_field_slots(expression, fields)

            tmpl = ThemeTemplate(
                id=f"theme_{dataset_id}_{len(templates):04d}",
                name=f"{skeleton_cat}_{len(templates):04d}",
                category=skeleton_cat,
                expression=expression,
                field_slots=field_slots,
                description=f"Auto-generated {skeleton_cat} template for {dataset_id}",
            )
            templates.append(tmpl)

        return templates

    def mutate_expression(
        self,
        expression: str,
        dataset_id: str,
        seed: int | None = None,
    ) -> str:
        """Produce a variant of *expression* using fields from *dataset_id*."""
        if seed is not None:
            random.seed(seed)

        fields = self._loader.get_fields(dataset_id)
        if not fields:
            return expression

        field_ids = [f.id for f in fields]
        windows = self._windows

        # Replace numeric literals with varied windows
        # Skip numbers that are part of field names by requiring non-identifier
        # boundaries on both sides.
        def _replace_window(match: re.Match) -> str:
            prefix = expression[: match.start()]
            if re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*=\s*$", prefix):
                return match.group(0)
            num = int(match.group(1))
            if 3 <= num <= 252:
                return str(random.choice(windows))
            return match.group(0)

        mutated = re.sub(r"(?<![a-zA-Z0-9_])(\d+)(?![a-zA-Z0-9_])", _replace_window, expression)

        # Optionally wrap with transform
        variant = random.randint(0, 3)
        if variant == 1:
            mutated = f"winsorize({mutated}, std={random.choice([3,4,5])})"
        elif variant == 2:
            mutated = f"zscore({mutated})"

        normalized = _normalize_operator_aliases(mutated)
        return normalized if expression_windows_within_constraints(normalized) else expression

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _fill_placeholders(
        self,
        skeleton: str,
        available_cats: list[str],
        cat_fields: dict[str, list[str]],
    ) -> str:
        result = skeleton
        used_fields: list[str] = []

        all_fields = [field for cat in available_cats for field in cat_fields[cat]]

        def choose_field() -> str:
            unused = [field for field in all_fields if field not in used_fields]
            pool = unused or all_fields
            return random.choice(pool) if pool else "returns"

        # {FIELD_A}, {FIELD_B}, {FIELD_C}, {FIELD_D}, {FIELD}
        for placeholder in ("{FIELD_A}", "{FIELD_B}", "{FIELD_C}", "{FIELD_D}", "{FIELD}"):
            if placeholder in result:
                field = choose_field()
                result = result.replace(placeholder, field)
                used_fields.append(field)

        # {WINDOW}, {WINDOW2}, {WINDOW3}, ... each receive a legal window value.
        result = re.sub(r"\{WINDOW\d*\}", lambda _match: str(random.choice(self._windows)), result)

        # {GROUP}
        if "{GROUP}" in result:
            result = result.replace("{GROUP}", random.choice(self._groups))

        # {STD} — safety net for any legacy template that still carries this placeholder
        if "{STD}" in result:
            result = result.replace("{STD}", str(random.choice([3, 4])))

        # ── Dataset field validation: reject phantom fields ──
        result = _normalize_operator_aliases(result)
        result = self._validate_fill_result(result, cat_fields)

        return result

    def _extract_field_slots(self, expression: str, fields: list["OfficialField"]) -> list[str]:
        """Return dataset field ids present in the generated expression."""
        import re as _re

        ids = {field.id.lower() for field in fields}
        tokens = {token.lower() for token in _re.findall(r"\b([a-zA-Z_]\w*)\b", expression)}
        return sorted(ids & tokens)

    def _validate_fill_result(
        self,
        result: str,
        cat_fields: dict[str, list[str]],
    ) -> str:
        """Ensure every field-like token in *result* exists in official field data.

        Phantom fields (e.g. ``anl20_…``, concatenated names) that survive
        placeholder filling are replaced with a random valid field from
        *cat_fields*.  This mirrors the safety net in
        ``HypothesisDrivenGenerator._validate_dataset_fields`` but protects
        the ``experience_feedback`` / ``random_exploration`` code paths that
        bypass that generator.
        """
        import re as _re

        valid_ids = {field.lower() for fields in cat_fields.values() for field in fields}
        _OPS = {op.name.lower() for op in self._loader.get_operators()}
        _OPS.update({"returns", "sector", "industry", "market", "subindustry"})

        tokens = _re.findall(r"\b([a-zA-Z_]\w+)\b", result)
        all_cat_fields = [f for fields in cat_fields.values() for f in fields]

        for t in tokens:
            # Only flag tokens that look like field names (contain underscore)
            # — bare words like std/k/hump are operator parameters, not fields.
            if t not in _OPS and t.lower() not in valid_ids and "_" in t:
                replacement = random.choice(all_cat_fields) if all_cat_fields else "returns"
                result = _re.sub(rf"\b{_re.escape(t)}\b", replacement, result)

        return result

    def _official_operator_names(self) -> set[str]:
        return {op.name.lower() for op in self._loader.get_operators()}

    @staticmethod
    def _operators_in_skeleton(skeleton: str) -> set[str]:
        normalized = _normalize_operator_aliases(skeleton)
        return {
            token.lower()
            for token in re.findall(r"\b([A-Za-z_]\w*)\s*\(", normalized)
        }

    @classmethod
    def _skeleton_uses_only_official_operators(cls, skeleton: str, official_ops: set[str]) -> bool:
        operators = cls._operators_in_skeleton(skeleton)
        return bool(operators) and operators <= official_ops

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def windows(self) -> list[int]:
        return list(self._windows)

    @windows.setter
    def windows(self, value: list[int]) -> None:
        self._windows = list(value)

    @property
    def categories(self) -> list[str]:
        return sorted(self._categories.keys())

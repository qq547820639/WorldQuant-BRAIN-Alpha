"""Field sanitization, validation, resolution, and extraction mixin.

Extracted from the original ``hypothesis_expression_support.py`` monolith
(deep-optimization-phase13). The methods here replace remaining semantic
tokens with actual dataset field names, validate field-like tokens against
the active dataset, resolve named field placeholders to concrete BRAIN
fields, and extract field/operator lists from expressions. They are mixed
into ``HypothesisExpressionSupport`` in ``_support`` to keep the main class
file under the per-submodule line budget while preserving the public class
API.
"""

from __future__ import annotations

import re

from brain_alpha_ops.research.expression_ast import (
    ordered_operators,
    profile_expression,
)
from brain_alpha_ops.research.fallback_generation import normalize_operator_aliases
from brain_alpha_ops.research.field_quality import generation_field_ids
from brain_alpha_ops.research.hypothesis_library import FieldCategoryDef

from brain_alpha_ops.research.hypothesis_expression_support._operators import (
    GROUP_KEYS,
    _current_official_operator_names,
)


class _FieldResolutionMixin:
    """Field sanitization, validation, resolution, and extraction."""

    def sanitize_expression(
        self,
        expr: str,
        fields: list[str],
        already_used: set[str] | None = None,
    ) -> str:
        """Replace remaining semantic tokens with actual dataset field names."""
        expr = normalize_operator_aliases(expr)
        if not fields:
            return expr

        dataset_fields = sorted(self._fields) if self._fields else []
        dataset_fields_lower = {f.lower() for f in dataset_fields}
        field_set_lower = {f.lower() for f in fields}
        known_ops = self._operators or set(_current_official_operator_names())
        brain_ops = set(_current_official_operator_names()) | GROUP_KEYS

        tokens = re.findall(r'\b([a-zA-Z_]\w+)\b', expr)
        replacements: dict[str, str] = {}
        used_fields: set[str] = set(already_used or set())
        used_fields.update(t.lower() for t in tokens if t.lower() in dataset_fields_lower)

        for token in tokens:
            t_lower = token.lower()
            if (
                t_lower in dataset_fields_lower
                or t_lower in known_ops
                or t_lower in field_set_lower
                or t_lower in brain_ops
                or t_lower in {'-1', 'nan', 'inf', 'std'}
            ):
                continue

            best_field = self.find_best_field_match(token, dataset_fields, used_fields)
            if best_field:
                replacements[token] = best_field
                used_fields.add(best_field)
            else:
                for df in dataset_fields:
                    if df not in used_fields:
                        replacements[token] = df
                        used_fields.add(df)
                        break

        if not replacements:
            return expr

        for token, field in sorted(replacements.items(), key=lambda x: -len(x[0])):
            expr = re.sub(rf'\b{re.escape(token)}\b', field, expr)

        return expr

    def find_best_field_match(
        self,
        token: str,
        dataset_fields: list[str],
        used_fields: set[str],
    ) -> str | None:
        """Find best dataset field matching an unknown token."""
        t_lower = token.lower()
        t_tokens = set(t_lower.split('_'))
        scored: list[tuple[int, str]] = []

        for df in dataset_fields:
            if df in used_fields:
                continue
            df_lower = df.lower()
            score = 0
            if t_lower == df_lower:
                score += 100
            if t_lower in df_lower:
                score += 25
            df_tokens = set(df_lower.split('_'))
            common = t_tokens & df_tokens
            score += len(common) * 8
            if score > 0:
                scored.append((score, df))

        if not scored:
            return None

        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    def validate_dataset_fields(self, expr: str, fallback_fields: list[str]) -> str:
        """Replace field-like tokens not present in the active dataset."""
        expr = normalize_operator_aliases(expr)
        if not self._fields:
            return expr

        ds_fields_lower = {f.lower() for f in self._fields}
        fallback_fields = [field for field in fallback_fields if field.lower() in ds_fields_lower]
        if not fallback_fields:
            fallback_fields = sorted(self._fields)
        if not fallback_fields:
            return expr
        tokens = re.findall(r'\b([a-zA-Z_]\w+)\b', expr)
        operators = set(_current_official_operator_names()) | GROUP_KEYS
        field_like = []
        for token in tokens:
            t_lower = token.lower()
            if (
                t_lower not in operators
                and t_lower not in ds_fields_lower
                and not token.isdigit()
                and token not in {'-1', 'nan', 'inf', 'std'}
            ):
                field_like.append(token)

        if not field_like:
            return expr

        field_iter = iter(fallback_fields)
        used: set[str] = set()
        for token in field_like:
            try:
                replacement = next(field_iter)
            except StopIteration:
                replacement = fallback_fields[0]
            if replacement in used:
                continue
            used.add(replacement)
            expr = re.sub(rf'\b{re.escape(token)}\b', replacement, expr)

        return expr

    def resolve_named_field(
        self,
        name: str,
        field_categories: list[FieldCategoryDef],
        selected_fields: list[str],
        exclude: set[str] | None = None,
    ) -> str:
        """Resolve a named field placeholder to a concrete BRAIN field."""
        name_lower = name.lower()
        dataset_fields = sorted(self._fields) if self._fields else []
        ds_fields_lower = {f.lower() for f in dataset_fields}
        excluded = exclude or set()

        if name_lower in ds_fields_lower:
            candidate = next(f for f in dataset_fields if f.lower() == name_lower)
            if candidate not in excluded:
                return candidate

        name_tokens = set(name_lower.split('_'))
        scored: list[tuple[int, str]] = []
        for df in dataset_fields:
            df_lower = df.lower()
            score = 0
            if name_lower == df_lower:
                score += 100
            if name_lower in df_lower:
                score += 30
            df_tokens = set(df_lower.split('_'))
            common = name_tokens & df_tokens
            score += len(common) * 10
            if score > 0:
                scored.append((score, df))

        if scored:
            scored.sort(key=lambda x: -x[0])
            for _, field in scored:
                if field not in excluded:
                    return field

        if field_categories:
            for category in field_categories:
                cat_lower = category.category.lower()
                if name_lower in cat_lower or cat_lower in name_lower:
                    cat_tokens = set(cat_lower.split('_'))
                    cat_scored: list[tuple[int, str]] = []
                    for df in dataset_fields:
                        df_lower = df.lower()
                        df_tokens = set(df_lower.split('_'))
                        common = cat_tokens & df_tokens
                        score = len(common) * 5
                        if name_lower in df_lower:
                            score += 20
                        if score > 0:
                            cat_scored.append((score, df))
                    if cat_scored:
                        cat_scored.sort(key=lambda x: -x[0])
                        for _, field in cat_scored:
                            if field not in excluded:
                                return field

        for selected in selected_fields:
            selected_lower = selected.lower()
            if name_lower in selected_lower and selected not in excluded:
                return selected

        if dataset_fields:
            for field in dataset_fields:
                if field not in excluded:
                    return field
            return dataset_fields[0]

        for selected in selected_fields:
            if selected not in excluded:
                return selected
        return selected_fields[0] if selected_fields else "returns"

    def extract_fields(self, expression: str) -> list[str]:
        """Extract active-dataset field names used in an expression."""
        profile = profile_expression(expression)
        fields = self._fields
        if not fields and self._loader:
            try:
                fields = set(generation_field_ids(self._loader.get_fields(self._dataset_id or None)))
            except Exception:
                self._logger.warning(
                    "generator field extraction metadata unavailable for dataset_id=%s",
                    self._dataset_id or "",
                    exc_info=True,
                )
                fields = set()
        if not fields:
            return list(profile.fields)
        tokens = {token.lower() for token in profile.fields}
        return sorted(fields & tokens)

    def extract_operators(self, expression: str) -> list[str]:
        """Extract operator names from an expression."""
        return ordered_operators(normalize_operator_aliases(expression))

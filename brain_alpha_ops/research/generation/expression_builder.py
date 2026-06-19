"""Expression building helpers for HypothesisDrivenGenerator.

These module-level functions are designed to be attached as methods on
``HypothesisDrivenGenerator``.  They receive ``self`` as the first argument
and delegate most work to ``self._expression_support()``.

This file exists solely to keep ``generator.py`` under the 500-line module
size guard while preserving the original logic unchanged.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from brain_alpha_ops.research.fallback_generation import (
    normalize_operator_aliases,
)
from brain_alpha_ops.research.hypothesis_generator_helpers import (
    pick_unused as _pick_unused,
)

if TYPE_CHECKING:
    from brain_alpha_ops.research.hypothesis_library import (
        ExpressionFamily,
        FieldCategoryDef,
    )


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
            expr = expr.replace(
                f"{{field_{placeholder_name}}}", concrete_field
            )
            used_fields.add(concrete_field)
    elif named_matches:
        # No field_categories available — use sequential fields
        for i, placeholder_name in enumerate(named_matches):
            fallback = (
                fields[i]
                if i < len(fields)
                else (fields[0] if fields else "returns")
            )
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
    expr = re.sub(r"\(window\)", f"({window})", expr)

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


def _normalize_wq_expression_shape(
    self, expr: str, window: int | None = None
) -> str:
    return self._expression_support().normalize_wq_expression_shape(
        expr, window
    )


def _operator_available(self, name: str) -> bool:
    return self._expression_support().operator_available(name)


def _normalize_field_function_calls(
    self, expr: str, window: int | None = None
) -> str:
    return self._expression_support().normalize_field_function_calls(
        expr, window
    )


def _rewrite_field_function_node(self, node, window: int | None = None):
    return self._expression_support().rewrite_field_function_node(
        node, window
    )


def _is_field_function_name(self, name: str) -> bool:
    return self._expression_support().is_field_function_name(name)


def _replacement_for_field_function(
    self,
    field_name: str,
    args,
    window: int | None = None,
):
    return self._expression_support().replacement_for_field_function(
        field_name, args, window
    )


def _sanitize_expression(
    self,
    expr: str,
    fields: list[str],
    already_used: set[str] | None = None,
) -> str:
    return self._expression_support().sanitize_expression(
        expr, fields, already_used
    )


def _find_best_field_match(
    self,
    token: str,
    dataset_fields: list[str],
    used_fields: set[str],
) -> str | None:
    return self._expression_support().find_best_field_match(
        token, dataset_fields, used_fields
    )


def _validate_dataset_fields(
    self, expr: str, fallback_fields: list[str]
) -> str:
    return self._expression_support().validate_dataset_fields(
        expr, fallback_fields
    )


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


__all__ = [
    "_build_expression",
    "_normalize_wq_expression_shape",
    "_operator_available",
    "_normalize_field_function_calls",
    "_rewrite_field_function_node",
    "_is_field_function_name",
    "_replacement_for_field_function",
    "_sanitize_expression",
    "_find_best_field_match",
    "_validate_dataset_fields",
    "_resolve_named_field",
]

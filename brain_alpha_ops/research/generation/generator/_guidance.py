"""Guidance configuration methods for ``HypothesisDrivenGenerator``.

These module-level functions handle experience, observability, and knowledge-base
constraint configuration.  They are attached as methods on
``HypothesisDrivenGenerator`` and receive ``self`` as the first argument —
matching the existing ``expression_builder`` pattern.
"""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
)
from brain_alpha_ops.research.hypothesis_generator_helpers import (
    safe_float as _safe_float,
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

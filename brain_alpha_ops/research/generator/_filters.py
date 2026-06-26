"""Field-pool building and expression filtering helpers.

Contains module-level filter functions (``_build_official_field_pool``,
``_expression_forbidden``, ``_is_observability_avoided``,
``_expression_satisfies_strict_preferred_constraints``,
``_official_preferred_fields``) plus the guidance configuration methods
(``set_experience_guidance``, ``set_observability_guidance``,
``set_knowledge_constraints``) which are attached as methods on
:class:`CandidateGenerator` in ``_generator.py``.
"""
from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
    expression_similarity,
    ordered_operators,
    profile_expression,
)
from brain_alpha_ops.research.fallback_generation import (
    is_high_turnover_generation_risk,
)
from brain_alpha_ops.research.field_quality import (
    filter_generation_fields,
    generation_field_ids,
)
from brain_alpha_ops.scoring.local_quality import (
    LocalQualityConfig,
    extract_fields,
    extract_operators,
    local_quality,
    nesting_depth,
)

# Imports of helper functions used by the guidance methods.
from brain_alpha_ops.research.generator._helpers import _safe_float

# Hardcoded logger name — preserves original ``brain_alpha_ops.research.generator``
# identity for test caplog filtering.
logger = logging.getLogger("brain_alpha_ops.research.generator")

FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD = 0.90


# ---------------------------------------------------------------------------
# Field-pool / constraint helpers — attached as methods on CandidateGenerator.
# ---------------------------------------------------------------------------

def _build_official_field_pool(self, dataset_id: str = "") -> list[str]:
    """Build field pool exclusively from official data sources.

    Priority:
      1. OfficialDataLoader (data/official_fields.json)
      2. context_defaults.DEFAULT_FIELDS (lazy-loaded from official JSON)
      3. self._fields (set by update_context with official data)

    Never returns hardcoded field names.
    """
    # Priority 1: OfficialDataLoader
    if self._loader:
        try:
            # Treat empty string as None (all datasets)
            ds_id: str | None = dataset_id if dataset_id else None
            raw_fields = self._loader.get_fields(ds_id if ds_id else None)
            ds_fields = filter_generation_fields(raw_fields)
            if raw_fields and not ds_fields:
                return []
            if ds_fields:
                # Score fields by coverage, pick top N
                # P1-5: Dynamic field pool — larger pools for datasets with more fields
                dl_count = len(ds_fields)
                dynamic_limit = max(30, min(100, int(dl_count * 0.05)))
                pool_size = self._max_field_pool_size
                scored = []
                for f in ds_fields:
                    # userCount / alphaCount from raw JSON (may not be in schema)
                    user_bonus = min(int(getattr(f, 'userCount', 0) or 0), 50) * 0.01
                    alpha_bonus = min(int(getattr(f, 'alphaCount', 0) or 0), 20) * 0.005
                    coverage = float(getattr(f, 'coverage', 0.0) or 0.0)
                    scored.append((coverage * (1.0 + user_bonus + alpha_bonus), f.id))
                scored.sort(reverse=True)
                # P1-5: Use dynamic pool size — respects max_field_pool_size as upper bound
                effective_limit = min(pool_size, dynamic_limit) if pool_size > 0 else dynamic_limit
                return [fid for _, fid in scored[:effective_limit]]
        except Exception:
            logger.warning(
                "OfficialDataLoader field pool failed for dataset %s", dataset_id, exc_info=True)

    # Priority 2: context_defaults (lazy-loaded from official JSON files)
    try:
        from brain_alpha_ops.brain_api.context_defaults import get_default_fields
        default_fields = get_default_fields()
        if default_fields:
            return generation_field_ids(default_fields)
    except Exception:
        logger.warning("context default fields unavailable; using in-memory field fallback", exc_info=True)

    # Priority 3: self._fields (set by update_context with official API data)
    if self._fields:
        return sorted(generation_field_ids(self._fields))

    return []


def _official_preferred_fields(self, fields: list[str]) -> list[str]:
    if not fields:
        return []
    official_fields = {str(field).lower() for field in self._fields if str(field)}
    if not official_fields:
        official_fields = {
            str(field).lower()
            for field in self._build_official_field_pool(self._dataset_id)
            if str(field)
        }
    return [field for field in fields if field in official_fields]


# ---------------------------------------------------------------------------
# Guidance configuration — attached as methods on CandidateGenerator.
# ---------------------------------------------------------------------------

def set_experience_guidance(self, patterns: dict) -> None:
    """Apply winning alpha patterns to bias future generation.

    Called by pipeline every N cycles with output from get_winning_patterns().
    Patterns include: top_operators, preferred_windows, field_combinations.
    """
    if not patterns or patterns.get("sample_size", 0) < 3:
        return
    self._experience_operators = patterns.get("top_operators", [])
    self._experience_windows = [int(w) for w in patterns.get("preferred_windows", []) if w]
    # Flatten field combinations
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
    """Bias generation toward structured KB rules and away from failures."""
    constraints = dict(constraints or {})
    requested_fields = [str(item).lower() for item in constraints.get("preferred_fields") or [] if str(item)]
    preferred_fields = self._official_preferred_fields(requested_fields)
    preferred_operators = [
        str(item).lower()
        for item in constraints.get("preferred_operators") or []
        if str(item) and str(item).lower() in self._official_operators
    ]
    forbidden_patterns = [str(item).strip() for item in constraints.get("forbidden_patterns") or [] if str(item)]
    strict_preferred_fields = bool(constraints.get("strict_preferred_fields"))
    strict_preferred_operators = bool(constraints.get("strict_preferred_operators"))
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


# ---------------------------------------------------------------------------
# Expression filter checks — attached as methods on CandidateGenerator.
# ---------------------------------------------------------------------------

def _expression_satisfies_strict_preferred_constraints(self, expression: str) -> bool:
    """Apply strict KB constraints to generated expressions after mutation."""
    if self._knowledge_constraints.get("strict_preferred_fields"):
        allowed_fields = {str(field).lower() for field in self._knowledge_constraints.get("preferred_fields") or []}
        expression_fields = {str(field).lower() for field in profile_expression(expression).fields}
        groups = {"market", "sector", "industry", "subindustry"}
        expression_fields -= groups
        if not expression_fields or not expression_fields <= allowed_fields:
            return False
    if self._knowledge_constraints.get("strict_preferred_operators"):
        allowed_operators = {
            str(operator).lower()
            for operator in self._knowledge_constraints.get("preferred_operators") or []
        }
        if not allowed_operators:
            return False
        if {operator.lower() for operator in ordered_operators(expression)} - allowed_operators:
            return False
    return True


def _is_observability_avoided(self, expression: str) -> bool:
    if not self._observability_avoid_keys:
        return False
    markers = {
        str(expression or "").strip(),
        expression_key(expression),
        expression_fingerprint(expression),
    }
    return bool(markers & self._observability_avoid_keys)


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
            if expression_similarity(expression_text, pattern_text) >= FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD:
                return True
        except Exception:
            logger.debug("failed to compare forbidden expression pattern", exc_info=True)
    return False

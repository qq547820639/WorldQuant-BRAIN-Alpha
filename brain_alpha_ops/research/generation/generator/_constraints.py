"""Expression constraint and helper methods for ``HypothesisDrivenGenerator``.

These module-level functions are designed to be attached as methods on
``HypothesisDrivenGenerator``.  They receive ``self`` as the first argument
and access state via ``self.`` — matching the existing ``expression_builder``
pattern.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.expression_ast import (
    expression_fingerprint,
    expression_key,
    expression_similarity,
    profile_expression,
)
from brain_alpha_ops.research.fallback_generation import (
    is_generated_duplicate,
    is_high_turnover_generation_risk,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD = 0.90


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
    except Exception as exc:
        current_key = ""
        current_fingerprint = ""
    for pattern in (
        self._knowledge_constraints.get("forbidden_patterns") or []
    ):
        pattern_text = str(pattern or "").strip()
        if not pattern_text:
            continue
        needle = pattern_text.lower()
        if needle and needle in expression_lower:
            return True
        if pattern_text in {
            expression_text,
            current_key,
            current_fingerprint,
        }:
            return True
        try:
            pattern_key = expression_key(pattern_text)
            pattern_fingerprint = expression_fingerprint(pattern_text)
        except Exception as exc:
            pattern_key = ""
            pattern_fingerprint = ""
        if current_key and pattern_key and current_key == pattern_key:
            return True
        if (
            current_fingerprint
            and pattern_fingerprint
            and current_fingerprint == pattern_fingerprint
        ):
            return True
        try:
            if (
                expression_similarity(expression_text, pattern_text)
                >= _FORBIDDEN_PATTERN_SIMILARITY_THRESHOLD
            ):
                return True
        except Exception as exc:
            logger.debug(
                "failed to compare forbidden expression pattern",
                exc_info=True,
            )
    return False


def _expression_satisfies_strict_preferred_constraints(
    self, expression: str
) -> bool:
    if not (
        self._knowledge_constraints.get("strict_preferred_fields")
        or self._knowledge_constraints.get(
            "strict_preferred_operators"
        )
    ):
        return True
    profile = profile_expression(expression)
    if not profile.parsed:
        return False
    if self._knowledge_constraints.get("strict_preferred_fields"):
        allowed_fields = {
            str(field).lower()
            for field in self._knowledge_constraints.get(
                "preferred_fields"
            )
            or []
            if str(field)
        }
        if not allowed_fields:
            return False
        expression_fields = {
            str(field).lower()
            for field in profile.fields
            if str(field)
        }
        expression_fields -= {
            "market",
            "sector",
            "industry",
            "subindustry",
        }
        if not expression_fields or not expression_fields <= allowed_fields:
            return False
    if self._knowledge_constraints.get("strict_preferred_operators"):
        allowed_operators = {
            str(operator).lower()
            for operator in self._knowledge_constraints.get(
                "preferred_operators"
            )
            or []
            if str(operator)
        }
        if not allowed_operators:
            return False
        expression_operators = {
            str(operator).lower()
            for operator in profile.operators
            if str(operator)
        }
        if expression_operators - allowed_operators:
            return False
    return True


def _prioritize_knowledge_fields(self, fields: list[str]) -> list[str]:
    preferred = set(
        self._knowledge_constraints.get("preferred_fields") or []
    )
    if not preferred:
        return list(fields)
    front = [field for field in fields if field.lower() in preferred]
    if self._knowledge_constraints.get("strict_preferred_fields"):
        return front
    rest = [
        field for field in fields if field.lower() not in preferred
    ]
    return front + rest


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
            candidate.template_source = (
                f"{candidate.template_source}:observability"
            )
        return
    if isinstance(meta, dict):
        meta["observability_diversified"] = True
        candidate.template_source = json.dumps(
            meta, ensure_ascii=False
        )

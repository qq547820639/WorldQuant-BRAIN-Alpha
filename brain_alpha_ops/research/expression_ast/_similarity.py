"""Expression similarity check helpers.

Re-exported via ``brain_alpha_ops.research.expression_ast``.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from brain_alpha_ops.research.expression_ast._profile import (
    profile_expression,
)
from brain_alpha_ops.research.expression_ast._types import (
    ExpressionProfile,
)


def expression_similarity(left: str, right: str) -> float:
    left_profile = profile_expression(left)
    right_profile = profile_expression(right)
    if not left_profile.canonical or not right_profile.canonical:
        return 0.0
    if left_profile.fingerprint == right_profile.fingerprint:
        return 1.0

    seq = SequenceMatcher(None, left_profile.canonical, right_profile.canonical).ratio()
    token_jaccard = _jaccard(_semantic_tokens(left_profile), _semantic_tokens(right_profile))
    if left_profile.parsed and right_profile.parsed and left_profile.canonical != right_profile.canonical:
        token_jaccard = min(token_jaccard, 0.999)
    operator_jaccard = _jaccard(
        {f"op:{item}" for item in left_profile.operators},
        {f"op:{item}" for item in right_profile.operators},
    )
    field_jaccard = _jaccard(
        {f"field:{item}" for item in left_profile.fields},
        {f"field:{item}" for item in right_profile.fields},
    )
    score = max(seq, token_jaccard, 0.6 * operator_jaccard + 0.4 * field_jaccard)
    if left_profile.parsed and right_profile.parsed and left_profile.canonical != right_profile.canonical:
        score = min(score, 0.999)
    return round(score, 4)


def canonical_tokens(expression: str) -> set[str]:
    return _semantic_tokens(profile_expression(expression))


def _semantic_tokens(profile: ExpressionProfile) -> set[str]:
    tokens = {f"op:{item}" for item in profile.operators}
    tokens.update(f"field:{item}" for item in profile.fields)
    tokens.update(f"w:{_window_bucket(item)}" for item in profile.windows)
    if profile.parsed:
        tokens.add(f"depth:{profile.max_depth}")
    return tokens


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _window_bucket(value: int) -> str:
    if value <= 7:
        return "short"
    if value <= 30:
        return "medium"
    return "long"

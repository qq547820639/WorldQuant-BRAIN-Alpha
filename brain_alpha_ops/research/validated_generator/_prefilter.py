"""Quality pre-filter heuristics for candidate expressions.

Provides ``prefilter_quality`` (expression-level quality gate) and
``_passes_diversity`` (Jaccard/MinHash diversity constraint).
"""
from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    expression_similarity,
    profile_expression,
)

from ._signatures import get_active_safe_fields
from ._validate import _tokenize, _minhash_top_k

logger = logging.getLogger("brain_alpha_ops.research.validated_generator")


# ═══════════════════════════════════════════════════════════════════
# Quality pre-filter — expression-level heuristics before BRAIN submission
# ═══════════════════════════════════════════════════════════════════

CROSS_SECTIONAL_OPS: set[str] = {"rank", "zscore", "scale", "group_rank", "group_zscore", "group_neutralize"}
KNOWN_TOXIC_OPS: set[str] = {"ts_cov"}  # BRAIN rejects these regardless
RETURN_TRANSFORM_OPS: set[str] = {"ts_delta", "ts_rank", "ts_zscore", "ts_mean", "ts_decay_linear"}


def prefilter_quality(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove expressions unlikely to pass BRAIN quality gates.

    Heuristics (conservative — prefer false-negatives to wasted BRAIN slots):
      1. Must have a cross_sectional operator
      2. Must have >= 2 operators
      3. Reject known-toxic operators
      4. Must have reasonable nesting depth (>= 2)
      5. Skip bare price-level expressions without return transform
      6. Single returns field + short window → high turnover dilutes fitness
      7. Ultra-short window (<= 3) → guaranteed high turnover
    """
    passed: list[dict[str, Any]] = []
    for c in candidates:
        expr = c.get("expression", "")
        profile = profile_expression(expr)

        # 1. Cross-sectional operator required
        tokens = set(profile.operators)
        if not (tokens & CROSS_SECTIONAL_OPS):
            continue

        # 2. Minimum operator count
        if len(tokens) < 2:
            continue

        # 3. No toxic operators
        if tokens & KNOWN_TOXIC_OPS:
            continue

        # 4. Must have nesting (at least one paren depth >= 2)
        max_depth = max(0, profile.max_depth - 1) if profile.parsed else profile.max_depth
        if max_depth < 2:
            continue

        # 5. No bare price levels without return transform
        price_fields = {"close", "open", "high", "low"}
        used_field_set = set(profile.fields)
        has_price = bool(price_fields & used_field_set)
        has_return_transform = bool(tokens & RETURN_TRANSFORM_OPS or "delta" in expr)
        if has_price and not has_return_transform:
            continue

        # 6. Single returns field + short window → high turnover risk
        active_sf = get_active_safe_fields()
        used_fields = used_field_set & active_sf
        windows = list(profile.windows)
        min_window = min(windows) if windows else 999
        if used_fields == {"returns"} and min_window <= 7:
            continue

        # 7. Ultra-short windows → guaranteed high turnover
        if min_window <= 3:
            continue

        passed.append(c)

    return passed


def _passes_diversity(
    new_expr: str,
    existing: list[dict[str, Any]],
    threshold: float,
) -> bool:
    """Check that *new_expr* is sufficiently different from all existing candidates.

    Uses Jaccard similarity on operator+field token sets with MinHash
    pre-filter for large candidate sets (n >= 20). Returns False if
    any existing candidate exceeds *threshold*.
    """
    if not existing or threshold >= 1.0:
        return True

    new_tokens = set(_tokenize(new_expr))
    if not new_tokens:
        return True

    # MinHash pre-filter for n >= 20: reduce O(n²) to O(n × k) where k << n
    candidates = list(existing)
    if len(candidates) >= 20:
        candidates = _minhash_top_k(new_tokens, candidates, k=10, threshold=threshold)
        if not candidates:
            return True

    for c in candidates:
        existing_expr = str(c.get("expression", ""))
        if expression_similarity(new_expr, existing_expr) > threshold:
            return False
        existing_tokens = set(_tokenize(existing_expr))
        if not existing_tokens:
            continue
        intersection = len(new_tokens & existing_tokens)
        union = len(new_tokens | existing_tokens)
        jaccard = intersection / union if union > 0 else 0
        if jaccard > threshold:
            return False

    return True

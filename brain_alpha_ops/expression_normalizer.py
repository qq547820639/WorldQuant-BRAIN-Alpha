"""Expression normalization utilities for FASTEXPR expressions.

Provides canonical form generation, deduplication detection, and AST-based
similarity scoring. Integrates with the generator and anti-overfit modules
to prevent duplicate/similar expression submissions.

Uses the existing expression_ast parser from the research module for AST
parsing and canonicalization.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    ExpressionParseError,
    ExprNode,
    expression_profile_summary,
    parse_expression,
    profile_expression,
)


@dataclass(frozen=True)
class NormalizedExpression:
    """Result of normalizing an expression."""
    original: str
    canonical: str
    fingerprint: str
    operators: tuple[str, ...]
    fields: tuple[str, ...]
    parse_error: str = ""


def normalize_expression(expression: str) -> NormalizedExpression:
    """Normalize an expression to canonical form.

    Canonical form ensures that equivalent expressions (differing only
    in whitespace, operator ordering, or constant formatting) produce
    the same canonical string.
    """
    profile = profile_expression(expression)
    return NormalizedExpression(
        original=expression,
        canonical=profile.canonical,
        fingerprint=profile.fingerprint,
        operators=profile.operators,
        fields=profile.fields,
        parse_error=profile.parse_error,
    )


def dedup_check(
    expressions: list[str],
) -> list[tuple[int, str, list[int]]]:
    """Detect duplicate expressions by fingerprint.

    Args:
        expressions: List of expression strings.

    Returns:
        List of (index, canonical, duplicate_indices) tuples.
        Each entry represents the first occurrence of a duplicate group.
    """
    fingerprint_map: dict[str, list[int]] = {}
    for i, expr in enumerate(expressions):
        norm = normalize_expression(expr)
        fp = norm.fingerprint
        if fp not in fingerprint_map:
            fingerprint_map[fp] = []
        fingerprint_map[fp].append(i)

    duplicates = []
    for fp, indices in fingerprint_map.items():
        if len(indices) > 1:
            norm = normalize_expression(expressions[indices[0]])
            duplicates.append((indices[0], norm.canonical, indices[1:]))
    return duplicates


def ast_edit_distance(expr_a: str, expr_b: str) -> float:
    """Compute AST-based edit distance between two expressions.

    Returns a similarity score in [0, 1] where:
      1.0 = identical expressions
      0.0 = completely different

    The algorithm computes tree edit distance by comparing node kinds,
    values, and subtree structure.
    """
    norm_a = normalize_expression(expr_a)
    norm_b = normalize_expression(expr_b)

    if norm_a.fingerprint == norm_b.fingerprint:
        return 1.0

    if norm_a.parse_error and norm_b.parse_error:
        return _string_similarity(norm_a.original, norm_b.original)

    if norm_a.parse_error or norm_b.parse_error:
        return _string_similarity(norm_a.original, norm_b.original)

    try:
        tree_a = parse_expression(expr_a)
        tree_b = parse_expression(expr_b)
    except ExpressionParseError:
        return _string_similarity(norm_a.original, norm_b.original)

    distance = _tree_edit_distance(tree_a, tree_b)
    max_nodes = max(_node_count(tree_a), _node_count(tree_b), 1)
    return 1.0 - (distance / max_nodes)


def similarity_score(expr_a: str, expr_b: str) -> float:
    """Public API: return AST-based similarity in [0, 1]."""
    return ast_edit_distance(expr_a, expr_b)


def are_duplicates(
    expr_a: str,
    expr_b: str,
    threshold: float = 0.95,
) -> bool:
    """Check if two expressions are duplicates above a similarity threshold."""
    return similarity_score(expr_a, expr_b) >= threshold


def find_similar_groups(
    expressions: list[str],
    threshold: float = 0.90,
) -> list[list[int]]:
    """Group expressions that are pairwise similar above threshold.

    Returns list of groups, each group is a list of indices into the input.
    """
    n = len(expressions)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) != find(j):
                score = similarity_score(expressions[i], expressions[j])
                if score >= threshold:
                    union(i, j)

    groups_map: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        groups_map.setdefault(root, []).append(i)

    return [g for g in groups_map.values() if len(g) > 1]


# ── Internal helpers ──

def _node_count(node: ExprNode, limit: int = 512) -> int:
    count = 1
    for child in node.children:
        count += _node_count(child, limit - count)
        if count >= limit:
            break
    return count


def _tree_edit_distance(a: ExprNode, b: ExprNode, limit: int = 512) -> int:
    """Compute bottom-up tree edit distance (insert/delete/rename).

    Uses a simplified algorithm suitable for expression trees of
    moderate depth (≤ 64 levels, ≤ 512 nodes).
    """
    if a.kind != b.kind or a.value != b.value:
        base_cost = 1
    else:
        base_cost = 0

    if not a.children and not b.children:
        return base_cost

    if not a.children:
        return base_cost + sum(_node_count(c) for c in b.children)
    if not b.children:
        return base_cost + sum(_node_count(c) for c in a.children)

    children_a = list(a.children)
    children_b = list(b.children)

    m, n = len(children_a), len(children_b)
    if m > limit or n > limit:
        return abs(m - n) + base_cost

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = sum(_node_count(children_a[k]) for k in range(i))
    for j in range(n + 1):
        dp[0][j] = sum(_node_count(children_b[k]) for k in range(j))

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = _tree_edit_distance(children_a[i - 1], children_b[j - 1], limit)
            dp[i][j] = min(
                dp[i - 1][j] + _node_count(children_a[i - 1]),
                dp[i][j - 1] + _node_count(children_b[j - 1]),
                dp[i - 1][j - 1] + cost,
            )

    return base_cost + dp[m][n]


def _string_similarity(a: str, b: str) -> float:
    """Fallback string similarity using normalized character overlap."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)

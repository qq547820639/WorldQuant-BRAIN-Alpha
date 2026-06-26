"""Expression validation and candidate generation.

Contains the core ``validate_expression`` plus the ``generate_validated_candidates``
generator and supporting MinHash/tokenize helpers.
"""
from __future__ import annotations

import logging
import random
import re
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    canonical_tokens,
    expression_similarity,
)

from ._signatures import (
    OPERATOR_SIGNATURES,
    WINDOW_CONSTRAINTS,
    TEMPLATES,
    FIELD_PAIRINGS,
    WINDOW_POOL,
    SHORT_WINDOWS,
    MEDIUM_WINDOWS,
    LONG_WINDOWS,
    get_active_safe_fields,
    get_active_field_pools,
)

logger = logging.getLogger("brain_alpha_ops.research.validated_generator")


# ═══════════════════════════════════════════════════════════════════
# Core: validate_expression()
# ═══════════════════════════════════════════════════════════════════

def validate_expression(expression: str) -> dict[str, Any]:
    """Pre-validate expression before submission. Catches all 3 failure classes.

    Returns:
        {"valid": bool, "errors": [str], "warnings": [str]}
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── 1. Field whitelist check ──
    tokens = set(re.findall(r'\b([a-zA-Z_]\w*)\b', expression))
    known_ops = set(OPERATOR_SIGNATURES.keys())
    reserved = {"if", "else", "and", "or", "not", "true", "false", "none"}

    candidate_fields = tokens - known_ops - reserved
    safe_fields = get_active_safe_fields()
    unknown_fields = sorted(
        t for t in candidate_fields
        if not t.isdigit() and t not in safe_fields
    )
    if unknown_fields:
        errors.append(f"Unknown fields: {', '.join(unknown_fields)}")

    # ── 2. Operator signature check (handles nested calls) ──
    # Find all function-like tokens and extract their args via bracket counting
    tokens = list(re.finditer(r'\b([a-zA-Z_]\w*)\s*\(', expression))
    for match in tokens:
        op = match.group(1)
        if op not in OPERATOR_SIGNATURES:
            warnings.append(f"Unknown operator '{op}' — expression may fail BRAIN validation")
            continue
        sig = OPERATOR_SIGNATURES[op]
        # Extract arguments by counting parentheses from the opening bracket
        start = match.end() - 1  # position of '('
        args_str = _extract_bracketed(expression, start)
        if args_str is None:
            errors.append(f"{op}(): unmatched parentheses")
            continue
        args = _split_args(args_str)
        expected_count = len(sig["params"])

        if len(args) != expected_count:
            errors.append(f"{op}() expects {expected_count} args, got {len(args)}")
            continue

        # Check d-params are integers
        for i, param_type in enumerate(sig["params"]):
            if param_type == "d":
                arg = args[i].strip()
                if not arg.isdigit():
                    errors.append(
                        f"{op}() param '{sig['params'][i]}' must be integer, got '{arg}'"
                    )
                else:
                    window = int(arg)
                    constraints = WINDOW_CONSTRAINTS.get(op, {})
                    wmin = constraints.get("min", 1)
                    wmax = constraints.get("max", 999)
                    if window < wmin or window > wmax:
                        warnings.append(
                            f"{op}() window {window} outside typical range [{wmin}, {wmax}]"
                        )

    # ── 3. Parentheses balance ──
    depth = 0
    for ch in expression:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if depth < 0:
            errors.append("Unbalanced parentheses: extra ')'")
            break
    if depth > 0:
        errors.append("Unbalanced parentheses: unclosed '('")

    # ── 4. Autocorrelation risk heuristic ──
    slow_ops = {"ts_mean", "ts_sum", "ts_decay_linear", "ts_corr", "ts_cov"}
    fast_ops = {"ts_delta", "sign"}
    has_slow = any(op in expression for op in slow_ops)
    has_fast = any(op in expression for op in fast_ops)
    if has_slow and not has_fast:
        windows = [int(w) for w in re.findall(r',\s*(\d+)\)', expression)]
        long_windows = [w for w in windows if w >= 60]
        if long_windows:
            warnings.append(
                f"High autocorrelation risk: slow operators with long windows "
                f"{long_windows} and no differencing"
            )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def _extract_bracketed(s: str, start: int) -> str | None:
    """Extract content between matching parentheses starting at *start* (position of '(')."""
    if start >= len(s) or s[start] != '(':
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == '(':
            depth += 1
        elif s[i] == ')':
            depth -= 1
            if depth == 0:
                return s[start + 1:i]
    return None  # unmatched


def _split_args(args_str: str) -> list[str]:
    """Split function arguments respecting nested parentheses."""
    args: list[str] = []
    depth = 0
    current = ""
    for ch in args_str:
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            args.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        args.append(current.strip())
    return args


# ═══════════════════════════════════════════════════════════════════
# Generator: produce validated candidates
# ═══════════════════════════════════════════════════════════════════

def generate_validated_candidates(
    themes: list[str] | None = None,
    count: int = 10,
    max_attempts: int = 50,
    *,
    diversity_threshold: float = 0.40,
    apply_prefilter: bool = True,
) -> list[dict[str, Any]]:
    """Generate candidates that pass validation + diversity + quality pre-filter.

    Args:
        themes: theme names to draw from. Defaults to ALL themes.
        count: desired number of valid candidates.
        max_attempts: maximum generation attempts before giving up.
        diversity_threshold: max Jaccard similarity before rejection.
        apply_prefilter: run prefilter_quality() before returning.

    Returns:
        List of {"expression": str, "theme": str, "warnings": [str]} dicts
    """
    # Lazy imports to avoid circular dependency with _prefilter.
    from ._prefilter import prefilter_quality, _passes_diversity

    if themes is None:
        themes = list(TEMPLATES.keys())

    candidates: list[dict[str, Any]] = []
    attempts = 0
    active_field_pools = get_active_field_pools()
    if not active_field_pools:
        return []

    while len(candidates) < count and attempts < max_attempts:
        attempts += 1

        theme = random.choice(themes)
        theme_templates = TEMPLATES.get(theme, TEMPLATES["momentum"])
        template, slots = random.choice(theme_templates)

        values: dict[str, str] = {}
        # Pick a logical field pairing for 2-field templates
        n_fields = len([s for s in slots if s.startswith("f")])
        pairing = random.choice(FIELD_PAIRINGS) if n_fields >= 2 else None

        for slot in slots:
            if slot.startswith("f"):
                if slot == "f1" and pairing:
                    pool_names = pairing[0]
                elif slot == "f2" and pairing:
                    pool_names = pairing[1]
                elif "2" in slot:
                    pool_names = ["price", "returns"]
                else:
                    pool_names = ["price", "volume", "returns"]

                pool_name = random.choice(pool_names)
                field_pool = active_field_pools.get(pool_name) or next(iter(active_field_pools.values()), [])
                if not field_pool:
                    continue
                values[slot] = random.choice(field_pool)
            elif slot.startswith("d"):
                # P0-8: stratified window selection — short for delta, long for mean/std
                if "delta" in template.lower() and values.get("d1") != slot:
                    values[slot] = str(random.choice(SHORT_WINDOWS))
                elif any(op in template for op in ("ts_mean", "ts_std_dev", "ts_corr")):
                    values[slot] = str(random.choice(MEDIUM_WINDOWS + LONG_WINDOWS))
                else:
                    values[slot] = str(random.choice(WINDOW_POOL))

        expression = template.format(**values)

        # Validate operator signatures + field whitelist
        result = validate_expression(expression)
        if not result["valid"]:
            continue

        # P0-8: Jaccard diversity constraint — prevent near-duplicate expressions
        if not _passes_diversity(expression, candidates, diversity_threshold):
            continue

        candidates.append({
            "expression": expression,
            "theme": theme,
            "warnings": result.get("warnings", []),
        })

    if apply_prefilter and candidates:
        candidates = prefilter_quality(candidates)

    return candidates


def _minhash_top_k(
    new_tokens: set[str],
    existing: list[dict[str, Any]],
    k: int = 10,
    threshold: float = 0.40,
) -> list[dict[str, Any]]:
    """MinHash pre-filter: return top-k candidates by estimated Jaccard similarity.

    Uses 64 hash functions for stable estimation. For n >= 20 candidates,
    this reduces the O(n²) pairwise comparison to O(n × k) where k << n.
    """
    n_hashes = 64
    existing_sigs: list[list[int]] = []
    for c in existing:
        tokens = set(_tokenize(str(c.get("expression", ""))))
        existing_sigs.append(_minhash_signature(tokens, n_hashes))
    new_sig = _minhash_signature(new_tokens, n_hashes)

    estimates: list[tuple[int, float]] = []
    for i, sig in enumerate(existing_sigs):
        matches = sum(1 for a, b in zip(new_sig, sig) if a == b)
        est = matches / n_hashes
        if est > threshold * 0.5:  # loose pre-filter
            estimates.append((i, est))
    estimates.sort(key=lambda x: -x[1])
    return [existing[i] for i, _ in estimates[:k]]


def _minhash_signature(tokens: set[str], n: int = 64) -> list[int]:
    """Compute MinHash signature for a set of tokens."""
    if not tokens:
        return [0] * n
    sig = []
    for i in range(n):
        min_hash = None
        for token in tokens:
            h = hash((i, token)) & 0x7FFFFFFF
            if min_hash is None or h < min_hash:
                min_hash = h
        sig.append(min_hash if min_hash is not None else 0)
    return sig


def _tokenize(expression: str) -> list[str]:
    """Extract normalized tokens (operators + field references) from expression."""
    return sorted(canonical_tokens(expression))

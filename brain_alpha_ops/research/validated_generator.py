"""Expression generator with pre-validation — eliminates 3 main failure classes.

Replaces random field/operator assembly with signature-validated templates.
Target: reduce BRAIN rejection rate from ~39% to ~10%.
"""
from __future__ import annotations

import random
import re
import threading
from typing import Any

from brain_alpha_ops.research.expression_ast import (
    canonical_tokens,
    expression_similarity,
    profile_expression,
)

# ═══════════════════════════════════════════════════════════════════
# P0: Operator signatures — authoritative from BRAIN official docs
# ═══════════════════════════════════════════════════════════════════

OPERATOR_SIGNATURES: dict[str, dict[str, Any]] = {
    # Cross-sectional
    "rank":           {"params": ["x"],   "category": "cross_sectional"},
    "zscore":         {"params": ["x"],   "category": "cross_sectional"},
    "scale":          {"params": ["x"],   "category": "cross_sectional"},
    "group_rank":     {"params": ["x", "sector"], "category": "cross_sectional"},
    "group_zscore":   {"params": ["x", "sector"], "category": "cross_sectional"},
    "group_neutralize":{"params": ["x", "sector"], "category": "cross_sectional"},
    # Transformation / sanitization
    "winsorize":      {"params": ["x", "std"], "category": "transformation"},
    "truncate":       {"params": ["x", "limit"], "category": "transformation"},
    # Time series (2-param)
    "ts_mean":         {"params": ["x", "d"], "category": "time_series"},
    "ts_std_dev":          {"params": ["x", "d"], "category": "time_series"},
    "ts_sum":          {"params": ["x", "d"], "category": "time_series"},
    "ts_delta":        {"params": ["x", "d"], "category": "time_series"},
    "ts_delay":        {"params": ["x", "d"], "category": "time_series"},
    "ts_rank":         {"params": ["x", "d"], "category": "time_series"},"ts_kurtosis":     {"params": ["x", "d"], "category": "time_series"},
    "ts_decay_linear": {"params": ["x", "d"], "category": "time_series"},
    "ts_zscore":       {"params": ["x", "d"], "category": "time_series"},
    # Time series (3-param)
    "ts_corr":  {"params": ["x", "y", "d"], "category": "time_series"},
    "ts_cov":   {"params": ["x", "y", "d"], "category": "time_series"},
    # Vector
    "abs":   {"params": ["x"],    "category": "vector"},
    "sign":  {"params": ["x"],    "category": "vector"},
    "log":   {"params": ["x"],    "category": "vector"},
    "max":   {"params": ["x", "y"], "category": "vector"},
    "min":   {"params": ["x", "y"], "category": "vector"},
}

# Window constraints per operator
WINDOW_CONSTRAINTS: dict[str, dict[str, int]] = {
    "winsorize":       {"min": 1,  "max": 5},
    "truncate":        {"min": 1,  "max": 10},
    "ts_mean":         {"min": 2,  "max": 252},
    "ts_std_dev":          {"min": 5,  "max": 252},
    "ts_sum":          {"min": 2,  "max": 252},
    "ts_delta":        {"min": 1,  "max": 120},
    "ts_delay":        {"min": 1,  "max": 120},
    "ts_rank":         {"min": 5,  "max": 252},
    "ts_corr":         {"min": 10, "max": 252},
    "ts_cov":          {"min": 10, "max": 252},"ts_kurtosis":     {"min": 10, "max": 252},
    "ts_decay_linear": {"min": 2,  "max": 120},
    "ts_zscore":       {"min": 5,  "max": 252},
}

# ═══════════════════════════════════════════════════════════════════
# P0: Field whitelist — loaded from official_fields.json
# ═══════════════════════════════════════════════════════════════════
SAFE_FIELDS: set[str] = set()


# ═══════════════════════════════════════════════════════════════════
# Validated templates — each template verified against operator signatures
# ═══════════════════════════════════════════════════════════════════

# Round 5: expanded from 10 to 55 templates with logical pairings + stratified windows + deep nesting

TEMPLATES: dict[str, list[tuple[str, list[str]]]] = {
    "momentum": [
        ("rank(ts_delta({f1}, {d1}))",                                    ["f1", "d1"]),
        ("rank(ts_delta({f1}, {d1}) / ts_std_dev({f2}, {d2}))",           ["f1", "d1", "f2", "d2"]),
        ("rank(ts_sum({f1}, {d1}))",                                       ["f1", "d1"]),
        ("rank(ts_rank({f1}, {d1}))",                                      ["f1", "d1"]),
        ("rank(ts_mean({f1}, {d1}))",                                      ["f1", "d1"]),
        ("rank(ts_sum(ts_delta({f1}, {d1}), {d2}))",                       ["f1", "d1", "d2"]),
        ("zscore(ts_delta({f1}, {d1}))",                                   ["f1", "d1"]),
        ("rank(ts_decay_linear({f1}, {d1}))",                               ["f1", "d1"]),
    ],
    "reversal": [
        ("-rank(ts_delta({f1}, {d1}))",                                    ["f1", "d1"]),
        ("-rank(ts_sum({f1}, {d1}))",                                       ["f1", "d1"]),
        ("rank(-ts_delta({f1}, {d1}))",                                    ["f1", "d1"]),
        ("-rank(ts_rank({f1}, {d1}))",                                      ["f1", "d1"]),
        ("rank(ts_delay({f1}, {d1}) - {f1})",                               ["f1", "d1"]),
        ("-zscore(ts_delta({f1}, {d1}))",                                   ["f1", "d1"]),
    ],
    "volume_reversal": [
        ("-rank(ts_zscore({f1}, {d1}) * ts_delta({f2}, {d2}))",           ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_delta({f1}, {d1}) * ts_delta({f2}, {d2}))",            ["f1", "d1", "f2", "d2"]),
        ("-rank(ts_delta({f1}, {d1}) * ts_mean({f2}, {d2}))",             ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_sum({f1}, {d1}) / ts_std_dev({f2}, {d2}))",            ["f1", "d1", "f2", "d2"]),
        ("-rank(ts_rank({f1}, {d1}) * zscore(ts_delta({f2}, {d2})))",     ["f1", "d1", "f2", "d2"]),
    ],
    "volatility": [
        ("rank(-ts_std_dev({f1}, {d1}))",                                   ["f1", "d1"]),
        ("-rank(ts_std_dev({f1}, {d1}))",                                   ["f1", "d1"]),
        ("-rank(ts_std_dev({f1}, {d1}) / ts_mean({f2}, {d2}))",            ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_std_dev({f1}, {d1}) * zscore({f1}))",                   ["f1", "d1"]),
        ("rank(ts_zscore({f1}, {d1}) / ts_std_dev({f1}, {d1}))",           ["f1", "d1"]),
    ],
    "mean_reversion": [
        ("-rank(ts_delta({f1}, {d1}) / ts_std_dev({f2}, {d2}))",           ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_delta({f1}, {d1}))",                                    ["f1", "d1"]),
        ("-rank(ts_zscore({f1}, {d1}))",                                     ["f1", "d1"]),
        ("-rank(({f1} - ts_mean({f1}, {d1})) / ts_std_dev({f1}, {d1}))",  ["f1", "d1"]),
        ("-rank(ts_decay_linear(ts_delta({f1}, {d1}), {d2}))",             ["f1", "d1", "d2"]),
    ],
    "value": [
        ("rank({f1})",                                                      ["f1"]),
        ("rank(zscore({f1}))",                                              ["f1"]),
        ("rank(-{f1})",                                                     ["f1"]),
        ("rank(zscore(-{f1}))",                                             ["f1"]),
    ],
    "quality": [
        ("rank(ts_mean({f1}, {d1}))",                                       ["f1", "d1"]),
        ("zscore(ts_mean({f1}, {d1}))",                                     ["f1", "d1"]),
        ("rank(ts_mean({f1}, {d1}) / ts_std_dev({f1}, {d1}))",             ["f1", "d1"]),
        ("rank(zscore(ts_mean({f1}, {d1})))",                                ["f1", "d1"]),
    ],
    "hybrid": [
        ("rank(ts_delta({f1}, {d1})) + rank(ts_delta({f2}, {d2}))",        ["f1", "d1", "f2", "d2"]),
        ("rank(ts_mean({f1}, {d1})) * rank(-ts_std_dev({f2}, {d2}))",      ["f1", "d1", "f2", "d2"]),
        ("rank(zscore({f1})) * rank(ts_delta({f2}, {d1}))",                ["f1", "f2", "d1"]),
        ("-rank(ts_delta({f1}, {d1}) * ts_zscore({f2}, {d2}))",            ["f1", "d1", "f2", "d2"]),
        ("zscore(ts_delta({f1}, {d1})) + zscore(-ts_std_dev({f2}, {d2}))", ["f1", "d1", "f2", "d2"]),
        ("rank(ts_sum({f1}, {d1}) + ts_delta({f2}, {d2}))",                ["f1", "d1", "f2", "d2"]),
    ],
    "deep_nested": [
        ("rank(ts_delta(ts_mean({f1}, {d1}), {d2}))",                       ["f1", "d1", "d2"]),
        ("rank(ts_mean(ts_delta({f1}, {d1}), {d2}))",                        ["f1", "d1", "d2"]),
        ("-rank(ts_std_dev(ts_delta({f1}, {d1}), {d2}))",                   ["f1", "d1", "d2"]),
        ("zscore(ts_delta(ts_mean({f1}, {d1}), {d2}))",                      ["f1", "d1", "d2"]),
        ("rank(ts_zscore(ts_delta({f1}, {d1}), {d2}))",                      ["f1", "d1", "d2"]),
    ],
    # ── P0-8 additions: new strategy families ──
    "growth": [
        ("rank(ts_delta({f1}, {d1}) / ts_mean({f1}, {d1}))",               ["f1", "d1"]),
        ("rank(ts_delta({f1}, {d1}) / ts_std_dev({f1}, {d1}))",            ["f1", "d1"]),
        ("zscore(ts_delta({f1}, {d1}) / ts_mean({f1}, {d2}))",             ["f1", "d1", "d2"]),
        ("rank(ts_decay_linear(ts_delta({f1}, {d1}), {d2}))",               ["f1", "d1", "d2"]),
        ("rank(ts_delta({f1}, {d1}) * ts_delta({f2}, {d2}))",              ["f1", "d1", "f2", "d2"]),
    ],
    "liquidity": [
        ("-rank(ts_delta({f1}, {d1}) / ts_std_dev({f1}, {d2}))",           ["f1", "d1", "d2"]),
        ("rank(-ts_std_dev({f1}, {d1}) * ts_delta({f2}, {d2}))",           ["f1", "d1", "f2", "d2"]),
        ("-rank(ts_rank({f1}, {d1}) * zscore(ts_delta({f2}, {d2})))",      ["f1", "d1", "f2", "d2"]),
        ("rank(-ts_zscore({f1}, {d1}) / ts_mean({f2}, {d2}))",             ["f1", "d1", "f2", "d2"]),
    ],
    "stat_arb": [
        ("rank(ts_corr({f1}, {f2}, {d1}))",                                  ["f1", "f2", "d1"]),
        ("rank(({f1} - ts_mean({f1}, {d1})) / ts_std_dev({f2}, {d1}))",    ["f1", "f2", "d1"]),
        ("rank(zscore({f1}) - ts_mean(zscore({f2}), {d1}))",               ["f1", "f2", "d1"]),
        ("-rank(zscore({f1}) + zscore({f2}))",                               ["f1", "f2"]),
    ],
    "cross_sectional": [
        ("group_rank(ts_delta({f1}, {d1}), {f2})",                          ["f1", "d1", "f2"]),
        ("group_neutralize(zscore({f1}), {f2})",                            ["f1", "f2"]),
        ("group_rank({f1}, {f2})",                                          ["f1", "f2"]),
        ("rank(zscore({f1}) - group_neutralize(zscore({f1}), {f2}))",      ["f1", "f2"]),
    ],
}

# Logical field pool names. Values are injected from official context at runtime.
FIELD_POOLS: dict[str, list[str]] = {
    "price": [],
    "volume": [],
    "returns": [],
    "value": [],
    "momentum": [],
    "volatility": [],
    "fundamental": [],
    "analyst": [],
    "cashflow": [],
    "quality": [],
}

# Logical field pairings for 2-field templates: (pool_for_f1, pool_for_f2)
FIELD_PAIRINGS = [
    (["price", "volume"],        ["returns", "volatility"]),
    (["price", "volatility"],    ["volume", "returns"]),
    (["momentum"],               ["value", "returns"]),
    (["volume", "price"],        ["returns", "momentum"]),
    (["price", "value"],         ["volatility", "returns"]),
    # P0-8 additions — cross-family pairings for diversity
    (["price", "volume"],        ["fundamental", "analyst"]),
    (["fundamental"],            ["returns", "volatility"]),
    (["analyst", "cashflow"],    ["price", "momentum"]),
    (["price", "fundamental"],   ["volume", "quality"]),
    (["fundamental", "analyst"], ["value", "returns"]),
    (["cashflow"],               ["price", "volatility"]),
]

# Stratified window pools — short, medium, long
WINDOW_POOL: list[int] = [1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 60, 90, 120]
SHORT_WINDOWS: list[int] = [1, 2, 3, 5, 7]
MEDIUM_WINDOWS: list[int] = [10, 15, 20, 30]
LONG_WINDOWS: list[int] = [40, 60, 90, 120]


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


# ═══════════════════════════════════════════════════════════════════
# Dynamic safe-fields injection point
# ═══════════════════════════════════════════════════════════════════
# Override SAFE_FIELDS at runtime with live-verified fields from pipeline:
#   from brain_alpha_ops.research.validated_generator import set_active_safe_fields
#   set_active_safe_fields(production_context["safe_fields"])

_ACTIVE_SAFE_FIELDS: set[str] | None = None
_ACTIVE_FIELD_POOLS: dict[str, list[str]] | None = None
_ACTIVE_STATE_LOCK = threading.Lock()


def get_active_safe_fields() -> set[str]:
    """Return the currently active safe-fields set."""
    with _ACTIVE_STATE_LOCK:
        if _ACTIVE_SAFE_FIELDS is not None:
            return set(_ACTIVE_SAFE_FIELDS)
    try:
        from brain_alpha_ops.data import OfficialDataLoader

        return {
            str(getattr(field, "id", "") or getattr(field, "name", "") or "").strip()
            for field in OfficialDataLoader.instance().get_fields()
            if str(getattr(field, "id", "") or getattr(field, "name", "") or "").strip()
        }
    except Exception:
        return set()


def get_active_field_pools() -> dict[str, list[str]]:
    """Return official field pools for generation without static field fallback."""
    with _ACTIVE_STATE_LOCK:
        if _ACTIVE_FIELD_POOLS is not None:
            return {key: list(value) for key, value in _ACTIVE_FIELD_POOLS.items()}
    fields = sorted(get_active_safe_fields())
    if not fields:
        return {}
    return {pool_name: list(fields) for pool_name in FIELD_POOLS}


def set_active_safe_fields(field_ids: list[str], field_pools: dict[str, list[str]] | None = None) -> None:
    """Inject live-verified fields from production context.

    Called by pipeline after authenticating and discovering available fields.
    If never called, local official_fields.json is used; unavailable context
    returns an empty set so validation fails closed.
    """
    global _ACTIVE_SAFE_FIELDS, _ACTIVE_FIELD_POOLS
    with _ACTIVE_STATE_LOCK:
        _ACTIVE_SAFE_FIELDS = set(field_ids)
        if field_pools is not None:
            _ACTIVE_FIELD_POOLS = dict(field_pools)


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

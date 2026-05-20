"""Expression generator with pre-validation — eliminates 3 main failure classes.

Replaces random field/operator assembly with signature-validated templates.
Target: reduce BRAIN rejection rate from ~39% to ~10%.
"""
import re
import random
from typing import Any, Dict, List, Optional, Set, Tuple

from brain_alpha_ops.research.expression_ast import canonical_tokens, expression_similarity, profile_expression


# ═══════════════════════════════════════════════════════════════════
# P0: Operator signatures — authoritative from BRAIN official docs
# ═══════════════════════════════════════════════════════════════════

OPERATOR_SIGNATURES: Dict[str, Dict[str, Any]] = {
    # Cross-sectional
    "rank":    {"params": ["x"],   "category": "cross_sectional"},
    "zscore":  {"params": ["x"],   "category": "cross_sectional"},
    "scale":   {"params": ["x"],   "category": "cross_sectional"},
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
WINDOW_CONSTRAINTS: Dict[str, Dict[str, int]] = {
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
# P0: Field whitelist — verified BRAIN fields from official_fields.json
# ═══════════════════════════════════════════════════════════════════
# All fields verified against data/official_fields.json (7,642 total).
# Every field name exists in BRAIN API — zero custom/fictional fields.

SAFE_FIELDS: Set[str] = {
    # ── Price & Volume (pv1, coverage 1.0) ──
    "close", "open", "high", "low",
    "volume", "returns",
    "vwap", "adv20",
    # ── Fundamental (fundamental6, coverage ≥ 0.5) ──
    "assets", "revenue", "eps", "operating_income",
    "enterprise_value",
    # ── Analyst Estimates (analyst4, MATRIX type only) ──
    "anl4_ebit_value", "anl4_ebitda_value",
    # ── Cash Flow (analyst4) ──
    "anl4_cfo_value", "anl4_cfi_value", "anl4_fcf_value",
    # ── Revisions (analyst4) ──
    "anl4_epsr_value", "anl4_epsr_mean",
}


# ═══════════════════════════════════════════════════════════════════
# Validated templates — each template verified against operator signatures
# ═══════════════════════════════════════════════════════════════════

# Round 5: expanded from 10 to 55 templates with logical pairings + stratified windows + deep nesting

TEMPLATES: Dict[str, List[Tuple[str, List[str]]]] = {
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
        ("group_rank(ts_delta({f1}, {d1}), sector)",                        ["f1", "d1"]),
        ("group_neutralize(zscore({f1}), sector)",                          ["f1"]),
        ("group_rank({f1}, subindustry)",                                    ["f1"]),
        ("rank(zscore({f1}) - group_neutralize(zscore({f1}), sector))",    ["f1"]),
    ],
}

# Expanded field pools with logical groupings — verified BRAIN field IDs
FIELD_POOLS: Dict[str, List[str]] = {
    "price":       ["close", "open", "vwap", "high", "low"],
    "volume":      ["volume", "adv20"],
    "returns":     ["returns"],
    "value":       ["enterprise_value"],
    "momentum":    ["close", "vwap", "returns"],
    "volatility":  ["close", "returns", "vwap"],
    "fundamental": ["revenue", "eps", "operating_income", "assets"],
    "analyst":     ["anl4_ebit_value", "anl4_ebitda_value"],
    "cashflow":    ["anl4_cfo_value", "anl4_fcf_value"],
    "quality":     ["anl4_epsr_value", "anl4_epsr_mean"],
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
WINDOW_POOL: List[int] = [1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 60, 90, 120]
SHORT_WINDOWS: List[int] = [1, 2, 3, 5, 7]
MEDIUM_WINDOWS: List[int] = [10, 15, 20, 30]
LONG_WINDOWS: List[int] = [40, 60, 90, 120]


# ═══════════════════════════════════════════════════════════════════
# Core: validate_expression()
# ═══════════════════════════════════════════════════════════════════

def validate_expression(expression: str) -> Dict[str, Any]:
    """Pre-validate expression before submission. Catches all 3 failure classes.

    Returns:
        {"valid": bool, "errors": [str], "warnings": [str]}
    """
    errors: List[str] = []
    warnings: List[str] = []

    # ── 1. Field whitelist check ──
    tokens = set(re.findall(r'\b([a-zA-Z_]\w*)\b', expression))
    known_ops = set(OPERATOR_SIGNATURES.keys())
    reserved = {"if", "else", "and", "or", "not", "true", "false", "none"}

    candidate_fields = tokens - known_ops - reserved
    unknown_fields = sorted(
        t for t in candidate_fields
        if not t.isdigit() and t not in SAFE_FIELDS
    )
    if unknown_fields:
        errors.append(f"Unknown fields: {', '.join(unknown_fields)}")

    # ── 2. Operator signature check (handles nested calls) ──
    # Find all function-like tokens and extract their args via bracket counting
    tokens = list(re.finditer(r'\b([a-zA-Z_]\w*)\s*\(', expression))
    for match in tokens:
        op = match.group(1)
        if op not in OPERATOR_SIGNATURES:
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


def _split_args(args_str: str) -> List[str]:
    """Split function arguments respecting nested parentheses."""
    args: List[str] = []
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
    themes: Optional[List[str]] = None,
    count: int = 10,
    max_attempts: int = 50,
    *,
    diversity_threshold: float = 0.40,
    apply_prefilter: bool = True,
) -> List[Dict[str, Any]]:
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

    candidates: List[Dict[str, Any]] = []
    attempts = 0

    while len(candidates) < count and attempts < max_attempts:
        attempts += 1

        theme = random.choice(themes)
        theme_templates = TEMPLATES.get(theme, TEMPLATES["momentum"])
        template, slots = random.choice(theme_templates)

        values: Dict[str, str] = {}
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
                field_pool = FIELD_POOLS.get(pool_name, FIELD_POOLS["price"])
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
    existing: List[Dict[str, Any]],
    threshold: float,
) -> bool:
    """Check that *new_expr* is sufficiently different from all existing candidates.

    Uses Jaccard similarity on operator+field token sets. Returns False if
    any existing candidate exceeds *threshold*.
    """
    if not existing or threshold >= 1.0:
        return True

    new_tokens = set(_tokenize(new_expr))
    if not new_tokens:
        return True

    for c in existing:
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


def _tokenize(expression: str) -> List[str]:
    """Extract normalized tokens (operators + field references) from expression."""
    return sorted(canonical_tokens(expression))


# ═══════════════════════════════════════════════════════════════════
# Dynamic safe-fields injection point
# ═══════════════════════════════════════════════════════════════════
# Override SAFE_FIELDS at runtime with live-verified fields from pipeline:
#   from brain_alpha_ops.research.validated_generator import set_active_safe_fields
#   set_active_safe_fields(production_context["safe_fields"])

_ACTIVE_SAFE_FIELDS: Set[str] | None = None  # None = use static SAFE_FIELDS
_ACTIVE_FIELD_POOLS: Dict[str, List[str]] | None = None


def get_active_safe_fields() -> Set[str]:
    """Return the currently active safe-fields set."""
    return _ACTIVE_SAFE_FIELDS if _ACTIVE_SAFE_FIELDS is not None else SAFE_FIELDS


def set_active_safe_fields(field_ids: List[str], field_pools: Dict[str, List[str]] | None = None) -> None:
    """Inject live-verified fields from production context.

    Called by pipeline after authenticating and discovering available fields.
    Falls back to static SAFE_FIELDS if never called.
    """
    global _ACTIVE_SAFE_FIELDS, _ACTIVE_FIELD_POOLS
    _ACTIVE_SAFE_FIELDS = set(field_ids)
    if field_pools is not None:
        _ACTIVE_FIELD_POOLS = dict(field_pools)


# ═══════════════════════════════════════════════════════════════════
# Quality pre-filter — expression-level heuristics before BRAIN submission
# ═══════════════════════════════════════════════════════════════════

CROSS_SECTIONAL_OPS: Set[str] = {"rank", "zscore", "scale", "group_rank", "group_zscore", "group_neutralize"}
KNOWN_TOXIC_OPS: Set[str] = {"ts_cov"}  # BRAIN rejects these regardless
RETURN_TRANSFORM_OPS: Set[str] = {"ts_delta", "ts_rank", "ts_zscore", "ts_mean", "ts_decay_linear"}


def prefilter_quality(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
    passed: List[Dict[str, Any]] = []
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

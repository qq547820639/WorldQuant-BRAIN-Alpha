"""Helper utilities extracted from hypothesis_driven_generator.py.

This module is a P1-3 refactor outcome.  It collects small pure-function
utilities that previously inflated the god-module (1325 lines) without
contributing to the generator's primary responsibility.

The functions here were previously defined as module-private helpers in
``hypothesis_driven_generator.py``.  They are now re-exported from this
module to keep the main file focused on the 5 selector classes plus the
``HypothesisDrivenGenerator`` orchestrator.

Note: ``stop_tokens`` and ``token_aliases`` are kept as module-level
constants here, mirroring the original values verbatim.  Tests of
``FieldSelector`` rely on the exact match behaviour.
"""

from __future__ import annotations

import re
from typing import Any

# Stop-tokens excluded from semantic field matching.
# (Mirrors the original _SEMANTIC_STOP_TOKENS in hypothesis_driven_generator.py.)
SEMANTIC_STOP_TOKENS: frozenset[str] = frozenset(
    {
        "and",
        "change",
        "count",
        "history",
        "historical",
        "long",
        "ratio",
        "short",
        "term",
        "the",
        "to",
    }
)

# Aliases that broaden a single semantic token to related concepts.
# (Mirrors the original _SEMANTIC_TOKEN_ALIASES in hypothesis_driven_generator.py.)
SEMANTIC_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "accruals": ("accrual",),
    "analyst": ("anl4",),
    "beta": ("beta",),
    "cash": ("cash", "cfo", "cff", "cfi"),
    "consensus": ("consensus", "mean", "median"),
    "coverage": ("numest", "number", "num"),
    "dispersion": ("dispersion", "std", "stddev", "high", "low"),
    "dividend": ("div", "dividend"),
    "earnings": ("eps", "earnings", "income", "netincome", "net_income"),
    "estimate": ("estimate", "est", "mean", "median"),
    "float": ("float", "shares"),
    "growth": ("growth", "sales", "revenue"),
    "margin": ("margin", "gross", "operating"),
    "price": ("price", "value"),
    "profitability": ("profit", "income", "roe", "roa"),
    "rating": ("rating", "rec"),
    "recommendation": ("rec", "rating"),
    "revenue": ("sales", "revenue"),
    "revision": (
        "revision",
        "revisions",
        "previosestimate",
        "previous",
        "preest",
        "chg",
        "change",
    ),
    "sales": ("sales", "revenue"),
    "surprise": ("surprise", "actual"),
    "target": ("target", "tp"),
}


def semantic_field_tokens(category_name: str, examples: list[str]) -> dict[str, float]:
    """Return a token→weight map for a category and its example fields.

    Weights: ``2.0`` for category tokens, ``3.0`` for example tokens; aliases
    add a small bonus.  Maximum weight wins on collision.
    """
    tokens: dict[str, float] = {}
    for token in split_semantic_tokens(category_name):
        add_semantic_token(tokens, token, 2.0)
        for alias in SEMANTIC_TOKEN_ALIASES.get(token, ()):
            add_semantic_token(tokens, alias, 2.5)
    for example in examples:
        for token in split_semantic_tokens(example):
            add_semantic_token(tokens, token, 3.0)
            for alias in SEMANTIC_TOKEN_ALIASES.get(token, ()):
                add_semantic_token(tokens, alias, 3.0)
    return tokens


def split_semantic_tokens(value: str) -> list[str]:
    """Split ``value`` into lowercase alphanum tokens, dropping stop words."""
    raw_tokens = re.split(r"[^a-zA-Z0-9]+", str(value or "").lower())
    return [
        token
        for token in raw_tokens
        if len(token) >= 3 and token not in SEMANTIC_STOP_TOKENS
    ]


def add_semantic_token(tokens: dict[str, float], token: str, weight: float) -> None:
    """Insert/replace a token in ``tokens`` keeping the maximum weight."""
    token = str(token or "").lower().strip()
    if len(token) < 3 or token in SEMANTIC_STOP_TOKENS:
        return
    tokens[token] = max(tokens.get(token, 0.0), weight)


def pick_unused(fields: list[str], index: int, used: set[str]) -> str:
    """Pick ``fields[index]`` if available and unused; otherwise the first unused.

    Prevents the same field from being assigned to multiple placeholders
    (e.g. {f1} and {f2} both resolving to the same field).
    """
    default = fields[index] if index < len(fields) else (fields[0] if fields else "returns")
    if default not in used:
        return default
    for f in fields:
        if f not in used:
            return f
    return default  # all used — duplicate is unavoidable


def safe_float(value: Any) -> float:
    """Coerce ``value`` to float, returning 0.0 on TypeError/ValueError."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

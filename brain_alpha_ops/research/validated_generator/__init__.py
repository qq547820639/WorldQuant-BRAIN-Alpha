"""Expression generator with pre-validation — eliminates 3 main failure classes.

Replaces random field/operator assembly with signature-validated templates.
Target: reduce BRAIN rejection rate from ~39% to ~10%.

This package re-exports the public API previously provided by the flat
``validated_generator.py`` module so existing imports continue to work.
"""
from __future__ import annotations

from ._signatures import (
    OPERATOR_SIGNATURES,
    WINDOW_CONSTRAINTS,
    SAFE_FIELDS,
    TEMPLATES,
    FIELD_POOLS,
    FIELD_PAIRINGS,
    WINDOW_POOL,
    SHORT_WINDOWS,
    MEDIUM_WINDOWS,
    LONG_WINDOWS,
    get_active_safe_fields,
    get_active_field_pools,
    set_active_safe_fields,
)
from ._validate import (
    validate_expression,
    _extract_bracketed,
    _split_args,
    generate_validated_candidates,
    _minhash_top_k,
    _minhash_signature,
    _tokenize,
)
from ._prefilter import (
    prefilter_quality,
    _passes_diversity,
    CROSS_SECTIONAL_OPS,
    KNOWN_TOXIC_OPS,
    RETURN_TRANSFORM_OPS,
)

__all__ = [
    # Signatures & constants
    "OPERATOR_SIGNATURES",
    "WINDOW_CONSTRAINTS",
    "SAFE_FIELDS",
    "TEMPLATES",
    "FIELD_POOLS",
    "FIELD_PAIRINGS",
    "WINDOW_POOL",
    "SHORT_WINDOWS",
    "MEDIUM_WINDOWS",
    "LONG_WINDOWS",
    "get_active_safe_fields",
    "get_active_field_pools",
    "set_active_safe_fields",
    # Validation & generation
    "validate_expression",
    "_extract_bracketed",
    "_split_args",
    "generate_validated_candidates",
    "_minhash_top_k",
    "_minhash_signature",
    "_tokenize",
    # Pre-filter
    "prefilter_quality",
    "_passes_diversity",
    "CROSS_SECTIONAL_OPS",
    "KNOWN_TOXIC_OPS",
    "RETURN_TRANSFORM_OPS",
]

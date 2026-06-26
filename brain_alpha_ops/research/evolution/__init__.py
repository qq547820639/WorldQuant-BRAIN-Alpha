"""Re-export from the ``evolution`` subpackage for backward compatibility.

The original monolithic ``evolution.py`` was split into the
``brain_alpha_ops.research.evolution`` subpackage. This module re-exports
the full public API surface so legacy imports continue to work.

Sub-modules:
  - ``_types``     : ``MutationResult``, ``CrossoverResult``, ``EvolutionResult``
  - ``_mutation``  : ``MutationEngine`` class (8 mutation strategies)
  - ``_crossover`` : ``CrossoverEngine`` class
  - ``_meta``      : ``MetaEvolutionSelector`` + ``EvolutionRunner``
"""
from __future__ import annotations

# Re-export everything from sub-modules
from brain_alpha_ops.research.evolution._types import (  # noqa: F401
    CrossoverResult,
    EvolutionResult,
    MutationResult,
)
from brain_alpha_ops.research.evolution._mutation import (  # noqa: F401
    MutationEngine,
)
from brain_alpha_ops.research.evolution._crossover import (  # noqa: F401
    CrossoverEngine,
)
from brain_alpha_ops.research.evolution._meta import (  # noqa: F401
    EvolutionRunner,
    MetaEvolutionSelector,
)

# ---- Backward-compat re-exports originally at the bottom of evolution.py ----
# These symbols are imported by tests/test_evolution_engine.py and other
# legacy consumers from `brain_alpha_ops.research.evolution`.
from brain_alpha_ops.research.evolution_helpers import (  # noqa: F401
    _BINARY_OPERATORS,
    _COMMON_FIELDS,
    _GROUP_OPERATORS,
    _MAX_MUTATION_ATTEMPTS,
    _MIN_EXPRESSION_LENGTH,
    _MUTABLE_OPERATORS,
    _UNARY_OPERATORS,
    _WINDOW_OPERATORS,
    _WINDOW_RANGES,
    _expression_operators_are_official,
    _extract_inner,
    _is_valid_expression,
    _mutation_hash,
    _official_field_ids,
    _official_operator_names,
    _split_args,
    _split_top_level,
    _tokenize,
)
from brain_alpha_ops.research.generator import _MAX_EXPRESSION_LENGTH  # noqa: F401
_MAX_NESTING_DEPTH = 8  # backward-compat: moved to generator.LocalQualityConfig

__all__ = [
    # Data structures
    "MutationResult",
    "CrossoverResult",
    "EvolutionResult",
    # Engines
    "MutationEngine",
    "CrossoverEngine",
    "MetaEvolutionSelector",
    "EvolutionRunner",
    # Backward-compat re-exports from evolution_helpers
    "_BINARY_OPERATORS",
    "_COMMON_FIELDS",
    "_GROUP_OPERATORS",
    "_MAX_MUTATION_ATTEMPTS",
    "_MIN_EXPRESSION_LENGTH",
    "_MUTABLE_OPERATORS",
    "_UNARY_OPERATORS",
    "_WINDOW_OPERATORS",
    "_WINDOW_RANGES",
    "_expression_operators_are_official",
    "_extract_inner",
    "_is_valid_expression",
    "_mutation_hash",
    "_official_field_ids",
    "_official_operator_names",
    "_split_args",
    "_split_top_level",
    "_tokenize",
    # Backward-compat re-exports from generator
    "_MAX_EXPRESSION_LENGTH",
    "_MAX_NESTING_DEPTH",
]

"""Re-export from the ``hypothesis_expression_support`` subpackage.

The original monolithic ``hypothesis_expression_support.py`` was split
(deep-optimization-phase13) into responsibility-focused submodules:
  - ``_operators``     : module-level constants (``GROUP_KEYS``,
                         ``_OFFICIAL_OPERATOR_FALLBACK``, ``KNOWN_BRAIN_OPERATORS``),
                         the cached ``_current_official_operator_names`` loader,
                         and the small AST/window helpers (``format_window``,
                         ``is_group_key_node``, ``first_number_literal``)
  - ``_normalization`` : ``_ExpressionNormalizationMixin`` carrying the
                         expression shape normalization and field-function
                         rewriting methods
  - ``_fields``        : ``_FieldResolutionMixin`` carrying the field
                         sanitization, validation, resolution, and extraction
                         methods
  - ``_support``       : ``HypothesisExpressionSupport`` class assembly

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.hypothesis_expression_support import ...``
continue to work, and re-exports the private helper symbols so any tests
that monkeypatch ``brain_alpha_ops.research.hypothesis_expression_support._xxx``
keep functioning.
"""

from __future__ import annotations

from brain_alpha_ops.research.hypothesis_expression_support._fields import (  # noqa: F401
    _FieldResolutionMixin,
)
from brain_alpha_ops.research.hypothesis_expression_support._normalization import (  # noqa: F401
    _ExpressionNormalizationMixin,
)
from brain_alpha_ops.research.hypothesis_expression_support._operators import (  # noqa: F401
    GROUP_KEYS,
    KNOWN_BRAIN_OPERATORS,
    _OFFICIAL_OPERATOR_FALLBACK,
    _current_official_operator_names,
    first_number_literal,
    format_window,
    is_group_key_node,
)
from brain_alpha_ops.research.hypothesis_expression_support._support import (  # noqa: F401
    HypothesisExpressionSupport,
)

__all__ = [
    # Public API
    "HypothesisExpressionSupport",
    "GROUP_KEYS",
    "KNOWN_BRAIN_OPERATORS",
    "first_number_literal",
    "format_window",
    "is_group_key_node",
    # Private symbols re-exported for test monkeypatch compatibility
    "_FieldResolutionMixin",
    "_ExpressionNormalizationMixin",
    "_OFFICIAL_OPERATOR_FALLBACK",
    "_current_official_operator_names",
]

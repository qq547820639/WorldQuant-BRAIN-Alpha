"""``HypothesisExpressionSupport`` class assembly.

Extracted from the original ``hypothesis_expression_support.py`` monolith
(deep-optimization-phase13). The expression-shape normalization methods are
mixed in via ``_ExpressionNormalizationMixin`` (see ``_normalization``) and
the field sanitization / resolution / extraction methods are mixed in via
``_FieldResolutionMixin`` (see ``_fields``) to keep this file under the
per-submodule line budget while preserving the public class API.
"""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.research.hypothesis_expression_support._fields import (
    _FieldResolutionMixin,
)
from brain_alpha_ops.research.hypothesis_expression_support._normalization import (
    _ExpressionNormalizationMixin,
)
from brain_alpha_ops.research.hypothesis_expression_support._operators import (
    _current_official_operator_names,
)


class HypothesisExpressionSupport(
    _ExpressionNormalizationMixin,
    _FieldResolutionMixin,
):
    """Resolves semantic hypothesis templates into valid FASTEXPR expressions."""

    def __init__(
        self,
        *,
        fields: set[str],
        operators: set[str],
        loader: Any = None,
        dataset_id: str = "",
        logger: logging.Logger | None = None,
    ) -> None:
        self._fields = fields
        self._operators = {op.lower() for op in operators} if operators else set(_current_official_operator_names())
        self._loader = loader
        self._dataset_id = dataset_id
        # Hardcoded logger name preserves the original module name after the
        # monolith was split into submodules (``__name__`` here would resolve
        # to ``...hypothesis_expression_support._support``).
        self._logger = logger or logging.getLogger(
            "brain_alpha_ops.research.hypothesis_expression_support"
        )

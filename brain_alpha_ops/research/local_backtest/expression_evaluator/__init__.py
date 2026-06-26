"""Re-export from the ``expression_evaluator`` subpackage for backward compatibility.

The original monolithic ``expression_evaluator.py`` was split into the
``brain_alpha_ops.research.local_backtest.expression_evaluator`` subpackage.
This module re-exports the full public API surface so legacy imports continue
to work.

Sub-modules:
  - ``_tokenizer`` : ``_TokenizerMixin`` — tokenizer + recursive-descent parser
  - ``_evaluator`` : ``_EvaluatorMixin`` — AST evaluator + function dispatch
  - ``_operators`` : ``_OperatorsMixin`` — cross-sectional / rolling / row ops
  - ``_core``      : ``LocalExpressionEvaluator`` class assembly
"""
from __future__ import annotations

from brain_alpha_ops.research.local_backtest.expression_evaluator._core import *  # noqa: F401,F403
from brain_alpha_ops.research.local_backtest.expression_evaluator._core import (  # noqa: F401
    LocalExpressionEvaluator,
)

__all__ = ["LocalExpressionEvaluator"]

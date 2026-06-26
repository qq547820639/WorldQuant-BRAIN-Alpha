"""``LocalExpressionEvaluator`` — lightweight FASTEXPR subset evaluation.

Assembles the tokenizer, evaluator, and operator mixins into the final
``LocalExpressionEvaluator`` class.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from brain_alpha_ops.research.local_backtest.expression_evaluator._tokenizer import (
    _TokenizerMixin,
)
from brain_alpha_ops.research.local_backtest.expression_evaluator._evaluator import (
    _EvaluatorMixin,
)
from brain_alpha_ops.research.local_backtest.expression_evaluator._operators import (
    _OperatorsMixin,
)

if TYPE_CHECKING:
    from brain_alpha_ops.market_data_vector import MarketDataFrame


class LocalExpressionEvaluator(_TokenizerMixin, _EvaluatorMixin, _OperatorsMixin):
    """Evaluates a simplified FASTEXPR expression on cross-sectional market data.

    Supported operators:
      - rank(x)            : cross-sectional rank (0.0–1.0 normalized)
      - zscore(x)          : cross-sectional z-score
      - ts_zscore(x, w)    : rolling time-series z-score over w days
      - ts_mean(x, w)      : rolling time-series mean
      - ts_std_dev(x, w)   : rolling time-series std deviation
      - ts_delta(x, w)     : difference over w days
      - ts_sum(x, w)       : rolling sum
      - ts_min(x, w)       : rolling min
      - ts_max(x, w)       : rolling max
      - ts_corr(x, y, w)   : rolling correlation
      - +, -, *, /          : arithmetic operators
      - neg(x)             : negation
      - reverse(x)         : negation alias used by FASTEXPR
      - abs(x)             : absolute value
      - log(x)             : natural log (clip to positive)
      - sign(x)            : sign function
      - power(x, a)        : raise to power a
      - multiply(x, y)     : elementwise multiplication
      - group_rank(x, s)   : rank within sector (s = sector field, currently ignored)
    """

    def evaluate(
        self,
        expression: str,
        data: "MarketDataFrame",
        *,
        max_depth: int = 6,
        max_length: int = 500,
    ) -> list[list[float]]:
        """Evaluate a FASTEXPR expression string on the given market data.

        Returns:
            2D list: [dates][symbols] of computed alpha values.
            NaN values are replaced with 0.0.

        Raises:
            ValueError: if expression exceeds max_depth or max_length.
        """
        if len(expression) > max_length:
            raise ValueError(
                f"expression too long: {len(expression)} > {max_length}"
            )
        tokens = self._tokenize(expression)
        if len(tokens) < 1:
            raise ValueError("empty expression")
        ast = self._parse(tokens, max_depth=max_depth)
        result = self._eval_ast(ast, data)
        # Replace NaN/Inf with 0.0
        for i, row in enumerate(result):
            result[i] = [
                0.0 if (math.isnan(v) or math.isinf(v)) else v for v in row
            ]
        return result


__all__ = ["LocalExpressionEvaluator"]

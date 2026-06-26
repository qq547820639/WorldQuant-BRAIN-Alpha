"""AST evaluator and function-dispatch mixin for ``LocalExpressionEvaluator``."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_corr as _safe_corr,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_mean as _safe_mean,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_stdev as _safe_stdev,
)

if TYPE_CHECKING:
    from brain_alpha_ops.market_data_vector import MarketDataFrame


class _EvaluatorMixin:
    """AST evaluator and function dispatcher."""

    def _eval_ast(
        self, node: dict, data: "MarketDataFrame"
    ) -> list[list[float]]:
        kind = node.get("kind")

        if kind == "literal":
            value = float(node.get("value", 0.0))
            return [[value] * data.n_symbols for _ in range(data.n_dates)]

        elif kind == "ident":
            field_name = node.get("value", "")
            field_data = data.get(field_name)
            if not field_data:
                # Try common aliases
                aliases = {
                    "price": "close",
                    "return": "returns",
                    "volume_traded": "volume",
                }
                aliased = aliases.get(field_name, "")
                field_data = data.get(aliased) if aliased else []
            if not field_data:
                # Unknown field → return zeros
                return [[0.0] * data.n_symbols for _ in range(data.n_dates)]
            return [list(row) for row in field_data]

        elif kind == "call":
            func = node.get("func", "")
            args = [
                self._eval_ast(arg, data) for arg in node.get("args", [])
            ]
            return self._apply_function(func, args, data)

        elif kind == "unary":
            op = node.get("op")
            arg = self._eval_ast(node["arg"], data)
            if op == "neg":
                return [[-v for v in row] for row in arg]
            return arg

        elif kind == "binary":
            left = self._eval_ast(node["left"], data)
            right = self._eval_ast(node["right"], data)
            op = node.get("op")
            return self._apply_binary(op, left, right)

        return [[0.0] * data.n_symbols for _ in range(data.n_dates)]

    def _apply_function(
        self,
        func: str,
        args: list[list[list[float]]],
        data: "MarketDataFrame",
    ) -> list[list[float]]:
        """Apply a function to its evaluated arguments."""
        n_dates = data.n_dates
        n_symbols = data.n_symbols

        if func == "rank" and args:
            return [self._cross_rank(row) for row in args[0]]

        elif func == "zscore" and args:
            return [self._cross_zscore(row) for row in args[0]]

        elif func == "ts_zscore" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(
                args[0], window, self._ts_zscore_window
            )

        elif func == "ts_rank" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(
                args[0], window, self._ts_rank_window
            )

        elif func == "ts_decay_linear" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(
                args[0], window, self._ts_decay_linear_window
            )

        elif func == "ts_mean" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(
                args[0], window, lambda w: _safe_mean(w)
            )

        elif func == "ts_std_dev" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(
                args[0], window, lambda w: _safe_stdev(w)
            )

        elif func == "ts_delta" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._ts_delta(args[0], window)

        elif func == "ts_sum" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(args[0], window, sum)

        elif func == "ts_min" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(args[0], window, min)

        elif func == "ts_max" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(args[0], window, max)

        elif func == "abs" and args:
            return [[abs(v) for v in row] for row in args[0]]

        elif func in {"neg", "reverse"} and args:
            return [[-v for v in row] for row in args[0]]

        elif func == "log" and args:
            return [
                [math.log(max(1e-10, v)) for v in row] for row in args[0]
            ]

        elif func == "sign" and args:
            return [
                [
                    (1 if v > 0 else (-1 if v < 0 else 0))
                    for v in row
                ]
                for row in args[0]
            ]

        elif func == "power" and len(args) >= 2:
            power_val = self._extract_scalar(args[1])
            return [
                [
                    v**power_val if v >= 0 else -((-v) ** power_val)
                    for v in row
                ]
                for row in args[0]
            ]

        elif func == "ts_corr" and len(args) >= 3:
            window = self._extract_window(args[2])
            # Precompute bounds to avoid redundant len() checks per-iteration
            max_t_a = len(args[0])
            max_t_b = len(args[1])
            result = []
            for d in range(n_dates):
                row = [0.0] * n_symbols
                start = max(0, d - window + 1)
                end = min(d + 1, max_t_a, max_t_b)
                for s in range(n_symbols):
                    xs = [args[0][t][s] for t in range(start, end)]
                    ys = [args[1][t][s] for t in range(start, end)]
                    row[s] = _safe_corr(xs, ys)
                result.append(row)
            return result

        elif func == "group_rank" and args:
            # Simplified: cross-sectional rank without sector grouping
            return [self._cross_rank(row) for row in args[0]]

        elif func == "group_neutralize" and args:
            return [self._group_neutralize(row) for row in args[0]]

        elif func == "winsorize" and args:
            std = (
                self._extract_scalar(args[1]) if len(args) >= 2 else 3.0
            )
            return [self._winsorize_row(row, std) for row in args[0]]

        elif func == "normalize" and args:
            return [self._normalize_row(row) for row in args[0]]

        elif func == "divide" and len(args) >= 2:
            return self._apply_binary("/", args[0], args[1])

        elif func == "multiply" and len(args) >= 2:
            return self._apply_binary("*", args[0], args[1])

        elif func == "subtract" and len(args) >= 2:
            return self._apply_binary("-", args[0], args[1])

        elif func == "greater" and len(args) >= 2:
            return self._apply_binary(">", args[0], args[1])

        elif func == "if_else" and len(args) >= 3:
            return self._if_else(args[0], args[1], args[2])

        # Unknown function → return first arg or zeros
        return (
            args[0]
            if args
            else [[0.0] * n_symbols for _ in range(n_dates)]
        )

    def _apply_binary(
        self,
        op: str,
        left: list[list[float]],
        right: list[list[float]],
    ) -> list[list[float]]:
        ops = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b if abs(b) > 1e-10 else 0.0,
            ">": lambda a, b: 1.0 if a > b else 0.0,
        }
        func = ops.get(op, lambda a, b: 0.0)
        result = []
        for lrow, rrow in zip(left, right):
            row = [func(la, rb) for la, rb in zip(lrow, rrow)]
            result.append(row)
        return result

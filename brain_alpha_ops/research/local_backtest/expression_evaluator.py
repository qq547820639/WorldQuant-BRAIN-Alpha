"""LocalExpressionEvaluator — lightweight FASTEXPR subset evaluation."""

from __future__ import annotations

import math
import re
import statistics

from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_corr as _safe_corr,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_mean as _safe_mean,
)
from brain_alpha_ops.research.local_backtest_metrics_helpers import (
    safe_stdev as _safe_stdev,
)

# Pre-compiled tokenizer regex — executed once at import, not per-expression
_TOKEN_PATTERN = re.compile(
    r"("
    r"[a-zA-Z_][a-zA-Z0-9_]*"  # identifier
    r"|[0-9]+(?:\.[0-9]*)?"  # number
    r'|[+\-*/()=<>!?,]'  # operator / punctuation
    r")\s*"
)


class LocalExpressionEvaluator:
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

    # ── Tokenizer ────────────────────────────────────────────────────────

    def _tokenize(self, expression: str) -> list[tuple[str, str]]:
        """Tokenize a FASTEXPR expression string."""
        tokens: list[tuple[str, str]] = []
        for match in _TOKEN_PATTERN.finditer(expression):
            token = match.group(1).strip()
            if not token:
                continue
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", token):
                tokens.append(("ident", token))
            elif re.match(r"^[0-9]+(?:\.[0-9]*)?$", token):
                tokens.append(("number", token))
            elif token in ("+", "-", "*", "/"):
                tokens.append(("arith", token))
            elif token == "(":
                tokens.append(("lparen", token))
            elif token == ")":
                tokens.append(("rparen", token))
            elif token == ",":
                tokens.append(("comma", token))
            else:
                tokens.append(("punct", token))
        return tokens

    # ── Parser ────────────────────────────────────────────────────────────

    def _parse(
        self,
        tokens: list[tuple[str, str]],
        *,
        max_depth: int = 6,
        depth: int = 0,
    ) -> dict:
        if depth > max_depth:
            raise ValueError(f"expression exceeds max depth {max_depth}")

        index = 0
        current_depth = depth  # nonlocal depth tracker for nested calls

        def peek() -> tuple[str, str] | None:
            nonlocal index
            return tokens[index] if index < len(tokens) else None

        def consume() -> tuple[str, str]:
            nonlocal index
            tok = tokens[index]
            index += 1
            return tok

        def parse_primary() -> dict:
            nonlocal current_depth
            current_depth += 1
            if current_depth > max_depth:
                raise ValueError(
                    f"expression exceeds max depth {max_depth}"
                )

            tok = peek()
            if tok is None:
                raise ValueError("unexpected end of expression")
            kind, value = tok

            if (
                kind == "ident"
                and index + 1 < len(tokens)
                and tokens[index + 1][0] == "lparen"
            ):
                # Function call — depth increments for the call itself and for each arg
                func_name = value
                consume()  # ident
                consume()  # lparen
                args = []
                while peek() and peek()[0] != "rparen":
                    args.append(parse_expr())
                    if peek() and peek()[0] == "comma":
                        consume()
                if peek() and peek()[0] == "rparen":
                    consume()
                else:
                    raise ValueError(
                        f"missing closing paren for {func_name}"
                    )
                current_depth -= 1
                return {
                    "kind": "call",
                    "func": func_name,
                    "args": args,
                    "depth": current_depth,
                }

            elif kind == "lparen":
                consume()
                expr = parse_expr()
                if peek() and peek()[0] == "rparen":
                    consume()
                current_depth -= 1
                return expr

            elif kind == "number":
                consume()
                current_depth -= 1
                return {"kind": "literal", "value": float(value)}

            elif kind == "ident":
                consume()
                current_depth -= 1
                return {"kind": "ident", "value": value}

            elif (
                kind == "arith"
                and value == "-"
                and (
                    index == 0
                    or tokens[index - 1][0]
                    in ("lparen", "arith", "comma")
                )
            ):
                # Unary minus
                consume()
                operand = parse_primary()
                current_depth -= 1
                return {"kind": "unary", "op": "neg", "arg": operand}

            else:
                raise ValueError(f"unexpected token: {tok}")

        def parse_expr() -> dict:
            # Build: primary (arith primary)*  — left-associative
            left = parse_primary()
            while peek() and peek()[0] == "arith":
                op = peek()[1]
                # Check for unary minus (already handled in parse_primary)
                if (
                    op == "-"
                    and isinstance(left, dict)
                    and left.get("kind") == "literal"
                    and left.get("value") == 0.0
                ):
                    break  # handled as unary
                consume()  # consume arith
                right = parse_primary()
                left = {
                    "kind": "binary",
                    "op": op,
                    "left": left,
                    "right": right,
                }
            return left

        return parse_expr()

    # ── AST Evaluator ─────────────────────────────────────────────────────

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

    # ── Cross-sectional helpers ──────────────────────────────────────────

    @staticmethod
    def _cross_rank(values: list[float]) -> list[float]:
        n = len(values)
        if n == 0:
            return []
        indexed = [(v, i) for i, v in enumerate(values)]
        indexed.sort(key=lambda x: (x[0], x[1]))
        ranks = [0.0] * n
        for rank, (v, i) in enumerate(indexed):
            ranks[i] = rank / max(1, n - 1)
        return ranks

    @staticmethod
    def _cross_zscore(values: list[float]) -> list[float]:
        n = len(values)
        if n <= 1:
            return [0.0] * n
        mean_val = statistics.mean(values)
        stdev_val = statistics.stdev(values) if n > 1 else 1.0
        if abs(stdev_val) < 1e-10:
            return [0.0] * n
        return [(v - mean_val) / stdev_val for v in values]

    # ── Rolling window helpers ───────────────────────────────────────────

    @staticmethod
    def _rolling_apply(
        data: list[list[float]], window: int, func
    ) -> list[list[float]]:
        n_dates = len(data)
        n_symbols = len(data[0]) if data else 0
        result = [[0.0] * n_symbols for _ in range(n_dates)]
        for s in range(n_symbols):
            series = [data[d][s] for d in range(n_dates)]
            for d in range(n_dates):
                start = max(0, d - window + 1)
                win = series[start : d + 1]
                result[d][s] = func(win)
        return result

    @staticmethod
    def _ts_zscore_window(window: list[float]) -> float:
        if len(window) <= 1:
            return 0.0
        mean_val = statistics.mean(window)
        stdev_val = _safe_stdev(window)
        if abs(stdev_val) < 1e-10:
            return 0.0
        return (window[-1] - mean_val) / stdev_val

    @staticmethod
    def _ts_rank_window(window: list[float]) -> float:
        if not window:
            return 0.0
        ranked = sorted(
            (value, idx) for idx, value in enumerate(window)
        )
        positions = {
            idx: rank for rank, (_value, idx) in enumerate(ranked)
        }
        if len(window) == 1:
            return 0.0
        return positions[len(window) - 1] / max(1, len(window) - 1)

    @staticmethod
    def _ts_decay_linear_window(window: list[float]) -> float:
        if not window:
            return 0.0
        weights = list(range(1, len(window) + 1))
        denom = float(sum(weights) or 1.0)
        return (
            sum(
                value * weight
                for value, weight in zip(window, weights)
            )
            / denom
        )

    @staticmethod
    def _ts_delta(
        data: list[list[float]], window: int
    ) -> list[list[float]]:
        n_dates = len(data)
        n_symbols = len(data[0]) if data else 0
        result = [[0.0] * n_symbols for _ in range(n_dates)]
        for d in range(n_dates):
            if d >= window:
                result[d] = [
                    data[d][s] - data[d - window][s]
                    for s in range(n_symbols)
                ]
        return result

    @staticmethod
    def _group_neutralize(row: list[float]) -> list[float]:
        if not row:
            return []
        mean_val = _safe_mean(row)
        return [value - mean_val for value in row]

    @staticmethod
    def _winsorize_row(
        row: list[float], std_factor: float
    ) -> list[float]:
        if not row:
            return []
        mean_val = _safe_mean(row)
        stdev_val = _safe_stdev(row)
        limit = abs(float(std_factor or 3.0)) * max(stdev_val, 1e-10)
        lower = mean_val - limit
        upper = mean_val + limit
        return [min(max(value, lower), upper) for value in row]

    @staticmethod
    def _normalize_row(row: list[float]) -> list[float]:
        if not row:
            return []
        mean_val = _safe_mean(row)
        stdev_val = _safe_stdev(row)
        if abs(stdev_val) < 1e-10:
            return [0.0 for _ in row]
        return [(value - mean_val) / stdev_val for value in row]

    @staticmethod
    def _if_else(
        cond: list[list[float]],
        when_true: list[list[float]],
        when_false: list[list[float]],
    ) -> list[list[float]]:
        result: list[list[float]] = []
        for cond_row, true_row, false_row in zip(
            cond, when_true, when_false
        ):
            row = [
                true_val if cond_val > 0 else false_val
                for cond_val, true_val, false_val in zip(
                    cond_row, true_row, false_row
                )
            ]
            result.append(row)
        return result

    @staticmethod
    def _extract_window(arg: list[list[float]]) -> int:
        """Extract window size from an AST argument (scalar or array)."""
        if arg and arg[0]:
            val = arg[0][0]
            return max(1, int(abs(val)))
        return 20

    @staticmethod
    def _extract_scalar(arg: list[list[float]]) -> float:
        if arg and arg[0]:
            return float(arg[0][0])
        return 2.0


__all__ = ["LocalExpressionEvaluator"]

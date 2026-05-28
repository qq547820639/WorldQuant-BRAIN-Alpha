"""Local backtest engine — evaluates alpha expressions without BRAIN API calls.

Supports a subset of FASTEXPR operators locally and computes standard metrics
(Sharpe, Fitness, Turnover, Drawdown, IC, IR) using vectorized operations.
Designed to pre-filter candidate expressions before consuming BRAIN API quota.

Architecture
------------
    LocalBacktestEngine
     ├── ExpressionEvaluator — evaluates a FASTEXPR AST on market data
     ├── PortfolioConstructor — daily cross-sectional ranking → long/short
     ├── MetricsComputer — Sharpe, Fitness, Turnover, Drawdown, IC, IR
     └── SyntheticDataProvider — generates test data when no real data

Usage::

    engine = LocalBacktestEngine()
    result = engine.evaluate("rank(ts_zscore(close, 20))")
    print(result["sharpe"], result["fitness"])
"""

from __future__ import annotations

import logging
import math
import random
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Pre-compiled tokenizer regex — executed once at import, not per-expression
_TOKEN_PATTERN = re.compile(
    r'('
    r'[a-zA-Z_][a-zA-Z0-9_]*'       # identifier
    r'|[0-9]+(?:\.[0-9]*)?'          # number
    r'|[+\-*/()=<>!?,]'               # operator / punctuation
    r')\s*'
)

# ═══════════════════════════════════════════════════════════════════════════
# Synthetic Market Data Provider
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MarketDataFrame:
    """A simple cross-sectional market data frame.

    Columns map field names to 2D arrays: rows = dates, columns = stocks.
    """
    fields: dict[str, list[list[float]]] = field(default_factory=dict)
    dates: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    n_dates: int = 0
    n_symbols: int = 0

    def get(self, field: str) -> list[list[float]]:
        return self.fields.get(field, [])

    def column(self, field: str, date_idx: int) -> list[float]:
        rows = self.fields.get(field, [])
        if date_idx < len(rows):
            return list(rows[date_idx])
        return [0.0] * self.n_symbols


class SyntheticDataProvider:
    """Generates synthetic market data for local backtest evaluation.

    Creates realistic time-series data for standard BRAIN fields (close, volume,
    returns, etc.) with configurable trend, volatility, and correlation.
    """

    STANDARD_FIELDS = [
        "close", "volume", "returns", "market_cap", "book_to_price",
        "pe_ratio", "debt_to_equity", "roe", "revenue_growth",
        "momentum_1m", "momentum_3m", "momentum_12m",
        "volatility_1m", "volatility_3m",
        "rsi_14", "macd", "atr_14",
        "short_interest", "dividend_yield", "beta",
        "open", "high", "low", "vwap", "adv20",
        "assets", "revenue", "eps", "operating_income", "enterprise_value",
        "anl4_ebit_value", "anl4_ebitda_value",
        "anl4_cfo_value", "anl4_cfi_value", "anl4_fcf_value",
        "anl4_epsr_value", "anl4_epsr_mean",
        "sector", "industry", "subindustry", "market",
    ]

    def generate(
        self,
        *,
        n_dates: int = 252,
        n_symbols: int = 500,
        fields: list[str] | None = None,
        start_date: str = "2024-01-01",
        seed: int = 42,
    ) -> MarketDataFrame:
        """Generate a synthetic market data frame.

        Args:
            n_dates: Number of trading days (default 252 ≈ 1 year).
            n_symbols: Number of stocks.
            fields: Field names to generate (defaults to STANDARD_FIELDS).
            start_date: ISO date string for the first trading day.
            seed: Random seed for reproducibility.

        Returns:
            A MarketDataFrame ready for backtest evaluation.
        """
        fields = fields or self.STANDARD_FIELDS
        rng = random.Random(seed)
        symbols = [f"STOCK_{i:04d}" for i in range(n_symbols)]

        # Generate trading dates (weekdays only)
        dates = []
        current = date.fromisoformat(start_date)
        while len(dates) < n_dates:
            if current.weekday() < 5:  # Monday-Friday
                dates.append(current.isoformat())
            current += timedelta(days=1)

        data = MarketDataFrame(
            fields={},
            dates=dates,
            symbols=symbols,
            n_dates=n_dates,
            n_symbols=n_symbols,
        )

        for field_name in fields:
            field_data = self._generate_field(field_name, n_dates, n_symbols, rng)
            data.fields[field_name] = field_data

        return data

    def _generate_field(
        self,
        name: str,
        n_dates: int,
        n_symbols: int,
        rng: random.Random,
    ) -> list[list[float]]:
        """Generate a single field's time-series cross-sectional data."""
        if name == "close":
            return self._generate_price_series(n_dates, n_symbols, rng, drift=0.0003, vol=0.015)
        elif name == "volume":
            return [[abs(rng.gauss(1_000_000, 500_000)) for _ in range(n_symbols)] for _ in range(n_dates)]
        elif name == "returns":
            return [[rng.gauss(0.0005, 0.02) for _ in range(n_symbols)] for _ in range(n_dates)]
        elif name == "market_cap":
            return self._generate_price_series(n_dates, n_symbols, rng, drift=0.0002, vol=0.01, base=1e9)
        elif name in ("momentum_1m", "momentum_3m", "momentum_12m"):
            window = {"momentum_1m": 21, "momentum_3m": 63, "momentum_12m": 252}.get(name, 21)
            return [[rng.gauss(0.01, 0.08) for _ in range(n_symbols)] for _ in range(n_dates)]
        elif name in ("volatility_1m", "volatility_3m"):
            return [[abs(rng.gauss(0.02, 0.01)) for _ in range(n_symbols)] for _ in range(n_dates)]
        elif name == "rsi_14":
            return [[30.0 + rng.random() * 40.0 for _ in range(n_symbols)] for _ in range(n_dates)]
        elif name == "beta":
            return [[0.5 + rng.random() * 1.5 for _ in range(n_symbols)] for _ in range(n_dates)]
        else:
            # Generic mean-reverting signal
            return [[rng.gauss(0.0, 1.0) for _ in range(n_symbols)] for _ in range(n_dates)]

    @staticmethod
    def _generate_price_series(
        n_dates: int,
        n_symbols: int,
        rng: random.Random,
        drift: float = 0.0003,
        vol: float = 0.015,
        base: float = 100.0,
    ) -> list[list[float]]:
        """Generate correlated geometric Brownian motion price series."""
        # Initialize starting prices
        prices = [[base * (0.5 + rng.random()) for _ in range(n_symbols)]]
        for _ in range(1, n_dates):
            # Market factor (common to all stocks)
            market_return = rng.gauss(drift, vol * 0.6)
            new_row = []
            for prev_price in prices[-1]:
                stock_return = rng.gauss(0.0, vol * 0.8) + market_return
                new_row.append(prev_price * math.exp(stock_return))
            prices.append(new_row)
        return prices


# ═══════════════════════════════════════════════════════════════════════════
# Expression Evaluator (Lightweight FASTEXPR subset)
# ═══════════════════════════════════════════════════════════════════════════

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
      - abs(x)             : absolute value
      - log(x)             : natural log (clip to positive)
      - sign(x)            : sign function
      - power(x, a)        : raise to power a
      - group_rank(x, s)   : rank within sector (s = sector field, currently ignored)
    """

    def evaluate(
        self,
        expression: str,
        data: MarketDataFrame,
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
            raise ValueError(f"expression too long: {len(expression)} > {max_length}")
        tokens = self._tokenize(expression)
        if len(tokens) < 1:
            raise ValueError("empty expression")
        ast = self._parse(tokens, max_depth=max_depth)
        result = self._eval_ast(ast, data)
        # Replace NaN/Inf with 0.0
        for i, row in enumerate(result):
            result[i] = [0.0 if (math.isnan(v) or math.isinf(v)) else v for v in row]
        return result

    # ── Tokenizer ────────────────────────────────────────────────────────

    def _tokenize(self, expression: str) -> list[tuple[str, str]]:
        """Tokenize a FASTEXPR expression string."""
        tokens: list[tuple[str, str]] = []
        for match in _TOKEN_PATTERN.finditer(expression):
            token = match.group(1).strip()
            if not token:
                continue
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', token):
                tokens.append(("ident", token))
            elif re.match(r'^[0-9]+(?:\.[0-9]*)?$', token):
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

    def _parse(self, tokens: list[tuple[str, str]], *, max_depth: int = 6, depth: int = 0) -> dict:
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
                raise ValueError(f"expression exceeds max depth {max_depth}")

            tok = peek()
            if tok is None:
                raise ValueError("unexpected end of expression")
            kind, value = tok

            if kind == "ident" and index + 1 < len(tokens) and tokens[index + 1][0] == "lparen":
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
                    raise ValueError(f"missing closing paren for {func_name}")
                current_depth -= 1
                return {"kind": "call", "func": func_name, "args": args, "depth": current_depth}

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

            elif kind == "arith" and value == "-" and (index == 0 or tokens[index-1][0] in ("lparen", "arith", "comma")):
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
                if op == "-" and isinstance(left, dict) and left.get("kind") == "literal" and left.get("value") == 0.0:
                    break  # handled as unary
                consume()  # consume arith
                right = parse_primary()
                left = {"kind": "binary", "op": op, "left": left, "right": right}
            return left

        return parse_expr()

    # ── AST Evaluator ─────────────────────────────────────────────────────

    def _eval_ast(self, node: dict, data: MarketDataFrame) -> list[list[float]]:
        kind = node.get("kind")

        if kind == "literal":
            value = float(node.get("value", 0.0))
            return [[value] * data.n_symbols for _ in range(data.n_dates)]

        elif kind == "ident":
            field_name = node.get("value", "")
            field_data = data.get(field_name)
            if not field_data:
                # Try common aliases
                aliases = {"price": "close", "return": "returns", "volume_traded": "volume"}
                aliased = aliases.get(field_name, "")
                field_data = data.get(aliased) if aliased else []
            if not field_data:
                # Unknown field → return zeros
                return [[0.0] * data.n_symbols for _ in range(data.n_dates)]
            return [list(row) for row in field_data]

        elif kind == "call":
            func = node.get("func", "")
            args = [self._eval_ast(arg, data) for arg in node.get("args", [])]
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

    def _apply_function(self, func: str, args: list[list[list[float]]], data: MarketDataFrame) -> list[list[float]]:
        """Apply a function to its evaluated arguments."""
        n_dates = data.n_dates
        n_symbols = data.n_symbols

        if func == "rank" and args:
            return [self._cross_rank(row) for row in args[0]]

        elif func == "zscore" and args:
            return [self._cross_zscore(row) for row in args[0]]

        elif func == "ts_zscore" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(args[0], window, self._ts_zscore_window)

        elif func == "ts_rank" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(args[0], window, self._ts_rank_window)

        elif func == "ts_decay_linear" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(args[0], window, self._ts_decay_linear_window)

        elif func == "ts_mean" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(args[0], window, lambda w: _safe_mean(w))

        elif func == "ts_std_dev" and len(args) >= 2:
            window = self._extract_window(args[1])
            return self._rolling_apply(args[0], window, lambda w: _safe_stdev(w))

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

        elif func == "neg" and args:
            return [[-v for v in row] for row in args[0]]

        elif func == "log" and args:
            return [[math.log(max(1e-10, v)) for v in row] for row in args[0]]

        elif func == "sign" and args:
            return [[(1 if v > 0 else (-1 if v < 0 else 0)) for v in row] for row in args[0]]

        elif func == "power" and len(args) >= 2:
            power_val = self._extract_scalar(args[1])
            return [[v ** power_val if v >= 0 else -((-v) ** power_val) for v in row] for row in args[0]]

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
            std = self._extract_scalar(args[1]) if len(args) >= 2 else 3.0
            return [self._winsorize_row(row, std) for row in args[0]]

        elif func == "normalize" and args:
            return [self._normalize_row(row) for row in args[0]]

        elif func == "divide" and len(args) >= 2:
            return self._apply_binary("/", args[0], args[1])

        elif func == "subtract" and len(args) >= 2:
            return self._apply_binary("-", args[0], args[1])

        elif func == "greater" and len(args) >= 2:
            return self._apply_binary(">", args[0], args[1])

        elif func == "if_else" and len(args) >= 3:
            return self._if_else(args[0], args[1], args[2])

        # Unknown function → return first arg or zeros
        return args[0] if args else [[0.0] * n_symbols for _ in range(n_dates)]

    def _apply_binary(self, op: str, left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
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
    def _rolling_apply(data: list[list[float]], window: int, func) -> list[list[float]]:
        n_dates = len(data)
        n_symbols = len(data[0]) if data else 0
        result = [[0.0] * n_symbols for _ in range(n_dates)]
        for s in range(n_symbols):
            series = [data[d][s] for d in range(n_dates)]
            for d in range(n_dates):
                start = max(0, d - window + 1)
                win = series[start:d + 1]
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
        ranked = sorted((value, idx) for idx, value in enumerate(window))
        positions = {idx: rank for rank, (_value, idx) in enumerate(ranked)}
        if len(window) == 1:
            return 0.0
        return positions[len(window) - 1] / max(1, len(window) - 1)

    @staticmethod
    def _ts_decay_linear_window(window: list[float]) -> float:
        if not window:
            return 0.0
        weights = list(range(1, len(window) + 1))
        denom = float(sum(weights) or 1.0)
        return sum(value * weight for value, weight in zip(window, weights)) / denom

    @staticmethod
    def _ts_delta(data: list[list[float]], window: int) -> list[list[float]]:
        n_dates = len(data)
        n_symbols = len(data[0]) if data else 0
        result = [[0.0] * n_symbols for _ in range(n_dates)]
        for d in range(n_dates):
            if d >= window:
                result[d] = [data[d][s] - data[d - window][s] for s in range(n_symbols)]
        return result

    @staticmethod
    def _group_neutralize(row: list[float]) -> list[float]:
        if not row:
            return []
        mean_val = _safe_mean(row)
        return [value - mean_val for value in row]

    @staticmethod
    def _winsorize_row(row: list[float], std_factor: float) -> list[float]:
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
    def _if_else(cond: list[list[float]], when_true: list[list[float]], when_false: list[list[float]]) -> list[list[float]]:
        result: list[list[float]] = []
        for cond_row, true_row, false_row in zip(cond, when_true, when_false):
            row = [true_val if cond_val > 0 else false_val for cond_val, true_val, false_val in zip(cond_row, true_row, false_row)]
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


# ═══════════════════════════════════════════════════════════════════════════
# Portfolio Constructor
# ═══════════════════════════════════════════════════════════════════════════

class PortfolioConstructor:
    """Construct dollar-neutral long/short portfolios from daily alpha signals.

    Each day:
      - Long: top quantile stocks (positive weight proportional to rank)
      - Short: bottom quantile stocks (negative weight proportional to rank)
      - Remaining stocks: zero weight
    """

    def __init__(self, long_quantile: float = 0.2, short_quantile: float = 0.2):
        self.long_quantile = long_quantile
        self.short_quantile = short_quantile

    def construct(self, alphas: list[list[float]]) -> list[list[float]]:
        """Build portfolio weights from alpha signals.

        Returns:
            2D list: [dates][symbols] of portfolio weights.
            Weights sum to 0.0 each day (dollar-neutral).
        """
        weights = []
        for day_alphas in alphas:
            n = len(day_alphas)
            if n == 0:
                weights.append([])
                continue

            # Sort by alpha value (ascending)
            indexed = sorted(enumerate(day_alphas), key=lambda x: x[1])
            n_long = max(1, int(n * self.long_quantile))
            n_short = max(1, int(n * self.short_quantile))

            day_weights = [0.0] * n
            # Short: bottom quantile (most negative alpha)
            for rank, (i, _) in enumerate(indexed[:n_short]):
                day_weights[i] = -1.0 / n_short
            # Long: top quantile (most positive alpha)
            for rank, (i, _) in enumerate(indexed[-n_long:]):
                day_weights[i] = 1.0 / n_long

            # Dollar-neutral check: force sum to zero
            total = sum(day_weights)
            if abs(total) > 1e-10:
                adjustment = total / n
                day_weights = [w - adjustment for w in day_weights]

            weights.append(day_weights)
        return weights


# ═══════════════════════════════════════════════════════════════════════════
# Metrics Computer
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class BacktestMetrics:
    """Standard backtest metrics aligned with BRAIN API format."""
    sharpe: float = 0.0
    fitness: float = 0.0
    turnover: float = 0.0
    returns: float = 0.0
    drawdown: float = 0.0
    correlation: float = 0.0
    weight_concentration: float = 0.0
    sub_universe_sharpe: float = 0.0
    margin_bps: float = 0.0
    ic_mean: float = 0.0
    ic_ir: float = 0.0
    n_dates: int = 0
    n_symbols: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sharpe": round(self.sharpe, 4),
            "fitness": round(self.fitness, 4),
            "turnover": round(self.turnover, 4),
            "returns": round(self.returns, 4),
            "drawdown": round(self.drawdown, 4),
            "correlation": round(self.correlation, 4),
            "weight_concentration": round(self.weight_concentration, 4),
            "sub_universe_sharpe": round(self.sub_universe_sharpe, 4),
            "margin": round(self.margin_bps, 4),
            "ic_mean": round(self.ic_mean, 4),
            "ic_ir": round(self.ic_ir, 4),
            "n_dates": self.n_dates,
            "n_symbols": self.n_symbols,
        }


class MetricsComputer:
    """Compute standard backtest metrics from portfolio weights and returns."""

    def compute(
        self,
        weights: list[list[float]],
        returns: list[list[float]],
        *,
        alphas: list[list[float]] | None = None,
        trading_days_per_year: int = 252,
    ) -> BacktestMetrics:
        """Compute all standard metrics.

        Args:
            weights: [dates][symbols] portfolio weights (dollar-neutral).
            returns: [dates][symbols] daily returns.
            alphas: Optional [dates][symbols] raw alpha signals.
                   Used for IC/IR computation (preferred over weights proxy).
            trading_days_per_year: Annualization factor.

        Returns:
            BacktestMetrics dataclass.
        """
        n_dates = len(weights)
        n_symbols = len(weights[0]) if weights else 0
        metrics = BacktestMetrics(n_dates=n_dates, n_symbols=n_symbols)

        # Daily PnL: dot product of weights and returns
        daily_pnl = []
        for d in range(n_dates):
            if d < len(returns):
                pnl = sum(weights[d][s] * returns[d][s] for s in range(n_symbols))
                daily_pnl.append(pnl)
            else:
                daily_pnl.append(0.0)

        if not daily_pnl or n_dates < 2:
            return metrics

        # Sharpe ratio
        mean_pnl = statistics.mean(daily_pnl)
        stdev_pnl = _safe_stdev(daily_pnl)
        metrics.sharpe = (mean_pnl / max(stdev_pnl, 1e-10)) * math.sqrt(trading_days_per_year)

        # Returns (annualized)
        metrics.returns = mean_pnl * trading_days_per_year

        # Turnover
        turnovers = []
        for d in range(1, n_dates):
            to = sum(abs(weights[d][s] - weights[d - 1][s]) for s in range(n_symbols)) / 2.0
            turnovers.append(to)
        metrics.turnover = statistics.mean(turnovers) if turnovers else 0.0

        # Fitness (BRAIN formula: Sharpe * sqrt(|Returns| / max(Turnover, 0.125)))
        adj_turnover = max(metrics.turnover, 0.125)
        metrics.fitness = metrics.sharpe * math.sqrt(abs(metrics.returns) / adj_turnover)

        # Drawdown (max peak-to-trough)
        cumulative = _cumsum(daily_pnl)
        max_dd = 0.0
        peak = cumulative[0]
        for val in cumulative:
            if val > peak:
                peak = val
            dd = peak - val
            if dd > max_dd:
                max_dd = dd
        metrics.drawdown = max_dd

        # Correlation (auto-correlation of daily PnL — lag-1)
        if len(daily_pnl) >= 2:
            metrics.correlation = _safe_corr(daily_pnl[:-1], daily_pnl[1:])

        # Weight concentration (max abs single-stock weight)
        max_w = 0.0
        for day_w in weights:
            for w in day_w:
                if abs(w) > max_w:
                    max_w = abs(w)
        metrics.weight_concentration = max_w

        # IC (Information Coefficient — Spearman rank correlation of alpha vs forward return)
        # Prefer raw alphas (quantitatively correct); fall back to weights proxy
        alpha_signal = alphas if alphas is not None else weights
        ics = []
        for d in range(n_dates - 1):
            day_alpha = alpha_signal[d] if d < len(alpha_signal) else []
            forward_returns = returns[d + 1] if d + 1 < len(returns) else returns[d]
            if not day_alpha:
                continue
            ic = _spearman_r(day_alpha, forward_returns)
            if not math.isnan(ic):
                ics.append(ic)
        if ics:
            metrics.ic_mean = statistics.mean(ics)
            metrics.ic_ir = metrics.ic_mean / max(_safe_stdev(ics), 1e-10)

        # Margin (bps) — simplified: mean daily PnL × 10000
        metrics.margin_bps = mean_pnl * 10000

        # Sub-universe Sharpe (simplified: Sharpe of top half by weight)
        mid = n_symbols // 2
        sub_pnl = []
        for d in range(n_dates):
            sub_pnl.append(sum(weights[d][:mid][s] * returns[d][s] for s in range(min(mid, len(returns[d])))))
        sub_mean = statistics.mean(sub_pnl) if sub_pnl else 0.0
        sub_std = _safe_stdev(sub_pnl)
        metrics.sub_universe_sharpe = (sub_mean / max(sub_std, 1e-10)) * math.sqrt(trading_days_per_year)

        return metrics


# ═══════════════════════════════════════════════════════════════════════════
# Main Engine
# ═══════════════════════════════════════════════════════════════════════════

class LocalBacktestEngine:
    """Unified local backtest engine combining all components.

    Usage::

        engine = LocalBacktestEngine()
        result = engine.evaluate("rank(ts_zscore(close, 20))")
        if result["sharpe"] >= 1.25:
            candidate.pass_local_backtest = True
    """

    def __init__(self, *, seed: int = 42, n_dates: int = 252, n_symbols: int = 500):
        self.data_provider = SyntheticDataProvider()
        self.evaluator = LocalExpressionEvaluator()
        self.portfolio = PortfolioConstructor()
        self.metrics_computer = MetricsComputer()
        self._cache: dict[str, MarketDataFrame] = {}
        self._cache_maxsize: int = 8  # LRU cap to prevent unbounded memory growth
        self.seed = seed
        self.n_dates = n_dates
        self.n_symbols = n_symbols

    @property
    def supported_fields(self) -> set[str]:
        return {str(field).lower() for field in self.data_provider.STANDARD_FIELDS}

    @property
    def supported_operators(self) -> set[str]:
        return {
            "rank",
            "zscore",
            "ts_zscore",
            "ts_mean",
            "ts_std_dev",
            "ts_rank",
            "ts_decay_linear",
            "ts_delta",
            "ts_sum",
            "ts_min",
            "ts_max",
            "ts_corr",
            "group_rank",
            "group_neutralize",
            "winsorize",
            "normalize",
            "abs",
            "neg",
            "log",
            "sign",
            "power",
            "divide",
            "subtract",
            "greater",
            "if_else",
        }

    def generate_data(
        self,
        *,
        fields: list[str] | None = None,
        n_dates: int | None = None,
        n_symbols: int | None = None,
    ) -> MarketDataFrame:
        """Generate synthetic market data for backtesting."""
        return self.data_provider.generate(
            n_dates=n_dates or self.n_dates,
            n_symbols=n_symbols or self.n_symbols,
            fields=fields,
            seed=self.seed,
        )

    def get_data(self, cache_key: str = "default") -> MarketDataFrame:
        """Get or generate cached market data. LRU-evicts when over maxsize."""
        if cache_key in self._cache:
            return self._cache[cache_key]
        # Evict oldest entry if at capacity
        if len(self._cache) >= self._cache_maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[cache_key] = self.generate_data()
        return self._cache[cache_key]

    def evaluate(
        self,
        expression: str,
        *,
        data: MarketDataFrame | None = None,
        cache_key: str = "default",
    ) -> dict[str, Any]:
        """Evaluate an alpha expression through the full local backtest pipeline.

        Args:
            expression: A FASTEXPR expression string.
            data: Optional pre-loaded market data.
            cache_key: Cache key for generated data.

        Returns:
            Dict with 'ok', 'sharpe', 'fitness', 'turnover', etc.,
            plus a 'pass_local' boolean based on BRAIN thresholds.
        """
        data = data or self.get_data(cache_key)

        try:
            # Step 1: Evaluate expression
            alphas = self.evaluator.evaluate(expression, data)

            # Step 2: Construct portfolio weights
            weights = self.portfolio.construct(alphas)

            # Step 3: Compute metrics (pass raw alphas for accurate IC/IR)
            returns = data.get("returns")
            if not returns:
                returns = [[0.0005] * data.n_symbols for _ in range(data.n_dates)]
            metrics = self.metrics_computer.compute(weights, returns, alphas=alphas)

            result = metrics.to_dict()
            result["ok"] = True
            result["expression"] = expression
            result["pass_local"] = (
                metrics.sharpe >= 1.25
                and metrics.fitness >= 1.0
                and metrics.turnover >= 0.01
                and metrics.turnover <= 0.70
                and metrics.weight_concentration <= 0.10
            )
            result["pass_reasons"] = self._pass_reasons(metrics)
            return result

        except (ValueError, TypeError, ZeroDivisionError) as exc:
            # Expected: expression parse/validation errors
            return {
                "ok": False,
                "expression": expression,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "pass_local": False,
            }
        except Exception as exc:
            # Unexpected: log full traceback for debugging
            logger.exception("unexpected error evaluating expression: %s", expression)
            return {
                "ok": False,
                "expression": expression,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "pass_local": False,
            }

    def batch_evaluate(
        self,
        expressions: list[str],
        *,
        data: MarketDataFrame | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate multiple expressions against the same data."""
        data = data or self.get_data()
        results = []
        for expr in expressions:
            result = self.evaluate(expr, data=data)
            results.append(result)
        return results

    def rank_expressions(
        self,
        expressions: list[str],
        *,
        data: MarketDataFrame | None = None,
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Evaluate and rank expressions by fitness score."""
        results = self.batch_evaluate(expressions, data=data)
        valid = [r for r in results if r.get("ok")]
        valid.sort(key=lambda r: r.get("fitness", 0.0), reverse=True)
        return valid[:top_n]

    @staticmethod
    def _pass_reasons(metrics: BacktestMetrics) -> list[str]:
        reasons = []
        if metrics.sharpe >= 1.25:
            reasons.append(f"Sharpe {metrics.sharpe:.2f} >= 1.25")
        else:
            reasons.append(f"Sharpe {metrics.sharpe:.2f} < 1.25 (FAIL)")
        if metrics.fitness >= 1.0:
            reasons.append(f"Fitness {metrics.fitness:.2f} >= 1.0")
        else:
            reasons.append(f"Fitness {metrics.fitness:.2f} < 1.0 (FAIL)")
        if metrics.turnover >= 0.01:
            reasons.append(f"Turnover {metrics.turnover:.2%} >= 1%")
        else:
            reasons.append(f"Turnover {metrics.turnover:.2%} < 1% (FAIL)")
        if metrics.turnover <= 0.70:
            reasons.append(f"Turnover {metrics.turnover:.2%} <= 70%")
        else:
            reasons.append(f"Turnover {metrics.turnover:.2%} > 70% (FAIL)")
        if metrics.weight_concentration <= 0.10:
            reasons.append(f"Concentration {metrics.weight_concentration:.2%} <= 10%")
        else:
            reasons.append(f"Concentration {metrics.weight_concentration:.2%} > 10% (FAIL)")
        return reasons


# ═══════════════════════════════════════════════════════════════════════════
# Math helpers
# ═══════════════════════════════════════════════════════════════════════════

def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return statistics.mean(values)


def _safe_stdev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return statistics.stdev(values)


def _safe_corr(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient, compatible with Python 3.9+."""
    n = min(len(xs), len(ys))
    if n <= 2:
        return 0.0
    return _pearson_r(xs[:n], ys[:n])


def _pearson_r(x: list[float], y: list[float]) -> float:
    """Manual Pearson correlation for Python <3.10 compatibility.

    Caller (_safe_corr) already validated n > 2.
    """
    n = len(x)
    mx = statistics.mean(x)
    my = statistics.mean(y)
    sx = _safe_stdev(x)
    sy = _safe_stdev(y)
    if sx < 1e-10 or sy < 1e-10:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1)
    return cov / (sx * sy)


def _spearman_r(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation."""
    n = min(len(xs), len(ys))
    if n <= 2:
        return 0.0
    rank_x = _rank_values(xs[:n])
    rank_y = _rank_values(ys[:n])
    return _pearson_r(rank_x, rank_y)


def _rank_values(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    for rank, (i, _) in enumerate(indexed):
        ranks[i] = float(rank) / max(1, len(values) - 1)
    return ranks


def _cumsum(values: list[float]) -> list[float]:
    result = []
    total = 0.0
    for v in values:
        total += v
        result.append(total)
    return result

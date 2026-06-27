"""LocalBacktestEngine — unified local backtest engine + MarketDataFrame re-export."""

from __future__ import annotations

import logging
import re
import warnings
from typing import Any

from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.local_backtest_market_data import (
    MarketDataFrame as _MarketDataFrame,  # re-export
)

from .data_provider import SyntheticDataProvider
from .expression_evaluator import LocalExpressionEvaluator
from .metrics import BacktestMetrics, MetricsComputer
from .portfolio import PortfolioConstructor

# P2-14 (2026-06-13): ``MarketDataFrame`` is now defined in
# ``local_backtest_market_data`` and re-exported here for backward
# compatibility with code that imports it from this module.
MarketDataFrame = _MarketDataFrame

logger = logging.getLogger(__name__)

# Locally-implementable operators by LocalExpressionEvaluator.
_FALLBACK_OPERATORS: frozenset[str] = frozenset({
    "rank", "zscore", "ts_zscore", "ts_mean", "ts_std_dev", "ts_rank", "ts_decay_linear",
    "ts_delta", "ts_sum", "ts_min", "ts_max", "ts_corr", "group_rank", "group_neutralize",
    "winsorize", "normalize", "abs", "neg", "reverse", "log", "sign", "power",
    "multiply", "divide", "subtract", "greater", "if_else",
})


def _derive_supported_operators() -> set[str]:
    """Derive supported_operators from the BRAIN capability registry.

    Returns the intersection of locally-implementable operators and the
    official registry. Falls back to ``_FALLBACK_OPERATORS`` with a
    DeprecationWarning when the registry is unavailable.
    """
    registry_ops: set[str] = set()
    try:
        from brain_alpha_ops.data.capability_registry import get_registry
        registry_ops = get_registry().operators()
    except Exception as exc:  # pragma: no cover - defensive import guard
        logger.debug("capability registry unavailable: %s", redact_error_message(exc))

    if not registry_ops:
        warnings.warn(
            "LocalBacktestEngine.supported_operators fell back to hardcoded "
            "fallback; BRAIN capability registry unavailable.",
            DeprecationWarning, stacklevel=2,
        )
        return set(_FALLBACK_OPERATORS)
    return set(_FALLBACK_OPERATORS) & registry_ops


# Module-level derivation; backward-compatible name for ``from .engine import supported_operators``.
supported_operators: set[str] = _derive_supported_operators()


class LocalBacktestEngine:
    """Unified local backtest engine combining all components.

    Usage::

        engine = LocalBacktestEngine()
        result = engine.evaluate("rank(ts_zscore(close, 20))")
        if result["sharpe"] >= 1.25:
            candidate.pass_local_backtest = True
    """

    def __init__(
        self,
        *,
        seed: int = 42,
        n_dates: int = 252,
        n_symbols: int = 500,
    ):
        self.data_provider = SyntheticDataProvider()
        self.evaluator = LocalExpressionEvaluator()
        self.portfolio = PortfolioConstructor()
        self.metrics_computer = MetricsComputer()
        self._cache: dict[str, "MarketDataFrame"] = {}
        self._cache_maxsize: int = (
            8  # LRU cap to prevent unbounded memory growth
        )
        self.seed = seed
        self.n_dates = n_dates
        self.n_symbols = n_symbols

    @property
    def supported_fields(self) -> set[str]:
        return {
            str(field).lower()
            for field in self.data_provider.STANDARD_FIELDS
        }

    @property
    def supported_operators(self) -> set[str]:
        """Return the registry-derived supported operators (module-level)."""
        return set(supported_operators)

    def generate_data(
        self,
        *,
        fields: list[str] | None = None,
        n_dates: int | None = None,
        n_symbols: int | None = None,
    ) -> "MarketDataFrame":
        """Generate synthetic market data for backtesting."""
        return self.data_provider.generate(
            n_dates=n_dates or self.n_dates,
            n_symbols=n_symbols or self.n_symbols,
            fields=fields,
            seed=self.seed,
        )

    def get_data(
        self, cache_key: str = "default"
    ) -> "MarketDataFrame":
        """Get or generate cached market data. LRU-evicts when over maxsize."""
        if cache_key in self._cache:
            return self._cache[cache_key]
        # Evict oldest entry if at capacity
        if len(self._cache) >= self._cache_maxsize:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[cache_key] = self.generate_data()
        return self._cache[cache_key]

    def _extract_fields_from_expression(
        self, expression: str
    ) -> set[str]:
        """Extract field names from a FASTEXPR expression.

        Identifies identifiers that are not function names or constants,
        returning them as potential field references.
        """
        fields: set[str] = set()
        for match in re.finditer(
            r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", expression
        ):
            token = match.group(1)
            if token not in _FALLBACK_OPERATORS:
                fields.add(token)
        return fields

    def get_data_for_expression(
        self, expression: str, cache_key: str = "default"
    ) -> "MarketDataFrame":
        """Get or generate market data that includes all fields used in expression."""
        base_fields = set(self.data_provider.STANDARD_FIELDS)
        expr_fields = self._extract_fields_from_expression(expression)
        extra_fields = expr_fields - base_fields
        if not extra_fields:
            return self.get_data(cache_key)
        all_fields = sorted(base_fields | expr_fields)
        data = self.generate_data(fields=all_fields)
        if len(self._cache) < self._cache_maxsize:
            self._cache[cache_key] = data
        return data

    def evaluate(
        self,
        expression: str,
        *,
        data: "MarketDataFrame | None" = None,
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
        data = data or self.get_data_for_expression(
            expression, cache_key
        )

        try:
            # Step 1: Evaluate expression
            alphas = self.evaluator.evaluate(expression, data)

            # Step 2: Construct portfolio weights
            weights = self.portfolio.construct(alphas)

            # Step 3: Compute metrics (pass raw alphas for accurate IC/IR)
            returns = data.get("returns")
            if not returns:
                returns = [
                    [0.0005] * data.n_symbols
                    for _ in range(data.n_dates)
                ]
            metrics = self.metrics_computer.compute(
                weights, returns, alphas=alphas
            )

            result = metrics.to_dict()
            result["ok"] = True
            result["expression"] = expression
            result.update(self._synthetic_metadata())
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
                "error": redact_error_message(exc),
                "error_type": type(exc).__name__,
                "pass_local": False,
                **self._synthetic_metadata(),
            }
        except (KeyboardInterrupt, SystemExit, TimeoutError):
            raise
        except Exception as exc:
            logger.error(
                "unexpected error evaluating expression: %s; error=%s",
                redact_text(expression, max_length=180),
                redact_error_message(exc),
            )
            return {
                "ok": False,
                "expression": expression,
                "error": redact_error_message(exc),
                "error_type": type(exc).__name__,
                "pass_local": False,
                **self._synthetic_metadata(),
            }

    def batch_evaluate(
        self,
        expressions: list[str],
        *,
        data: "MarketDataFrame | None" = None,
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
        data: "MarketDataFrame | None" = None,
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
            reasons.append(
                f"Sharpe {metrics.sharpe:.2f} < 1.25 (FAIL)"
            )
        if metrics.fitness >= 1.0:
            reasons.append(f"Fitness {metrics.fitness:.2f} >= 1.0")
        else:
            reasons.append(
                f"Fitness {metrics.fitness:.2f} < 1.0 (FAIL)"
            )
        if metrics.turnover >= 0.01:
            reasons.append(
                f"Turnover {metrics.turnover:.2%} >= 1%"
            )
        else:
            reasons.append(
                f"Turnover {metrics.turnover:.2%} < 1% (FAIL)"
            )
        if metrics.turnover <= 0.70:
            reasons.append(
                f"Turnover {metrics.turnover:.2%} <= 70%"
            )
        else:
            reasons.append(
                f"Turnover {metrics.turnover:.2%} > 70% (FAIL)"
            )
        if metrics.weight_concentration <= 0.10:
            reasons.append(
                f"Concentration {metrics.weight_concentration:.2%} <= 10%"
            )
        else:
            reasons.append(
                f"Concentration {metrics.weight_concentration:.2%} > 10% (FAIL)"
            )
        return reasons

    def _synthetic_metadata(self) -> dict[str, Any]:
        return {
            "data_source": "synthetic_prefilter",
            "is_official_equivalent": False,
            "synthetic_config": {
                "seed": self.seed,
                "n_dates": self.n_dates,
                "n_symbols": self.n_symbols,
            },
        }


__all__ = ["LocalBacktestEngine", "MarketDataFrame"]

"""Local synthetic backtest sub-package.

Exposes seven component classes/data via lazy ``__getattr__`` re-export so
that importers of the historical path
``brain_alpha_ops.research.local_backtest_engine`` (and the new path
``brain_alpha_ops.research.local_backtest``) receive the same objects.
"""

from __future__ import annotations

import importlib
from typing import Any

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "SyntheticDataProvider": (
        "brain_alpha_ops.research.local_backtest.data_provider",
        "SyntheticDataProvider",
    ),
    "LocalExpressionEvaluator": (
        "brain_alpha_ops.research.local_backtest.expression_evaluator",
        "LocalExpressionEvaluator",
    ),
    "PortfolioConstructor": (
        "brain_alpha_ops.research.local_backtest.portfolio",
        "PortfolioConstructor",
    ),
    "BacktestMetrics": (
        "brain_alpha_ops.research.local_backtest.metrics",
        "BacktestMetrics",
    ),
    "MetricsComputer": (
        "brain_alpha_ops.research.local_backtest.metrics",
        "MetricsComputer",
    ),
    "LocalBacktestEngine": (
        "brain_alpha_ops.research.local_backtest.engine",
        "LocalBacktestEngine",
    ),
    "MarketDataFrame": (
        "brain_alpha_ops.research.local_backtest.engine",
        "MarketDataFrame",
    ),
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        )
    module_name, attr_name = target
    try:
        module = importlib.import_module(module_name)
        value = getattr(module, attr_name)
        globals()[name] = value
        return value
    except (ImportError, AttributeError) as exc:
        raise type(exc)(
            f"Failed to import {name!r} from {module_name!r}: {exc}"
        ) from exc

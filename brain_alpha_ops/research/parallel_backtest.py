"""Budgeted full-market backtest planning and execution helpers.

Re-export shim. The implementation has been split into the
``brain_alpha_ops.research.parallel_backtest`` subpackage. This module remains
for backward compatibility so existing imports
``from brain_alpha_ops.research.parallel_backtest import ...`` continue to work.

Note: when both ``parallel_backtest.py`` and ``parallel_backtest/__init__.py``
exist, Python resolves ``brain_alpha_ops.research.parallel_backtest`` to the
package directory. The ``parallel_backtest/__init__.py`` is the live module;
this file mirrors its public API for documentation and as a safety net.
"""
from __future__ import annotations

from .parallel_backtest._executor import (  # noqa: F401
    ParallelBacktestBudget,
    ParallelBacktestExecutor,
    ParallelBacktestPlanner,
)
from .parallel_backtest._helpers import (  # noqa: F401
    BacktestJobRunner,
    ProgressCallback,
)

__all__ = [
    "BacktestJobRunner",
    "ParallelBacktestBudget",
    "ParallelBacktestExecutor",
    "ParallelBacktestPlanner",
    "ProgressCallback",
]

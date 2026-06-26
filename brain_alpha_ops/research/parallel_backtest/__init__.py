"""Budgeted full-market backtest planning and execution helpers.

Subpackage split (formerly ``parallel_backtest.py`` monolith, Workstream F3.9):
  - ``_executor``: ``ParallelBacktestBudget``, ``ParallelBacktestPlanner``,
    ``ParallelBacktestExecutor``, and the per-job runner/error helpers
  - ``_helpers``: batching/dedup/event bookkeeping helpers plus the
    ``BacktestJobRunner`` / ``ProgressCallback`` type aliases

Logger name is hardcoded to ``brain_alpha_ops.research.parallel_backtest``
per project convention so log attribution remains stable after the split.

``ParallelBacktestExecutor`` is a *separate* facility from the official 3-slot
simulation scheduler (``ThreeSlotScheduler``); see ``_executor`` for details.
"""

from __future__ import annotations

from ._executor import (
    ParallelBacktestBudget,
    ParallelBacktestExecutor,
    ParallelBacktestPlanner,
    _job_error,
    _run_job,
)
from ._helpers import (
    BacktestJobRunner,
    ProgressCallback,
    _duplicate_text,
    _emit_event,
    _failure_counts,
    _job_batches,
    _unique_text,
)

__all__ = [
    "BacktestJobRunner",
    "ParallelBacktestBudget",
    "ParallelBacktestExecutor",
    "ParallelBacktestPlanner",
    "ProgressCallback",
]

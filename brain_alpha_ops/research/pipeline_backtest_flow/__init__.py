"""Re-export from the ``pipeline_backtest_flow`` subpackage.

The original monolithic ``pipeline_backtest_flow.py`` was split into the
``brain_alpha_ops.research.pipeline_backtest_flow`` subpackage. This
module re-exports the full public API surface so the legacy import
``from brain_alpha_ops.research.pipeline_backtest_flow import
PipelineBacktestMixin`` continues to work, and re-exports the private
sub-mixin symbols so tests that monkeypatch
``brain_alpha_ops.research.pipeline_backtest_flow._XxxMixin`` keep
functioning.

Sub-modules (consolidated):
  - ``pipeline_backtest_flow``       : ``PipelineBacktestMixin`` class
    assembly plus ``_BacktestSlotMixin`` (slot filling/submission) and
    ``_BacktestPollMixin`` (due-backtest polling loop)
  - ``pipeline_backtest_flow_mixins``: ``_BacktestChecksMixin``
    (alpha-checks + robustness checks; also defines the package ``logger``)
    and ``_BacktestFinalizationMixin`` (candidate finalization, simulation
    retry, fusion-candidate factories)
"""

from __future__ import annotations

from .pipeline_backtest_flow import (  # noqa: F401
    PipelineBacktestMixin,
    _BacktestSlotMixin,
    _BacktestPollMixin,
)
from .pipeline_backtest_flow_mixins import (  # noqa: F401
    _BacktestChecksMixin,
    _BacktestFinalizationMixin,
    logger,
)

__all__ = [
    # Public API
    "PipelineBacktestMixin",
    # Module-level logger (preserved from the original monolith)
    "logger",
    # Private sub-mixins re-exported for test monkeypatch compatibility.
    "_BacktestSlotMixin",
    "_BacktestPollMixin",
    "_BacktestChecksMixin",
    "_BacktestFinalizationMixin",
]

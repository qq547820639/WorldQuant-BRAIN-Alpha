"""Re-export from the ``pipeline_backtest_flow`` subpackage.

The original monolithic ``pipeline_backtest_flow.py`` was split into the
``brain_alpha_ops.research.pipeline_backtest_flow`` subpackage. This
module re-exports the full public API surface so the legacy import
``from brain_alpha_ops.research.pipeline_backtest_flow import
PipelineBacktestMixin`` continues to work, and re-exports the private
sub-mixin symbols so tests that monkeypatch
``brain_alpha_ops.research.pipeline_backtest_flow._XxxMixin`` keep
functioning.

Sub-modules:
  - ``_slot_submission_mixin`` : ``_BacktestSlotMixin`` carrying
    ``_fill_backtest_slots``, ``_next_backtest_candidate`` and
    ``_handle_slot_submit_error`` (backtest slot filling & submission)
  - ``_polling_mixin``          : ``_BacktestPollMixin`` carrying
    ``_poll_due_backtests`` and ``_poll_interval_seconds`` (due-backtest
    polling loop and unified poll-interval accessor)
  - ``_checks_mixin``           : ``_BacktestChecksMixin`` carrying
    ``_run_alpha_checks`` and ``_run_robustness_checks`` (post-simulation
    BRAIN-standard alpha checks and deterministic robustness reports);
    also defines the package ``logger``
  - ``_finalization_mixin``     : ``_BacktestFinalizationMixin`` carrying
    ``_finalize_backtest_candidate``, ``_simulation_retry_count``,
    ``_retry_simulation_candidate``,
    ``_create_secondary_fusion_candidate`` and
    ``_try_fusion_top_candidates`` (candidate finalization, simulation
    retry, and fusion-candidate factories)
  - ``_mixin``                  : ``PipelineBacktestMixin`` class assembly
    composed from the four sub-mixins above
"""

from __future__ import annotations

from brain_alpha_ops.research.pipeline_backtest_flow._slot_submission_mixin import (  # noqa: F401
    _BacktestSlotMixin,
)
from brain_alpha_ops.research.pipeline_backtest_flow._polling_mixin import (  # noqa: F401
    _BacktestPollMixin,
)
from brain_alpha_ops.research.pipeline_backtest_flow._checks_mixin import (  # noqa: F401
    _BacktestChecksMixin,
    logger,
)
from brain_alpha_ops.research.pipeline_backtest_flow._finalization_mixin import (  # noqa: F401
    _BacktestFinalizationMixin,
)
from brain_alpha_ops.research.pipeline_backtest_flow._mixin import (  # noqa: F401
    PipelineBacktestMixin,
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

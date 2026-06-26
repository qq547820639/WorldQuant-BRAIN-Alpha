"""Re-export from the ``backtest_flow_service`` subpackage.

The original monolithic ``backtest_flow_service.py`` was split into:
  - ``_slot_submission`` : ``_SlotSubmissionMixin`` carrying
                          ``_fill_backtest_slots``,
                          ``_next_backtest_candidate`` and
                          ``_handle_slot_submit_error``
  - ``_polling``         : ``_PollingMixin`` carrying
                          ``_poll_due_backtests`` and
                          ``_poll_interval_seconds``
  - ``_checks``          : ``_ChecksMixin`` carrying
                          ``_run_alpha_checks`` and
                          ``_run_robustness_checks`` plus the
                          module-level ``logger`` (hardcoded name)
  - ``_finalization``    : ``_FinalizationMixin`` carrying
                          ``_finalize_backtest_candidate``,
                          ``_simulation_retry_count``,
                          ``_retry_simulation_candidate``,
                          ``_create_secondary_fusion_candidate`` and
                          ``_try_fusion_top_candidates``
  - ``_service``         : ``BacktestFlowService`` class assembly that
                          mixes in the four responsibility mixins

This file re-exports the full public API surface so legacy imports
``from brain_alpha_ops.research.backtest_flow_service import ...``
continue to work.
"""

from __future__ import annotations

from brain_alpha_ops.research.backtest_flow_service._checks import (  # noqa: F401
    _ChecksMixin,
    _blocked_gate,
    logger,
)
from brain_alpha_ops.research.backtest_flow_service._finalization import (  # noqa: F401
    _FinalizationMixin,
)
from brain_alpha_ops.research.backtest_flow_service._polling import (  # noqa: F401
    _PollingMixin,
)
from brain_alpha_ops.research.backtest_flow_service._service import (  # noqa: F401
    BacktestFlowService,
)
from brain_alpha_ops.research.backtest_flow_service._slot_submission import (  # noqa: F401
    _SlotSubmissionMixin,
    _expr_key,
)

__all__ = [
    # Public API
    "BacktestFlowService",
    "logger",
    # Private mixins (re-exported for test monkeypatch compatibility)
    "_SlotSubmissionMixin",
    "_PollingMixin",
    "_ChecksMixin",
    "_FinalizationMixin",
    # Private aliases (re-exported to preserve original module surface)
    "_blocked_gate",
    "_expr_key",
]

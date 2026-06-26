"""``PipelineBacktestMixin`` class assembly.

Extracted from the original ``pipeline_backtest_flow.py`` monolith. The
slot-submission, polling, post-simulation checks and finalization/retry/
fusion behaviours are split into the four sub-mixins below and assembled
here into the public ``PipelineBacktestMixin`` class so the legacy import
``from brain_alpha_ops.research.pipeline_backtest_flow import
PipelineBacktestMixin`` keeps working unchanged.
"""

from __future__ import annotations

from brain_alpha_ops.research.pipeline_backtest_flow._slot_submission_mixin import _BacktestSlotMixin
from brain_alpha_ops.research.pipeline_backtest_flow._polling_mixin import _BacktestPollMixin
from brain_alpha_ops.research.pipeline_backtest_flow._checks_mixin import _BacktestChecksMixin
from brain_alpha_ops.research.pipeline_backtest_flow._finalization_mixin import _BacktestFinalizationMixin


class PipelineBacktestMixin(
    _BacktestSlotMixin,
    _BacktestPollMixin,
    _BacktestChecksMixin,
    _BacktestFinalizationMixin,
):
    """Backtest slot, polling, finalization, and fusion helpers for
    ``AlphaResearchPipeline``.

    Assembled from the four responsibility-specific sub-mixins so each
    submodule stays under the per-file line budget while the public class
    API remains identical to the original monolith.
    """

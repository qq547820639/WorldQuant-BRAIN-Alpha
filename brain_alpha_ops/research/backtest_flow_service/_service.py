"""``BacktestFlowService`` class assembly.

Extracted from the original ``backtest_flow_service.py`` monolith. The
service orchestrates backtest slot submission, polling, alpha/robustness
checks, and finalization for ``AlphaResearchPipeline``. The method bodies
live in four responsibility mixins (``_SlotSubmissionMixin``,
``_PollingMixin``, ``_ChecksMixin``, ``_FinalizationMixin``) which are
mixed in here to keep this file under the per-submodule line budget while
preserving the public class API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from brain_alpha_ops.research.backtest_flow_service._checks import _ChecksMixin
from brain_alpha_ops.research.backtest_flow_service._finalization import (
    _FinalizationMixin,
)
from brain_alpha_ops.research.backtest_flow_service._polling import _PollingMixin
from brain_alpha_ops.research.backtest_flow_service._slot_submission import (
    _SlotSubmissionMixin,
)

if TYPE_CHECKING:
    from brain_alpha_ops.research.pipeline import AlphaResearchPipeline


class BacktestFlowService(
    _SlotSubmissionMixin,
    _PollingMixin,
    _ChecksMixin,
    _FinalizationMixin,
):
    """Standalone backtest flow service using composition.

    Takes a pipeline instance and accesses its state through the reference.
    """

    def __init__(self, pipeline: AlphaResearchPipeline) -> None:
        self._pipeline = pipeline

"""``PipelineRuntimeMixin`` class definition.

Assembles the Mixin classes extracted from the original ``pipeline_runtime.py``
monolith into the final ``PipelineRuntimeMixin`` class.
"""

from __future__ import annotations

from ._records_mixin import PipelineRecordsMixin
from ._strategy_plugins_mixin import PipelineStrategyPluginsMixin
from ._backtest_recovery_mixin import PipelineBacktestRecoveryMixin
from ._official_calls_mixin import PipelineOfficialCallsMixin
from ._observability_mixin import PipelineObservabilityMixin
from ._runtime_helpers_mixin import PipelineRuntimeHelpersMixin


class PipelineRuntimeMixin(
    PipelineRecordsMixin,
    PipelineStrategyPluginsMixin,
    PipelineBacktestRecoveryMixin,
    PipelineOfficialCallsMixin,
    PipelineObservabilityMixin,
    PipelineRuntimeHelpersMixin,
):
    """Persistence, observability, and runtime helpers for AlphaResearchPipeline."""

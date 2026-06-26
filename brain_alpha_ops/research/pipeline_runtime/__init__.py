"""Persistence, observability, and runtime helpers for AlphaResearchPipeline.

Subpackage split (formerly ``pipeline_runtime.py`` monolith):
  - ``_records_mixin``: ``PipelineRecordsMixin`` with lifecycle/backtest
    recording and scientific-audit feedback
  - ``_strategy_plugins_mixin``: ``PipelineStrategyPluginsMixin`` with
    strategy plugin load/summary/notify helpers
  - ``_backtest_recovery_mixin``: ``PipelineBacktestRecoveryMixin`` with
    persisted backtest slot recovery
  - ``_official_calls_mixin``: ``PipelineOfficialCallsMixin`` with
    official-call halt/defer/error-context/retry helpers
  - ``_observability_mixin``: ``PipelineObservabilityMixin`` with
    observability throttle refresh and generation-guidance application
  - ``_runtime_helpers_mixin``: ``PipelineRuntimeHelpersMixin`` with
    archive/stop/sleep/event/progress helpers
  - ``_class``: ``PipelineRuntimeMixin`` class assembly
"""

from __future__ import annotations

from ._class import PipelineRuntimeMixin

__all__ = ["PipelineRuntimeMixin"]

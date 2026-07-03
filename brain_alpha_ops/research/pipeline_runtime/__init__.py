"""Persistence, observability, and runtime helpers for AlphaResearchPipeline.

Consolidated from the original ``pipeline_runtime.py`` monolith into:
  - ``runtime``: ``PipelineRecordsMixin``, ``PipelineRuntimeHelpersMixin``,
    and the final ``PipelineRuntimeMixin`` class assembly
  - ``runtime_mixins``: ``PipelineStrategyPluginsMixin``,
    ``PipelineBacktestRecoveryMixin``, ``PipelineOfficialCallsMixin``,
    ``PipelineObservabilityMixin``
"""

from __future__ import annotations

from .runtime import PipelineRuntimeMixin

__all__ = ["PipelineRuntimeMixin"]

"""Composition-based service accessor for AlphaResearchPipeline.

This module provides PipelineServices, a lightweight proxy that delegates
to the pipeline's existing factory methods. This is the recommended pattern
for new code that needs to interact with pipeline services.

Usage:
    services = pipeline.services
    candidates = services.candidate_pool.filter(pool, ...)
    services.backtest_submission.submit(candidates, ...)
"""

from __future__ import annotations

from typing import Any


class PipelineServices:
    """Lazy proxy for pipeline service objects.

    This replaces the 10-Mixin inheritance chain with explicit service
    ownership via composition. Services are created on first access and
    cached for subsequent use.

    New code should prefer accessing services through this container
    rather than inheriting from Mixin classes.
    """

    def __init__(self, pipeline: Any) -> None:
        object.__setattr__(self, "_pipeline", pipeline)
        object.__setattr__(self, "_cache", {})

    def _get(self, name: str, factory_method: str) -> Any:
        cache = object.__getattribute__(self, "_cache")
        if name not in cache:
            pipeline = object.__getattribute__(self, "_pipeline")
            factory = getattr(pipeline, factory_method)
            cache[name] = factory()
        return cache[name]

    @property
    def candidate_pool(self):
        return self._get("candidate_pool", "_candidate_pool_service")

    @property
    def generation_phase(self):
        return self._get("generation_phase", "_generation_phase_service")

    @property
    def dataset_selection(self):
        return self._get("dataset_selection", "_dataset_selection_service")

    @property
    def backtest_submission(self):
        return self._get("backtest_submission", "_backtest_submission_service")

    @property
    def backtest_polling(self):
        return self._get("backtest_polling", "_backtest_polling_service")

    @property
    def backtest_finalization(self):
        return self._get("backtest_finalization", "_backtest_finalization_service")

    @property
    def batch_backtest(self):
        return self._get("batch_backtest", "_batch_backtest_coordinator")

    @property
    def official_workflow(self):
        return self._get("official_workflow", "_official_workflow_service")

    @property
    def experience_feedback(self):
        return self._get("experience_feedback", "_experience_feedback_service")

    @property
    def fusion_candidates(self):
        return self._get("fusion_candidates", "_fusion_candidate_service")

    @property
    def secondary_fusion(self):
        return self._get("secondary_fusion", "_secondary_fusion_service")

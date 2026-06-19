"""Composition-based service accessor for AlphaResearchPipeline.

This module provides PipelineServices, a lazy proxy that creates and
caches service instances on first access. This is the recommended pattern
for all code that needs to interact with pipeline services.

Usage:
    services = pipeline.services
    candidates = services.candidate_pool.filter(pool, ...)
    services.backtest_submission.submit(candidates, ...)

── Coverage status (A-04, updated 2026-06-19) ──

  PipelineServices provides access to all 18 pipeline services through
  two mechanism groups:

  Group A — Mixin factory methods (pipeline_services.py):
    candidate_pool, generation_phase, dataset_selection,
    backtest_submission, backtest_polling, backtest_finalization,
    batch_backtest, official_workflow, experience_feedback,
    fusion_candidates, secondary_fusion

  Group B — Direct instantiation:
    strategy, submission_gate, context_sync,
    official_validation, backtest_flow, runtime,
    legacy_simulation
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

    # ═══════════════════════════════════════════════════════════
    # Group A: Mixin factory methods (pipeline_services.py)
    # ═══════════════════════════════════════════════════════════

    @property
    def candidate_pool(self):
        if "candidate_pool" not in self._cache:
            from .candidate_pool_service_ import CandidatePoolService_
            self._cache["candidate_pool"] = CandidatePoolService_(self._pipeline)
        return self._cache["candidate_pool"]

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

    # ═══════════════════════════════════════════════════════════
    # Group B: Directly instantiated services (formerly delegate)
    #
    # Each property lazily imports and instantiates the
    # corresponding service class, passing the pipeline reference.
    # This replaces the thin delegate wrappers that were removed
    # from AlphaResearchPipeline.
    # ═══════════════════════════════════════════════════════════

    @property
    def strategy(self):
        if "strategy" not in self._cache:
            from .strategy_service import StrategyService
            self._cache["strategy"] = StrategyService(self._pipeline)
        return self._cache["strategy"]

    @property
    def submission_gate(self):
        if "submission_gate" not in self._cache:
            from .submission_gate_service import SubmissionGateService
            self._cache["submission_gate"] = SubmissionGateService(self._pipeline)
        return self._cache["submission_gate"]

    @property
    def context_sync(self):
        if "context_sync" not in self._cache:
            from .context_sync_service import ContextSyncService
            self._cache["context_sync"] = ContextSyncService(self._pipeline)
        return self._cache["context_sync"]

    @property
    def official_validation(self):
        if "official_validation" not in self._cache:
            from .official_validation_service import OfficialValidationService_
            self._cache["official_validation"] = OfficialValidationService_(self._pipeline)
        return self._cache["official_validation"]

    @property
    def backtest_flow(self):
        if "backtest_flow" not in self._cache:
            from .backtest_flow_service import BacktestFlowService
            self._cache["backtest_flow"] = BacktestFlowService(self._pipeline)
        return self._cache["backtest_flow"]

    @property
    def runtime(self):
        if "runtime" not in self._cache:
            from .runtime_service import RuntimeService
            self._cache["runtime"] = RuntimeService(self._pipeline)
        return self._cache["runtime"]

    @property
    def legacy_simulation(self):
        if "legacy_simulation" not in self._cache:
            from .legacy_simulation_service import LegacySimulationService
            self._cache["legacy_simulation"] = LegacySimulationService(self._pipeline)
        return self._cache["legacy_simulation"]

"""``DecoupledCoordinator`` and ``DecoupledPipeline`` classes.

The coordinator orchestrates the 4 decoupled workers (production, filter,
optimization, validation) with shared state.  The pipeline is the
top-level entry point that wires up all components and runs the
research lifecycle.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from brain_alpha_ops.models import Candidate, PipelineResult, new_id
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.pipeline_helpers import rank_candidates
from brain_alpha_ops.research.simulation_scheduler import ThreeSlotScheduler

from brain_alpha_ops.research.decoupled_pipeline._state import SharedState, WorkerState
from brain_alpha_ops.research.decoupled_pipeline._workers import (
    FilterWorker,
    ProductionWorker,
)
from brain_alpha_ops.research.decoupled_pipeline._workers_ext import (
    OptimizationWorker,
    ValidationWorker,
)

# Hardcoded logger name — preserves original ``brain_alpha_ops.research.decoupled_pipeline``
# identity for test caplog filtering.
logger = logging.getLogger("brain_alpha_ops.research.decoupled_pipeline")


@dataclass
class DecoupledCoordinator:
    """Orchestrates the 4 decoupled workers with shared state.

    Manages worker lifecycle (start/stop), monitors health, and
    provides a unified interface for the pipeline to interact with.
    """

    shared: SharedState
    production: ProductionWorker
    filter: FilterWorker
    optimization: OptimizationWorker
    validation: ValidationWorker
    event_fn: Callable[..., None]
    stop_fn: Callable[[], bool]

    def start_all(self) -> None:
        self.production.start()
        self.filter.start()
        self.optimization.start()
        self.validation.start()
        self.event_fn(
            "coordinator_started",
            "All decoupled workers started.",
            level="INFO",
        )

    def stop_all(self) -> None:
        self.production.stop()
        self.filter.stop()
        self.optimization.stop()
        self.validation.stop()
        self.event_fn(
            "coordinator_stopped",
            "All decoupled workers stopped.",
            level="INFO",
        )

    def status(self) -> dict[str, Any]:
        return {
            "production": self.production.status(),
            "filter": self.filter.status(),
            "optimization": self.optimization.status(),
            "validation": self.validation.status(),
            "pool_size": len(self.shared.pool_by_expression),
            "produced_total": self.shared.produced_count,
            "simulated_total": self.shared.officially_simulated_count,
            "submitted_total": self.shared.submitted_count,
        }

    def wait_for_completion(self, timeout: float = 0.0) -> None:
        """Wait until all workers finish or timeout (0 = until stopped)."""
        deadline = time.monotonic() + timeout if timeout > 0 else float("inf")
        while time.monotonic() < deadline:
            if self.stop_fn():
                break
            if all(
                w.state in (WorkerState.STOPPED, WorkerState.IDLE)
                for w in [self.production, self.filter, self.optimization, self.validation]
            ):
                break
            time.sleep(1.0)


@dataclass
class DecoupledPipeline:
    """Decoupled alpha research pipeline.

    Replaces the serial pattern with continuous concurrent workers:
      - ProductionWorker generates candidates continuously
      - FilterWorker scores and filters candidates
      - OptimizationWorker optimizes failed candidates
      - ValidationWorker runs official simulations via ThreeSlotScheduler
      - DecoupledCoordinator orchestrates everything

    Official simulation results write back to shared state but do NOT
    block candidate production.

    Usage:
        pipeline = DecoupledPipeline(config=config, api=api, ...)
        result = pipeline.run()
    """

    config: Any  # OpsConfig
    api: Any  # BrainAPI
    execution_backend: Any = None
    progress_callback: Callable[[dict], None] | None = None
    stop_callback: Callable[[], bool] | None = None
    experiment_id: str = ""
    experiment_version: str = ""

    def run(self, *, auto_submit: bool = False) -> PipelineResult:
        """Run the decoupled pipeline."""
        run_id = new_id("run")
        self._run_id = run_id

        self._event("run_started", "Decoupled research pipeline started.")

        # Authenticate
        self.api.authenticate()

        # Load context
        from ..pipeline_context_sync import PipelineContextSyncMixin
        from ..production_context import build_production_context

        # Build shared state
        shared = SharedState()

        # Initialize generator
        from ..generator import CandidateGenerator
        generator = CandidateGenerator()

        def cycle_fn(cycle: int, config: Any) -> list[Candidate]:
            return generator.generate_batch(
                count=config.budget.max_candidates_per_cycle,
                cycle=cycle,
            )

        # Initialize scoring
        from ..scoring import score_candidate
        from ..alpha_checks import AlphaCheckRegistry

        check_registry = AlphaCheckRegistry()
        check_registry.build_default_checks()

        # Initialize scheduler
        def settings_provider() -> dict[str, Any]:
            return self.config.settings.to_platform_dict()

        scheduler = ThreeSlotScheduler(
            api=self.api,
            settings_provider=settings_provider,
            event_callback=self._event,
            stop_callback=self.stop_callback or (lambda: False),
            max_slots=getattr(self.config.budget, "max_official_concurrent_simulations", 3),
        )

        # Build workers
        production = ProductionWorker(
            shared=shared,
            generator=generator,
            config=self.config,
            cycle_fn=cycle_fn,
            event_fn=self._event,
            stop_fn=self.stop_callback or (lambda: False),
            target_pool_size=getattr(self.config.budget, "retained_alpha_pool_size", 10),
        )

        filter_worker = FilterWorker(
            shared=shared,
            scoring_config=self.config.scoring,
            check_registry=check_registry,
            config=self.config,
            event_fn=self._event,
            stop_fn=self.stop_callback or (lambda: False),
        )

        optimization = OptimizationWorker(
            shared=shared,
            optimizer=None,  # Will be set up later
            event_fn=self._event,
            stop_fn=self.stop_callback or (lambda: False),
        )

        validation = ValidationWorker(
            shared=shared,
            scheduler=scheduler,
            accepted_candidates=[],
            event_fn=self._event,
            stop_fn=self.stop_callback or (lambda: False),
            auto_submit=auto_submit,
        )

        # Build coordinator
        coordinator = DecoupledCoordinator(
            shared=shared,
            production=production,
            filter=filter_worker,
            optimization=optimization,
            validation=validation,
            event_fn=self._event,
            stop_fn=self.stop_callback or (lambda: False),
        )

        # Start all workers
        coordinator.start_all()

        # Run until stopped
        try:
            coordinator.wait_for_completion(
                timeout=getattr(self.config.budget, "max_pipeline_runtime_seconds", 3600)
            )
        finally:
            coordinator.stop_all()

        # Build result
        final_candidates = rank_candidates(
            shared.accepted_candidates + list(shared.pool_by_expression.values())
        )
        summary = self._build_summary(final_candidates, shared)
        result = PipelineResult(
            run_id=run_id,
            candidates=final_candidates,
            events=shared.events,
            summary=summary,
        )

        self._event("run_completed", "Decoupled pipeline completed.", data=summary)
        return result

    def _event(self, event: str, message: str, **kwargs: Any) -> None:
        level = kwargs.pop("level", "INFO")
        data = kwargs.pop("data", None)
        if self.progress_callback:
            self.progress_callback({
                "event": event,
                "message": message,
                "level": level,
                "data": data,
            })

    def _build_summary(
        self, candidates: list[Candidate], shared: SharedState
    ) -> dict[str, Any]:
        return {
            "run_id": self._run_id,
            "total_candidates": len(candidates),
            "produced": shared.produced_count,
            "filtered": shared.filtered_count,
            "officially_simulated": shared.officially_simulated_count,
            "submitted": shared.submitted_count,
            "pool_size": len(shared.pool_by_expression),
        }

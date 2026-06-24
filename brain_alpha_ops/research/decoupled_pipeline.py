"""Decoupled alpha research pipeline (DEFECT-009).

Replaces the serial 'generate → Top3 official sim → quality check → optimize/refill'
pattern with a continuous production/filtered/optimized/validated architecture:

  Production   → continuously generates candidates to maintain pool capacity
  Filter       → fast local scoring + quality gates filter/sort/optimize
  Optimization → runs optimization on failed candidates (independent)
  Validation   → consumes TopK from filtered pool for official simulation
  Coordinator  → orchestrates the 4 workers with shared state

Official simulation results write back to trigger state update, scoring
recalibration, and optimization direction adjustment, but do NOT block
candidate production.

Usage:
    pipeline = DecoupledPipeline(config=config, api=api, ...)
    result = pipeline.run()
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.models import Candidate, PipelineResult, new_id
from brain_alpha_ops.redaction import redact_error_message

from .pipeline_helpers import rank_candidates
from .simulation_scheduler import ThreeSlotScheduler, SlotOutcome

logger = logging.getLogger(__name__)


class WorkerState(enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class SharedState:
    """Thread-safe shared state between all pipeline workers."""

    pool_by_expression: dict[str, Candidate] = field(default_factory=dict)
    blocked_expressions: set[str] = field(default_factory=set)
    accepted_candidates: list[Candidate] = field(default_factory=list)
    archive_stats: dict[str, int] = field(default_factory=dict)
    archive_samples: list[Candidate] = field(default_factory=list)

    produced_count: int = 0
    filtered_count: int = 0
    officially_simulated_count: int = 0
    submitted_count: int = 0

    events: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def get_ranked_pool(self) -> list[Candidate]:
        with self._lock:
            return rank_candidates(list(self.pool_by_expression.values()))

    def add_to_pool(self, candidates: list[Candidate]) -> int:
        added = 0
        with self._lock:
            for c in candidates:
                key = c.expression.strip()
                if key not in self.pool_by_expression:
                    self.pool_by_expression[key] = c
                    added += 1
        return added

    def remove_from_pool(self, keys: list[str]) -> None:
        with self._lock:
            for key in keys:
                self.pool_by_expression.pop(key, None)

    def record_event(self, event: str, message: str, **kwargs: Any) -> None:
        with self._lock:
            self.events.append({
                "event": event,
                "message": message,
                "timestamp": time.time(),
                **kwargs,
            })


@dataclass
class ProductionWorker:
    """Continuously generates candidates to maintain pool capacity.

    Runs in its own thread, generating new candidates when pool size
    drops below the target threshold. Generation speed adapts based
    on pool size and production rate.
    """

    shared: SharedState
    generator: Any  # CandidateGenerator
    config: Any  # OpsConfig
    cycle_fn: Callable[[int, Any], list[Candidate]]
    event_fn: Callable[..., None]
    stop_fn: Callable[[], bool]
    target_pool_size: int = 10
    min_pool_size: int = 3
    _state: WorkerState = field(default=WorkerState.IDLE)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def start(self) -> None:
        self._state = WorkerState.RUNNING
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="production-worker"
        )
        self._thread.start()

    def stop(self) -> None:
        self._state = WorkerState.STOPPED
        if self._thread:
            self._thread.join(timeout=30)

    def _run_loop(self) -> None:
        cycle = 0
        while self._state == WorkerState.RUNNING and not self.stop_fn():
            pool_size = len(self.shared.pool_by_expression)
            if pool_size < self.target_pool_size:
                need = self.target_pool_size - pool_size
                cycle += 1
                try:
                    candidates = self.cycle_fn(cycle, self.config)
                    if candidates:
                        added = self.shared.add_to_pool(candidates[:need * 2])
                        self.shared.produced_count += added
                        self.event_fn(
                            "production_batch",
                            f"Generated {len(candidates)} candidates, added {added} to pool",
                            level="INFO",
                            data={"pool_size": len(self.shared.pool_by_expression)},
                        )
                except Exception as exc:
                    self.event_fn(
                        "production_error",
                        f"Generation failed: {redact_error_message(exc)}",
                        level="WARN",
                    )

            # Adaptive sleep: faster when pool is low
            sleep_time = 5.0 if pool_size < self.min_pool_size else 15.0
            time.sleep(sleep_time)

    @property
    def state(self) -> WorkerState:
        return self._state

    def status(self) -> dict[str, Any]:
        return {
            "worker": "production",
            "state": self._state.value,
            "pool_size": len(self.shared.pool_by_expression),
            "produced_count": self.shared.produced_count,
        }


@dataclass
class FilterWorker:
    """Runs local scoring + quality gates on new candidates.

    Continuously scans for unfiltered candidates in the pool and
    applies scoring, quality gates, and sorting. Failed candidates
    are flagged for optimization.
    """

    shared: SharedState
    scoring_config: Any  # ScoringConfig
    check_registry: Any  # AlphaCheckRegistry
    config: Any  # OpsConfig
    event_fn: Callable[..., None]
    stop_fn: Callable[[], bool]
    _state: WorkerState = field(default=WorkerState.IDLE)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _processed_keys: set[str] = field(default_factory=set)

    def start(self) -> None:
        self._state = WorkerState.RUNNING
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="filter-worker"
        )
        self._thread.start()

    def stop(self) -> None:
        self._state = WorkerState.STOPPED
        if self._thread:
            self._thread.join(timeout=30)

    def _run_loop(self) -> None:
        while self._state == WorkerState.RUNNING and not self.stop_fn():
            candidates = self.shared.get_ranked_pool()
            new_candidates = [
                c for c in candidates
                if c.expression.strip() not in self._processed_keys
            ]

            for candidate in new_candidates[:20]:  # Process up to 20 per tick
                self._filter_candidate(candidate)
                self._processed_keys.add(candidate.expression.strip())

            # Prune pool of low-quality candidates
            self._prune_low_quality()

            time.sleep(10.0)

    def _filter_candidate(self, candidate: Candidate) -> None:
        """Apply local scoring and quality gates to a single candidate."""
        try:
            # Basic quality checks
            if not candidate.expression or len(candidate.expression.strip()) < 5:
                candidate.lifecycle_status = "local_prefilter_rejected"
                return

            # Score the candidate
            from .scoring import score_candidate
            scores = score_candidate(candidate, self.scoring_config)
            candidate.local_quality = scores
            candidate.lifecycle_status = "locally_scored"

            # Check quality thresholds
            min_score = getattr(self.config.budget, "min_local_quality_score", 4.0)
            if scores.get("composite_score", 0) < min_score:
                candidate.lifecycle_status = "local_quality_rejected"
                candidate.gate = {
                    "submission_ready": False,
                    "reason": f"composite_score {scores.get('composite_score', 0):.2f} < {min_score}",
                }

        except Exception as exc:
            self.event_fn(
                "filter_error",
                f"Filter failed for {candidate.alpha_id}: {redact_error_message(exc)}",
                level="WARN",
            )

    def _prune_low_quality(self) -> None:
        """Remove candidates below quality thresholds from pool."""
        to_remove = []
        with self.shared._lock:
            for key, candidate in self.shared.pool_by_expression.items():
                if candidate.lifecycle_status in (
                    "local_prefilter_rejected",
                    "local_quality_rejected",
                ):
                    to_remove.append(key)

        if to_remove:
            self.shared.remove_from_pool(to_remove)
            self.shared.archive_stats["local_pruned"] = (
                self.shared.archive_stats.get("local_pruned", 0) + len(to_remove)
            )

    @property
    def state(self) -> WorkerState:
        return self._state

    def status(self) -> dict[str, Any]:
        return {
            "worker": "filter",
            "state": self._state.value,
            "processed_count": len(self._processed_keys),
            "filtered_count": self.shared.filtered_count,
        }


@dataclass
class OptimizationWorker:
    """Runs optimization on failed/rejected candidates.

    Monitors the pool for candidates with optimization potential and
    generates mutations or parameter adjustments. Runs independently
    of the main pipeline to avoid blocking production.
    """

    shared: SharedState
    optimizer: Any  # IterativeOptimizer
    event_fn: Callable[..., None]
    stop_fn: Callable[[], bool]
    _state: WorkerState = field(default=WorkerState.IDLE)
    _thread: threading.Thread | None = field(default=None, repr=False)

    def start(self) -> None:
        self._state = WorkerState.RUNNING
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="optimization-worker"
        )
        self._thread.start()

    def stop(self) -> None:
        self._state = WorkerState.STOPPED
        if self._thread:
            self._thread.join(timeout=30)

    def _run_loop(self) -> None:
        while self._state == WorkerState.RUNNING and not self.stop_fn():
            candidates = self.shared.get_ranked_pool()

            # Find candidates suitable for optimization
            optimizable = [
                c for c in candidates
                if self._is_optimizable(c)
            ][:5]  # Optimize up to 5 per tick

            for candidate in optimizable:
                self._optimize_candidate(candidate)

            time.sleep(30.0)  # Optimization is slower

    def _is_optimizable(self, candidate: Candidate) -> bool:
        return (
            candidate.lifecycle_status in (
                "local_quality_rejected",
                "simulation_failed",
                "simulation_poll_failed",
            )
            and candidate.submission.get("optimization_attempts", 0) < 3
        )

    def _optimize_candidate(self, candidate: Candidate) -> None:
        try:
            if self.optimizer:
                optimized = self.optimizer.optimize(candidate)
                if optimized:
                    self.shared.add_to_pool([optimized])
                    self.event_fn(
                        "optimization_created",
                        f"Optimization created variant for {candidate.alpha_id}",
                        level="INFO",
                    )
            candidate.submission["optimization_attempts"] = (
                candidate.submission.get("optimization_attempts", 0) + 1
            )
        except Exception as exc:
            self.event_fn(
                "optimization_error",
                f"Optimization failed: {redact_error_message(exc)}",
                level="WARN",
            )

    @property
    def state(self) -> WorkerState:
        return self._state

    def status(self) -> dict[str, Any]:
        return {
            "worker": "optimization",
            "state": self._state.value,
        }


@dataclass
class ValidationWorker:
    """Consumes TopK candidates from filtered pool for official simulation.

    Uses ThreeSlotScheduler for concurrent simulation management.
    Official results write back to SharedState and trigger scoring
    recalibration, but do NOT block production.
    """

    shared: SharedState
    scheduler: ThreeSlotScheduler
    accepted_candidates: list[Candidate]
    event_fn: Callable[..., None]
    stop_fn: Callable[[], bool]
    auto_submit: bool = False
    _state: WorkerState = field(default=WorkerState.IDLE)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _finalize_fn: Callable[..., int] | None = None

    def set_finalize_fn(self, fn: Callable[..., int]) -> None:
        self._finalize_fn = fn

    def start(self) -> None:
        self._state = WorkerState.RUNNING
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="validation-worker"
        )
        self._thread.start()

    def stop(self) -> None:
        self._state = WorkerState.STOPPED
        if self._thread:
            self._thread.join(timeout=30)

    def _run_loop(self) -> None:
        cycle = 0
        while self._state == WorkerState.RUNNING and not self.stop_fn():
            cycle += 1
            ranked = self.shared.get_ranked_pool()

            # Only consider submission-ready candidates
            submission_ready = [
                c for c in ranked
                if c.gate.get("submission_ready", True)
                and c.lifecycle_status not in (
                    "local_prefilter_rejected",
                    "local_quality_rejected",
                )
            ]

            active_keys = {
                c.expression.strip()
                for c in self.shared.pool_by_expression.values()
                if c.submission.get("simulation_status") in (
                    "SUBMITTED", "RUNNING", "PENDING", "QUEUED"
                )
            }

            outcomes = self.scheduler.tick(submission_ready, cycle, active_keys)

            for outcome in outcomes:
                self._handle_outcome(outcome, cycle)

            time.sleep(max(0.5, self.scheduler.poll_interval()))

    def _handle_outcome(self, outcome: SlotOutcome, cycle: int) -> None:
        if outcome.action == "completed" and outcome.finalized:
            self.shared.officially_simulated_count += 1
            if outcome.candidate:
                self.shared.accepted_candidates.append(outcome.candidate)
            if self._finalize_fn:
                try:
                    self._finalize_fn(
                        outcome.candidate,
                        self.shared.pool_by_expression,
                        self.shared.accepted_candidates,
                        self.shared.archive_stats,
                        self.shared.archive_samples,
                        self.shared.blocked_expressions,
                        self.shared.submitted_count,
                        self.auto_submit,
                    )
                except Exception as exc:
                    self.event_fn(
                        "finalize_error",
                        f"Finalization failed: {redact_error_message(exc)}",
                        level="WARN",
                    )
        elif outcome.action == "failed":
            self.shared.officially_simulated_count += 1
            if outcome.candidate:
                outcome.candidate.lifecycle_status = "simulation_failed"
                self.shared.archive_samples.append(outcome.candidate)

    @property
    def state(self) -> WorkerState:
        return self._state

    def status(self) -> dict[str, Any]:
        return {
            "worker": "validation",
            "state": self._state.value,
            "officially_simulated": self.shared.officially_simulated_count,
            "scheduler_status": self.scheduler.slot_summaries(),
        }


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
        from .pipeline_context_sync import PipelineContextSyncMixin
        from .production_context import build_production_context

        # Build shared state
        shared = SharedState()

        # Initialize generator
        from .generator import CandidateGenerator
        generator = CandidateGenerator()

        def cycle_fn(cycle: int, config: Any) -> list[Candidate]:
            return generator.generate_batch(
                count=config.budget.max_candidates_per_cycle,
                cycle=cycle,
            )

        # Initialize scoring
        from .scoring import score_candidate
        from .alpha_checks import AlphaCheckRegistry

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

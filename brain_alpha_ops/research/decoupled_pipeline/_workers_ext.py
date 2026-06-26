"""Optimization and Validation workers for the decoupled pipeline.

  - ``OptimizationWorker`` — optimizes failed candidates
  - ``ValidationWorker`` — runs official simulations via ``ThreeSlotScheduler``

Production and Filter workers live in ``_workers.py``.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.simulation_scheduler import ThreeSlotScheduler, SlotOutcome
from brain_alpha_ops.research.decoupled_pipeline._state import SharedState, WorkerState

# Hardcoded logger name — preserves original ``brain_alpha_ops.research.decoupled_pipeline``
# identity for test caplog filtering.
logger = logging.getLogger("brain_alpha_ops.research.decoupled_pipeline")


@dataclass
class OptimizationWorker:
    """Runs optimization on failed/rejected candidates."""

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

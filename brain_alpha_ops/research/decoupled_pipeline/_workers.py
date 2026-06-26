"""Production and Filter workers for the decoupled pipeline.

  - ``ProductionWorker`` — continuously generates candidates
  - ``FilterWorker`` — applies local scoring and quality gates

Optimization and Validation workers live in ``_workers_ext.py``.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.decoupled_pipeline._state import SharedState, WorkerState

# Hardcoded logger name — preserves original ``brain_alpha_ops.research.decoupled_pipeline``
# identity for test caplog filtering.
logger = logging.getLogger("brain_alpha_ops.research.decoupled_pipeline")


@dataclass
class ProductionWorker:
    """Continuously generates candidates to maintain pool capacity."""

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
    """Runs local scoring + quality gates on new candidates."""

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
            if not candidate.expression or len(candidate.expression.strip()) < 5:
                candidate.lifecycle_status = "local_prefilter_rejected"
                return

            from ..scoring import score_candidate
            scores = score_candidate(candidate, self.scoring_config)
            candidate.local_quality = scores
            candidate.lifecycle_status = "locally_scored"

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

"""Shared state and worker-state enum for the decoupled pipeline.

Contains ``WorkerState`` (lifecycle enum) and ``SharedState`` (thread-safe
dataclass shared between all pipeline workers).
"""
from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message

from brain_alpha_ops.research.pipeline_helpers import rank_candidates
from brain_alpha_ops.research.simulation_scheduler import ThreeSlotScheduler, SlotOutcome

# Hardcoded logger name — preserves original ``brain_alpha_ops.research.decoupled_pipeline``
# identity for test caplog filtering.
logger = logging.getLogger("brain_alpha_ops.research.decoupled_pipeline")


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

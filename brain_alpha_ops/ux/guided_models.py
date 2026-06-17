"""Data structures for the guided pipeline UX."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PipelinePhase:
    """Single phase in the guided pipeline flow."""

    name: str
    description: str
    status: str = "pending"
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float = 0.0
    result_summary: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.status = "running"
        self.started_at = datetime.now(timezone.utc).isoformat()

    def complete(self, summary: str = "") -> None:
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc).isoformat()
        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.duration_seconds = (end - start).total_seconds()
        self.result_summary = summary

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.completed_at = datetime.now(timezone.utc).isoformat()
                # S-14: dedup + cap to prevent unbounded growth
        if error not in self.errors and len(self.errors) < 20:
            self.errors.append(error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "result_summary": self.result_summary,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class CheckpointData:
    """Serializable checkpoint for pipeline resume."""

    run_id: str
    phase_completed: str
    candidates_generated: int
    simulations_completed: int
    submissions_made: int
    cycle_number: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase_completed": self.phase_completed,
            "candidates_generated": self.candidates_generated,
            "simulations_completed": self.simulations_completed,
            "submissions_made": self.submissions_made,
            "cycle_number": self.cycle_number,
            "timestamp": self.timestamp,
            "snapshot": self.snapshot,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointData":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RunRecord:
    """Historical run record for browsing and replay."""

    run_id: str
    started_at: str
    completed_at: str | None = None
    status: str = "running"
    phases: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    checkpoint_path: str = ""
    parameter_audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "phases": self.phases,
            "summary": self.summary,
            "checkpoint_path": self.checkpoint_path,
            "parameter_audit": self.parameter_audit,
        }

"""Domain models used by the research operations pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class Candidate:
    alpha_id: str
    expression: str
    family: str
    hypothesis: str
    data_fields: list[str] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)
    source_tags: list[str] = field(default_factory=lambda: ["经验"])
    parent_id: str = ""
    mutation_type: str = ""
    dataset_id: str = ""          # P2-3: active dataset ID used during generation
    template_source: str = ""     # P2-3: source template/skeleton ID
    local_quality: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    simulation_id: str = ""
    official_alpha_id: str = ""
    official_metrics: dict[str, Any] = field(default_factory=dict)
    scorecard: dict[str, Any] = field(default_factory=dict)
    gate: dict[str, Any] = field(default_factory=dict)
    submission: dict[str, Any] = field(default_factory=dict)
    lifecycle_status: str = "created"
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        known = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in known})


@dataclass
class PipelineEvent:
    event: str
    message: str
    alpha_id: str = ""
    level: str = "INFO"
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    run_id: str
    candidates: list[Candidate]
    events: list[PipelineEvent]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "summary": self.summary,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "events": [event.to_dict() for event in self.events],
        }

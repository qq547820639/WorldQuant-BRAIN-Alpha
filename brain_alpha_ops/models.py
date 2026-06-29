"""Domain models used by the research operations pipeline."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from brain_alpha_ops.types import (
        GateResultDict,
        LocalQualityDict,
        OfficialMetrics,
        QualityDiagnosisDict,
        ScorecardDict,
        SubmissionDict,
        ValidationDict,
    )


def utc_now() -> str:  # N-05: returns ISO string, not datetime (consider renaming to utc_now_iso); prefer datetime before serialization
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass  # B-01: intentionally mutable for pipeline state management
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
    local_quality: LocalQualityDict = field(default_factory=dict)
    validation: ValidationDict = field(default_factory=dict)
    simulation_id: str = ""
    official_alpha_id: str = ""
    official_metrics: OfficialMetrics = field(default_factory=dict)
    scorecard: ScorecardDict = field(default_factory=dict)
    gate: GateResultDict = field(default_factory=dict)
    submission: SubmissionDict = field(default_factory=dict)
    alpha_output_config: dict[str, Any] = field(default_factory=dict)
    quality_diagnosis: QualityDiagnosisDict = field(default_factory=dict)
    lifecycle_status: str = "created"
    created_at: str = field(default_factory=utc_now)
    extra_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.data_fields = list(self.data_fields or [])
        self.operators = list(self.operators or [])
        self.source_tags = list(self.source_tags or [])


    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candidate":
        known = {f.name for f in fields(cls)}
        known_data = {key: value for key, value in data.items() if key in known}
        overflow = {key: value for key, value in data.items() if key not in known}
        extra = {**overflow, **dict(known_data.get("extra_fields") or {})}
        known_data["extra_fields"] = extra
        return cls(**known_data)


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

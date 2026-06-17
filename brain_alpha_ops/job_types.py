"""Shared job execution result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class JobExecutionResult:
    job_id: str
    status: str
    result: Any = None
    error: str = ""
    duration_seconds: float = 0.0

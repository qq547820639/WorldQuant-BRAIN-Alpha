"""BRAIN official Alpha Checks — data structures.

Re-exports the ``CheckResult`` and ``CheckReport`` dataclasses that were
originally defined at the top of ``alpha_checks.py``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    """Result of a single alpha check."""
    check_name: str
    passed: bool
    actual: Any = None
    expected: str = ""
    severity: str = "ERROR"       # ERROR | WARNING | INFO
    message: str = ""
    exception_applied: bool = False  # True when BRAIN exception rule was applied (e.g. SELF_CORRELATION Sharpe advantage)


@dataclass
class CheckReport:
    """Aggregate report of all alpha checks."""
    passed: bool = True
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    results: list[CheckResult] = field(default_factory=list)
    summary: str = ""

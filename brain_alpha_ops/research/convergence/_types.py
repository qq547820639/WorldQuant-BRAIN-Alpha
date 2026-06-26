"""Dataclasses for the ``convergence`` subpackage.

Extracted from the original ``convergence.py`` monolith. Holds the
``CycleRecord`` (single production cycle snapshot) and ``ConvergenceStatus``
(tracker status report) dataclasses used by ``ConvergenceTracker``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CycleRecord:
    """Single production cycle snapshot."""
    cycle: int
    produced: int = 0
    passed_local: int = 0
    simulated: int = 0
    passed_gate: int = 0
    submitted: int = 0
    avg_sharpe: float = 0.0
    avg_fitness: float = 0.0
    max_sharpe: float = 0.0
    avg_turnover: float = 0.0
    fusion_created: int = 0
    fusion_improvement_rate: float = 0.0
    # P1: bootstrap-compatible raw data
    raw_sharpes: list[float] = field(default_factory=list)
    raw_fitnesses: list[float] = field(default_factory=list)
    raw_turnovers: list[float] = field(default_factory=list)

@dataclass
class ConvergenceStatus:
    """Convergence tracker status report."""
    cycles_tracked: int = 0
    total_produced: int = 0
    total_submitted: int = 0
    recent_avg_sharpe: float = 0.0
    recent_max_sharpe: float = 0.0
    sharpe_trend: str = "stable"       # "improving" | "stable" | "declining"
    fitness_trend: str = "stable"
    stalled: bool = False
    stall_cycles: int = 0
    recommendation: str = ""
    cycle_history: list[dict[str, Any]] = field(default_factory=list)
    # P1: statistical fields
    sharpe_ci_low: float | None = None     # bootstrap 90% CI lower bound
    sharpe_ci_high: float | None = None    # bootstrap 90% CI upper bound
    trend_confidence: float = 0.0             # Spearman ρ or trend strength
    stall_is_significant: bool = False        # statistically significant stall

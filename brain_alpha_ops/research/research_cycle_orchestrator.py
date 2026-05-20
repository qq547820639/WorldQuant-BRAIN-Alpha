"""Cycle state progression for the alpha research loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CycleDecision:
    cycle: int
    should_run: bool
    reason: str = ""


@dataclass
class ResearchCycleOrchestrator:
    """Owns the small but easy-to-regress cycle progression rules."""

    run_forever: bool
    max_cycles: int
    should_stop: Callable[[], bool]
    cycle: int = 0

    def next_cycle(self) -> CycleDecision:
        if self.should_stop():
            return CycleDecision(self.cycle, False, "stopped")
        if not self.run_forever and self.cycle >= max(0, int(self.max_cycles or 0)):
            return CycleDecision(self.cycle, False, "max_cycles_reached")
        self.cycle += 1
        return CycleDecision(self.cycle, True, "continue")

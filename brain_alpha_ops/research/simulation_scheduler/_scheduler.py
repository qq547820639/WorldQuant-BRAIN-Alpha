"""``ThreeSlotScheduler`` — 3-slot concurrent scheduler for official BRAIN simulations.

Assembles the helper and tick mixins into the final ``ThreeSlotScheduler``
dataclass.

Architecture:
  - SimulationSlot: state machine per slot (idle→submitting→polling→done/failed/cooldown)
  - ThreeSlotScheduler: manages 3 slots, picks next candidates, handles cooldowns
  - Integration via callback pattern with the existing pipeline
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from brain_alpha_ops.brain_api.base import BrainAPI
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.simulation_scheduler._types import (
    SlotOutcome,
    SimulationSlot,
    SlotState,
    _DEFAULT_POLL_INTERVAL,
)
from brain_alpha_ops.research.simulation_scheduler._scheduler_helpers import (
    _SchedulerHelpersMixin,
)
from brain_alpha_ops.research.simulation_scheduler._scheduler_tick import (
    _SchedulerTickMixin,
)


@dataclass
class ThreeSlotScheduler(_SchedulerHelpersMixin, _SchedulerTickMixin):
    """Manages up to 3 concurrent simulation slots.

    Each slot independently submits, polls, and completes simulations.
    When a slot finishes (or enters cooldown), the next TopK candidate
    from the pool fills it.

    Usage:
        scheduler = ThreeSlotScheduler(api=api, settings_provider=..., ...)
        # Each cycle:
        scheduler.tick(candidates, cycle)  # polls existing + fills empty slots
        # Check results:
        for outcome in scheduler.drain_completed():
            process(outcome)
    """

    api: BrainAPI
    settings_provider: Callable[[], dict[str, Any]]
    poll_interval: Callable[[], float] = field(default=lambda: _DEFAULT_POLL_INTERVAL)
    event_callback: Callable[..., None] = field(default=lambda: lambda *a, **kw: None)
    progress_callback: Callable[..., None] | None = None
    stop_callback: Callable[[], bool] = field(default=lambda: False)
    max_slots: int = 3
    max_simulation_retries: int = 3

    _slots: list[SimulationSlot] = field(init=False, default_factory=list)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)
    _completed: list[SlotOutcome] = field(init=False, default_factory=list)
    _global_cooldown_until: float = field(init=False, default=0.0)
    _global_cooldown_reason: str = field(init=False, default="")
    _halted: bool = field(init=False, default=False)
    _halt_reason: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self._slots = [
            SimulationSlot(slot_id=i + 1) for i in range(self.max_slots)
        ]

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def tick_loop(
        self,
        candidate_provider: Callable[[], list[Candidate]],
        result_handler: Callable[[SlotOutcome], None],
        cycle: int,
        duration_seconds: float = 0,
        active_expression_keys: Callable[[], set[str]] | None = None,
    ) -> None:
        """Run a continuous tick loop for a fixed duration or until stopped.

        Useful for the decoupled pipeline where the scheduler runs
        independently. Polls all active slots at poll_interval and fills
        idle slots as candidates become available.

        Args:
            candidate_provider: Callable returning ranked candidates.
            result_handler: Called with each SlotOutcome.
            cycle: Current cycle number.
            duration_seconds: How long to loop (0 = until stopped).
            active_expression_keys: Callable returning keys to avoid.
        """
        deadline = time.monotonic() + duration_seconds if duration_seconds > 0 else float("inf")
        while time.monotonic() < deadline:
            if self.stop_callback():
                break

            candidates = candidate_provider()
            keys = active_expression_keys() if active_expression_keys else set()
            outcomes = self.tick(candidates, cycle, keys)

            for outcome in outcomes:
                result_handler(outcome)

            # Sleep between poll rounds
            time.sleep(max(0.1, self.poll_interval()))

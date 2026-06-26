"""Re-export from the ``simulation_scheduler`` subpackage for backward compatibility.

The original monolithic ``simulation_scheduler.py`` was split into the
``brain_alpha_ops.research.simulation_scheduler`` subpackage. This module
re-exports the full public API surface so legacy imports continue to work.

Sub-modules:
  - ``_types``               : ``SlotState`` enum, ``SimulationSlot`` /
                               ``SlotOutcome`` dataclasses, cooldown constants
  - ``_scheduler_helpers``   : ``_SchedulerHelpersMixin`` (slot management,
                               candidate selection, event emission)
  - ``_scheduler_tick``      : ``_SchedulerTickMixin`` (tick loop, submit,
                               poll, outcome handling)
  - ``_scheduler``           : ``ThreeSlotScheduler`` class assembly
  - ``_consistency``         : ``SchedulerInconsistencyError``,
                               ``assert_scheduler_consistency()``,
                               ``OFFICIAL_SIMULATION_SLOT_LIMIT`` (Workstream C1.1)
"""
from __future__ import annotations

from brain_alpha_ops.research.simulation_scheduler._types import *  # noqa: F401,F403
from brain_alpha_ops.research.simulation_scheduler._scheduler import *  # noqa: F401,F403

# Explicit re-exports for clarity and to ensure all public symbols are
# available via ``from brain_alpha_ops.research.simulation_scheduler import X``.
from brain_alpha_ops.research.simulation_scheduler._types import (  # noqa: F401
    SlotOutcome,
    SlotState,
    SimulationSlot,
)
from brain_alpha_ops.research.simulation_scheduler._scheduler import (  # noqa: F401
    ThreeSlotScheduler,
)

# Workstream C1.1: scheduler consistency guard — single source of truth
# for the official 3-slot simulation limit.
from brain_alpha_ops.research.simulation_scheduler._consistency import (  # noqa: F401
    OFFICIAL_SIMULATION_SLOT_LIMIT,
    SchedulerInconsistencyError,
    assert_scheduler_consistency,
)

# Re-export private constants for backward compatibility — the original
# ``simulation_scheduler.py`` exposed these at module level.
from brain_alpha_ops.research.simulation_scheduler._types import (  # noqa: F401
    _COOLDOWN_429,
    _COOLDOWN_CONCURRENT_LIMIT,
    _COOLDOWN_GENERIC,
    _COOLDOWN_SERVER_ERROR,
    _DEFAULT_POLL_INTERVAL,
    _MAX_CONSECUTIVE_ERRORS_PER_SLOT,
)

"""Scheduler consistency guard for the official 3-slot simulation pipeline.

Workstream C1.1 of the Alpha production system overhaul spec.

This module provides the *single source of truth* for the official
simulation slot limit and a runtime assertion that all schedulers /
managers / budget fields agree on that limit.

Architecture note
-----------------
Two schedulers coexist in the codebase:

1. ``ThreeSlotScheduler`` (``research/simulation_scheduler/_scheduler.py``)
   — the official simulation scheduler. ``max_slots`` defaults to
   ``OFFICIAL_SIMULATION_SLOT_LIMIT`` (3) and each slot runs an
   independent state machine (idle → submitting → polling →
   completed/failed/cooldown).

2. ``BacktestSlotManager`` (``research/backtest_slots.py``) — owns the
   mutable official backtest slot map. ``active_limit`` is *parameterised*
   at call time via ``open_slots(active_limit)``; the pipeline feeds it
   ``AlphaResearchPipeline._active_backtest_limit()``, which is the min of
   three ``ResearchBudget`` fields:

       min(
           budget.official_backtest_batch_size,
           budget.max_official_simulations_per_cycle,
           budget.max_official_concurrent_simulations,
       )

   All three default to 3 (see ``config_models.py:ResearchBudget``).

A silent drift between these two schedulers would either waste official
API quota (manager allows more slots than the scheduler can run) or
starve the scheduler (manager allows fewer). ``assert_scheduler_consistency()``
is called at ``ThreeSlotScheduler.__post_init__`` to catch such drift
early.

Note: ``ParallelBacktestExecutor`` (``research/parallel_backtest.py``,
``max_workers=4``) is intentionally NOT covered here — it is a separate
multi-market batch backtest planner, unrelated to the official 3-slot
limit. See its module docstring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from brain_alpha_ops.research.simulation_scheduler._scheduler import (
        ThreeSlotScheduler,
    )


# ── Single source of truth ──────────────────────────────────────────────
# The official BRAIN simulation slot limit. All schedulers, slot managers,
# budget defaults, and web layers MUST agree on this value.
#
# Rationale: BRAIN's official concurrent simulation quota for regular
# accounts is 3. The ThreeSlotScheduler was built around this limit and
# each slot runs an independent state machine so that a single slot's
# cooldown / failure / 429 does NOT halt the whole production chain.
OFFICIAL_SIMULATION_SLOT_LIMIT: int = 3


class SchedulerInconsistencyError(RuntimeError):
    """Raised when official scheduler/slot-manager/budget limits disagree.

    Triggered by ``assert_scheduler_consistency()``. Indicates a regression
    that would either waste official API quota or starve the scheduler.
    """


def assert_scheduler_consistency(
    scheduler: "ThreeSlotScheduler | None" = None,
) -> None:
    """Assert that all official-simulation schedulers agree on the limit.

    Verifies:
      1. ``ThreeSlotScheduler.max_slots`` (class default or instance value)
         equals ``OFFICIAL_SIMULATION_SLOT_LIMIT``.
      2. ``ResearchBudget`` defaults for
         ``max_official_concurrent_simulations``,
         ``max_official_simulations_per_cycle``, and
         ``official_backtest_batch_size`` all equal
         ``OFFICIAL_SIMULATION_SLOT_LIMIT`` — these feed
         ``BacktestSlotManager.open_slots(active_limit)`` via
         ``AlphaResearchPipeline._active_backtest_limit()``.

    Args:
        scheduler: Optional ``ThreeSlotScheduler`` instance. If omitted,
            the class-level default ``max_slots`` is checked.

    Raises:
        SchedulerInconsistencyError: If any check fails.
    """
    # Import inside the function to avoid circular imports —
    # ``_scheduler.py`` imports this module at ``__post_init__`` time.
    from brain_alpha_ops.research.simulation_scheduler._scheduler import (
        ThreeSlotScheduler,
    )
    from brain_alpha_ops.config_models import ResearchBudget

    expected = OFFICIAL_SIMULATION_SLOT_LIMIT

    # 1. ThreeSlotScheduler.max_slots
    max_slots = (
        scheduler.max_slots
        if scheduler is not None
        else ThreeSlotScheduler.max_slots
    )
    if int(max_slots) != expected:
        raise SchedulerInconsistencyError(
            f"ThreeSlotScheduler.max_slots={max_slots} but "
            f"OFFICIAL_SIMULATION_SLOT_LIMIT={expected}; "
            f"official simulation schedulers are out of sync."
        )

    # 2. ResearchBudget defaults that feed BacktestSlotManager.active_limit
    budget = ResearchBudget()
    budget_fields = {
        "max_official_concurrent_simulations": budget.max_official_concurrent_simulations,
        "max_official_simulations_per_cycle": budget.max_official_simulations_per_cycle,
        "official_backtest_batch_size": budget.official_backtest_batch_size,
    }
    for field_name, value in budget_fields.items():
        if int(value) != expected:
            raise SchedulerInconsistencyError(
                f"ResearchBudget.{field_name}={value} but "
                f"OFFICIAL_SIMULATION_SLOT_LIMIT={expected}; "
                f"BacktestSlotManager would receive a divergent active_limit."
            )

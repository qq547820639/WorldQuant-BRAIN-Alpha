"""Canonical state enumerations used across the project (P2-1 refactor).

Before this module existed, the same conceptual status sets were redeclared
in at least four places:

  - ``tasks.py`` (job store ACTIVE/TERMINAL/KNOWN_STATUSES)
  - ``research/contracts.py`` (ACTIVE/TERMINAL_BACKTEST_STATUSES)
  - ``web_state_contract.py`` (status_kind categorisation)
  - ``web_get_handlers.py`` (legacy per-job status map)

That drift risk is what this module removes.  All four sources now re-export
the canonical sets from here.  New code MUST import from
``brain_alpha_ops.core_state`` rather than declaring its own.
"""

from __future__ import annotations


# ── Job lifecycle (web console, async jobs) ────────────────────────────────

JOB_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {"queued", "pending", "starting", "running", "stopping"}
)
JOB_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "completed_with_warnings", "failed", "stopped", "cancelled", "canceled"}
)
JOB_KNOWN_STATUSES: frozenset[str] = (
    JOB_ACTIVE_STATUSES | JOB_TERMINAL_STATUSES | {"idle"}
)

# Status-kind: coarser categorisation used by the React UI for colour
# coding and human-readable labels.
JOB_STATUS_KIND: dict[str, str] = {
    "queued": "active",
    "pending": "active",
    "starting": "active",
    "running": "active",
    "stopping": "active",
    "completed": "success",
    "completed_with_warnings": "warning",
    "failed": "failed",
    "stopped": "interrupted",
    "cancelled": "interrupted",
    "canceled": "interrupted",
    "idle": "idle",
}


# ── Backtest lifecycle (BRAIN official simulations) ────────────────────────

BACKTEST_ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        "SUBMITTED",
        "RUNNING",
        "PENDING",
        "POLLING",
        "SIMULATION_SUBMITTED",
        "SIMULATION_RUNNING",
        "SIMULATION_POLL_DEFERRED_RATE_LIMIT",
        "SIMULATION_RESULT_DEFERRED_RATE_LIMIT",
    }
)
BACKTEST_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        "COMPLETED",
        "FAILED",
        "ERROR",
        "CANCELLED",
        "SIMULATION_FAILED",
        "SIMULATION_POLL_FAILED",
        "SIMULATION_REQUEST_FAILED",
        "SIMULATION_RESULT_FAILED",
        "SIMULATION_TIMEOUT",
        "OFFICIAL_SIMULATED",
        "OFFICIAL_STANDARD_REJECTED",
        "SUBMISSION_READY",
    }
)
BACKTEST_ACTIVE_ACTIONS: frozenset[str] = frozenset(
    {"submitted", "polled", "running", "poll_deferred", "result_deferred"}
)
BACKTEST_TERMINAL_ACTIONS: frozenset[str] = frozenset(
    {"completed", "failed", "submit_failed", "poll_failed", "result_failed"}
)


# ── Helpers ────────────────────────────────────────────────────────────────

def is_active_job_status(status: str) -> bool:
    return str(status or "").lower() in {s.lower() for s in JOB_ACTIVE_STATUSES}


def is_terminal_job_status(status: str) -> bool:
    return str(status or "").lower() in {s.lower() for s in JOB_TERMINAL_STATUSES}


def classify_job_status(status: str) -> str:
    """Return the coarse status_kind for ``status`` (or 'unknown')."""
    return JOB_STATUS_KIND.get(str(status or "").lower(), "unknown")


def is_active_backtest_status(status: str) -> bool:
    return str(status or "").upper() in BACKTEST_ACTIVE_STATUSES


def is_terminal_backtest_status(status: str) -> bool:
    return str(status or "").upper() in BACKTEST_TERMINAL_STATUSES

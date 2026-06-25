"""Module-level constants for the pipeline task store.

Extracted from ``brain_alpha_ops.tasks`` to keep the store module focused on
state management while preserving the public import surface.
"""
from __future__ import annotations

DEFAULT_RECOVERY_ERROR = "Process restarted before this task completed."
DEFAULT_WATCHDOG_TIMEOUT_SECONDS = 300.0
DEFAULT_WATCHDOG_ERROR = "Web flow watchdog stopped this task after no clear progress update."
JOB_PREVIEW_ROWS = 5
COMPACT_LIST_KEYS = {"alphas", "cloud_alphas", "candidates", "backtests", "lifecycle_records"}
DEFAULT_MAX_PERSISTENCE_LOAD_BYTES = 50 * 1024 * 1024

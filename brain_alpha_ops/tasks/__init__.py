"""Reusable task state storage for long-running operations (pipeline jobs).

**Purpose**: Persist pipeline background jobs (production, sync, check,
async) with thread-safe state, watchdog, and atomic JSON persistence.

**Relationship to web_jobs.py**: This module tracks *pipeline* background
jobs; ``brain_alpha_ops.web_jobs`` tracks *Web UI* user operations.  They
serve different lifecycles and should NOT be unified (P1-7 clarification).
See ``web_jobs.get_web_job_store()`` for the Protocol-based bridge that
allows background services to use web_jobs without a full JobStore.

The web console and internal automation share the same small contract for job
lifecycle state. The store intentionally keeps the
runtime payload narrow: status, progress, result, cancellation flag, and error.
It never persists request credentials.

Subpackage split (formerly ``tasks.py`` monolith):
  - ``__init__``: public API re-export shim
  - ``_constants``: module-level constants
  - ``_store``: ``JobStore`` class with thread-safe state + persistence
  - ``_watchdog``: stall detection and terminal-state protection helpers
  - ``_compaction``: runtime result compaction and redaction helpers
"""
from __future__ import annotations

from brain_alpha_ops.core_state import (
    JOB_ACTIVE_STATUSES as ACTIVE_STATUSES,
)  # noqa: F401
from brain_alpha_ops.core_state import (
    JOB_TERMINAL_STATUSES as TERMINAL_STATUSES,
)  # noqa: F401
from brain_alpha_ops.redaction import redact_data  # noqa: F401

from ._compaction import (  # noqa: F401
    _candidate_submission_audit_evidence,
    _compact_runtime_result,
    _job_safe,
    _json_safe,
    _should_compact_named_list,
    _submission_evidence_key,
    _submission_evidence_rows,
)
from ._constants import (  # noqa: F401
    COMPACT_LIST_KEYS,
    DEFAULT_MAX_PERSISTENCE_LOAD_BYTES,
    DEFAULT_RECOVERY_ERROR,
    DEFAULT_WATCHDOG_ERROR,
    DEFAULT_WATCHDOG_TIMEOUT_SECONDS,
    JOB_PREVIEW_ROWS,
)
from ._store import JobStore  # noqa: F401
from ._watchdog import (  # noqa: F401
    _is_watchdog_terminal_failed,
    _mark_watchdog_failed,
    _reject_watchdog_terminal_update,
    _updated_at,
    _watchdog_should_stop,
)

__all__ = [
    "ACTIVE_STATUSES",
    "TERMINAL_STATUSES",
    "COMPACT_LIST_KEYS",
    "DEFAULT_MAX_PERSISTENCE_LOAD_BYTES",
    "DEFAULT_RECOVERY_ERROR",
    "DEFAULT_WATCHDOG_ERROR",
    "DEFAULT_WATCHDOG_TIMEOUT_SECONDS",
    "JOB_PREVIEW_ROWS",
    "JobStore",
    "redact_data",
]

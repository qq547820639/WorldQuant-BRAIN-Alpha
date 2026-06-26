"""Re-export from the ``observability`` subpackage for backward compatibility.

The original monolithic ``observability.py`` was split into the
``brain_alpha_ops.research.observability`` subpackage. This module re-exports
the full public API surface so legacy imports continue to work.

Sub-modules:
  - ``_snapshot`` : ``build_research_observability_snapshot`` + JSONL constants
  - ``_context``  : ``observability_context``, ``official_call_guard_observability``,
                    ``actionable_duplicate_expression_buckets``,
                    ``actionable_duplicate_expression_records``
  - ``_health``   : ``diagnose_research_health``
"""
from __future__ import annotations

from brain_alpha_ops.research.observability._snapshot import *  # noqa: F401,F403
from brain_alpha_ops.research.observability._context import *  # noqa: F401,F403
from brain_alpha_ops.research.observability._health import *  # noqa: F401,F403

# Explicitly re-export public constants (``*`` already catches them, but be
# explicit for clarity and to survive future ``__all__`` additions).
from brain_alpha_ops.research.observability._snapshot import (  # noqa: F401
    JSONL_FILES,
    SQLITE_INDEX_DIAGNOSTICS_FILE,
    build_research_observability_snapshot,
)
from brain_alpha_ops.research.observability._context import (  # noqa: F401
    actionable_duplicate_expression_buckets,
    actionable_duplicate_expression_records,
    observability_context,
    official_call_guard_observability,
)
from brain_alpha_ops.research.observability._health import (  # noqa: F401
    diagnose_research_health,
)

# Re-export private helpers from ``_observability_helpers`` for backward
# compatibility — the original ``observability.py`` re-imported these at the
# bottom of the module so they were accessible as
# ``brain_alpha_ops.research.observability._backtest_observability`` etc.
from brain_alpha_ops.research._observability_helpers import (  # noqa: F401
    _backtest_observability,
    _check_observability,
    _compact_backtest_row,
    _counter_rows,
    _error_observability,
    _expression_index_failure_summary,
    _expression_sqlite_status,
    _failure_reason,
    _float_from_any,
    _int_from_any,
    _is_backtest_completed,
    _is_backtest_failure,
    _is_backtest_submitted,
    _observability_expression_payload,
    _observability_recommendations,
    _row_retryable,
    _text,
    _unique_text_items,
)

__all__ = [
    # Public API from _snapshot
    "JSONL_FILES",
    "SQLITE_INDEX_DIAGNOSTICS_FILE",
    "build_research_observability_snapshot",
    # Public API from _context
    "observability_context",
    "official_call_guard_observability",
    "actionable_duplicate_expression_buckets",
    "actionable_duplicate_expression_records",
    # Public API from _health
    "diagnose_research_health",
    # Private symbols re-exported from _observability_helpers for backward
    # compatibility (the original observability.py re-imported these).
    "_backtest_observability",
    "_check_observability",
    "_compact_backtest_row",
    "_counter_rows",
    "_error_observability",
    "_expression_index_failure_summary",
    "_expression_sqlite_status",
    "_failure_reason",
    "_float_from_any",
    "_int_from_any",
    "_is_backtest_completed",
    "_is_backtest_failure",
    "_is_backtest_submitted",
    "_observability_expression_payload",
    "_observability_recommendations",
    "_row_retryable",
    "_text",
    "_unique_text_items",
]

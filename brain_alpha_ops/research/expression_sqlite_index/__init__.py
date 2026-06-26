"""Re-export from the ``expression_sqlite_index`` subpackage for backward compatibility."""
from __future__ import annotations

from brain_alpha_ops.research.expression_sqlite_index._core import *  # noqa: F401,F403
from brain_alpha_ops.research.expression_sqlite_index._helpers import *  # noqa: F401,F403

# Explicitly re-export private symbols for test monkeypatch compatibility
from brain_alpha_ops.research.expression_sqlite_index._core import (  # noqa: F401
    ExpressionSqliteIndex,
)
from brain_alpha_ops.research.expression_sqlite_index._helpers import (  # noqa: F401
    DEFAULT_LOOKUP_SCAN_LIMIT,
    SCHEMA_VERSION,
    _compact_record,
    _ensure_schema,
    _expression_from_record,
    _feature_rows,
    _finalize_bucket,
    _float,
    _int,
    _loads_dict,
    _nested,
    _next_record_index,
    _row_to_record,
    _score_for,
    _status_for,
    _summary_from_record,
    _summary_from_records,
    _text,
    _window_rows,
)

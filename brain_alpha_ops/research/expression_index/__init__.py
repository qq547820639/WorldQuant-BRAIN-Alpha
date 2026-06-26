"""Re-export from the ``expression_index`` subpackage for backward compatibility.

The original ``brain_alpha_ops/research/expression_index.py`` module was split
into focused submodules; this package preserves the public API and the private
symbols that tests monkeypatch.
"""
from __future__ import annotations

from brain_alpha_ops.research.expression_index._buckets import (  # noqa: F401
    _compat_lookup_schema,
    _compat_summary_schema,
    _expression_bucket,
    _feature_bucket,
    _finalize_expression_bucket,
    _rank_feature_buckets,
    _rank_window_buckets,
    _update_expression_bucket,
    _update_feature_bucket,
)
from brain_alpha_ops.research.expression_index._core import (  # noqa: F401
    DEFAULT_SOURCES,
    ExpressionHistoryIndex,
)
from brain_alpha_ops.research.expression_index._helpers import (  # noqa: F401
    _append_unique,
    _as_int_list,
    _as_text_list,
    _compact_record,
    _nested,
    _num,
    _score_for,
    _status_for,
    _text,
)
from brain_alpha_ops.research.expression_index._records import (  # noqa: F401
    _expression_from_record,
    _load_jsonl,
    _source_records_for,
    _summary_from_record,
)

__all__ = [
    # Public API
    "DEFAULT_SOURCES",
    "ExpressionHistoryIndex",
    # Private helpers re-exported for test monkeypatch compatibility
    "_append_unique",
    "_as_int_list",
    "_as_text_list",
    "_compact_record",
    "_compat_lookup_schema",
    "_compat_summary_schema",
    "_expression_bucket",
    "_expression_from_record",
    "_feature_bucket",
    "_finalize_expression_bucket",
    "_load_jsonl",
    "_nested",
    "_num",
    "_rank_feature_buckets",
    "_rank_window_buckets",
    "_score_for",
    "_source_records_for",
    "_status_for",
    "_summary_from_record",
    "_text",
    "_update_expression_bucket",
    "_update_feature_bucket",
]

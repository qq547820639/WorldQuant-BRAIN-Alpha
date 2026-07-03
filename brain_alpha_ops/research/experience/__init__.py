"""Re-export from the ``experience`` subpackage for backward compatibility.

The original ``experience`` subpackage (``_common``, ``_query``,
``_recording``) was consolidated into:
  - ``experience`` : shared helpers/constants (``logger``,
                     ``DEFAULT_HISTORY_LIMIT``, ``_num``, ``_ratio``,
                     ``_load_records``, ``_empty_patterns``,
                     ``normalize_brain_ratio``) and pattern-query functions
                     (``get_winning_patterns``, ``update_hypothesis_weights``)
  - ``recording``  : ``record_alpha_result``, ``_record_ab_comparison``,
                     ``get_mutation_effectiveness``
"""
from __future__ import annotations

from .experience import *  # noqa: F401,F403
from .recording import *  # noqa: F401,F403

# Explicitly re-export private symbols for test monkeypatch compatibility
from .experience import (  # noqa: F401
    DEFAULT_HISTORY_LIMIT,
    _empty_patterns,
    _load_records,
    _num,
    _ratio,
    normalize_brain_ratio,
)
from .recording import (  # noqa: F401
    _record_ab_comparison,
)

__all__ = [
    # Public API from experience
    "DEFAULT_HISTORY_LIMIT",
    "logger",
    "normalize_brain_ratio",
    # Public API from query
    "get_winning_patterns",
    "update_hypothesis_weights",
    # Public API from recording
    "record_alpha_result",
    "get_mutation_effectiveness",
    # Private symbols re-exported for test monkeypatch compatibility
    "_empty_patterns",
    "_load_records",
    "_num",
    "_ratio",
    "_record_ab_comparison",
]

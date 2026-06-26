"""Re-export from the ``experience`` subpackage for backward compatibility."""
from __future__ import annotations

from brain_alpha_ops.research.experience._common import *  # noqa: F401,F403
from brain_alpha_ops.research.experience._query import *  # noqa: F401,F403
from brain_alpha_ops.research.experience._recording import *  # noqa: F401,F403

# Explicitly re-export private symbols for test monkeypatch compatibility
from brain_alpha_ops.research.experience._common import (  # noqa: F401
    DEFAULT_HISTORY_LIMIT,
    _empty_patterns,
    _load_records,
    _num,
    _ratio,
)
from brain_alpha_ops.research.experience._common import (  # noqa: F401
    normalize_brain_ratio,
)
from brain_alpha_ops.research.experience._recording import (  # noqa: F401
    _record_ab_comparison,
)

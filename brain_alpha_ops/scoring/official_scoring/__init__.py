"""Re-export from the ``official_scoring`` subpackage for backward compatibility."""
from __future__ import annotations

from brain_alpha_ops.scoring.official_scoring._constants import (  # noqa: F401
    SCORING_VERSION,
    _MAX_SCORE_HISTORY_PER_ALPHA,
    _MAX_SCORE_HISTORY_TOTAL_ENTRIES,
    _SOFT_GATE_TOLERANCE,
    _TREND_DELTA_DECLINING,
    _TREND_DELTA_IMPROVING,
    _format_gate_failure,
    _gate_item_value,
)
from brain_alpha_ops.scoring.official_scoring._result import (  # noqa: F401
    ScoringResult,
)
from brain_alpha_ops.scoring.official_scoring._system import (  # noqa: F401
    OfficialScoringSystem,
    _PersistedScoreHistoryDB,
    logger,
)

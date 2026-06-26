"""Backtest slot payload and queue-summary helpers for Web routes.

Re-export shim. The implementation has been split into the
``brain_alpha_ops.web.misc.web_backtest_slots`` subpackage. This module remains
for backward compatibility so existing imports
``from brain_alpha_ops.web.misc.web_backtest_slots import ...`` continue to work.

Note: when both ``web_backtest_slots.py`` and ``web_backtest_slots/__init__.py``
exist, Python resolves ``brain_alpha_ops.web.misc.web_backtest_slots`` to the
package directory. The ``web_backtest_slots/__init__.py`` is the live module;
this file mirrors its public API for documentation and as a safety net.
"""
from __future__ import annotations

from .web_backtest_slots._handlers import (  # noqa: F401
    backtest_queue_summary,
    backtest_slot_limit,
    backtest_slots_payload,
    backtest_status_board,
    slot_payload,
)
from .web_backtest_slots._helpers import (  # noqa: F401
    candidate_local_backtest_failed,
    candidate_local_valid,
    candidate_official_review_blockers,
    candidate_score,
    candidate_submit_evidence_blockers,
    is_submit_only_quality_reason,
    official_simulation_score_threshold,
    slot_active,
    slot_has_official_work_record,
    slot_score,
)

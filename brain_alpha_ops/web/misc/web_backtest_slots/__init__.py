"""Backtest slot payload and queue-summary helpers for Web routes.

Subpackage split (formerly ``web_backtest_slots.py`` monolith, Workstream F3.9):
  - ``_handlers``: route handlers (``backtest_slot_limit``,
    ``backtest_slots_payload``, ``slot_payload``, ``backtest_status_board``,
    ``backtest_queue_summary``)
  - ``_helpers``: official-review blocker classification, slot/row predicates,
    candidate scoring, and queue next-action helpers

The legacy flat import ``brain_alpha_ops.web_backtest_slots`` (redirected by
``_web_bridge``) continues to resolve to this package, so existing callers
``from brain_alpha_ops.web_backtest_slots import backtest_slot_limit`` and
``from brain_alpha_ops.web.misc.web_backtest_slots import X`` both work.
"""

from __future__ import annotations

from ._handlers import (
    backtest_queue_summary,
    backtest_slot_limit,
    backtest_slots_payload,
    backtest_status_board,
    slot_payload,
)
from ._helpers import (
    LoadRunConfig,
    ReadJsonlRecords,
    backtest_queue_next_action,
    backtest_row_completed,
    backtest_row_failed,
    backtest_row_pass_verdict,
    backtest_row_submitted,
    backtest_task_key,
    candidate_high_cloud_similarity_blocked,
    candidate_local_backtest_failed,
    candidate_local_valid,
    candidate_official_review_blockers,
    candidate_score,
    candidate_submit_evidence_blockers,
    is_submit_only_quality_reason,
    official_simulation_score_threshold,
    quality_diagnosis_official_review_blockers,
    slot_active,
    slot_has_official_work_record,
    slot_score,
)

__all__ = [
    "LoadRunConfig",
    "ReadJsonlRecords",
    "backtest_queue_next_action",
    "backtest_queue_summary",
    "backtest_row_completed",
    "backtest_row_failed",
    "backtest_row_pass_verdict",
    "backtest_row_submitted",
    "backtest_slot_limit",
    "backtest_slots_payload",
    "backtest_status_board",
    "backtest_task_key",
    "candidate_high_cloud_similarity_blocked",
    "candidate_local_backtest_failed",
    "candidate_local_valid",
    "candidate_official_review_blockers",
    "candidate_score",
    "candidate_submit_evidence_blockers",
    "is_submit_only_quality_reason",
    "official_simulation_score_threshold",
    "quality_diagnosis_official_review_blockers",
    "slot_active",
    "slot_has_official_work_record",
    "slot_payload",
    "slot_score",
]

"""Production decisions for Web candidate-pool rows.

Subpackage split (formerly ``decisions.py`` monolith):
  - ``_helpers`` : candidate inspection utilities and constants
  - ``_evidence``: decision evidence and lifecycle risk normalization
  - ``_decision``: core production decision logic
  - ``_annotate``: decision annotation and aggregation helpers
"""

from __future__ import annotations

from ._helpers import (
    _ARCHIVE_STATUS_TOKENS,
    _GENERIC_POOL_STATUSES,
    _blocking_pairs,
    _decision_band,
    _gate_failed_reasons,
    _has_human_confirmation_blocker,
    _is_submit_only_quality_reason,
    _lifecycle_text,
    _only_official_evidence_missing,
    _safe_int,
    _status,
    candidate_hard_blocking_reasons,
    candidate_has_official_evidence,
    candidate_score,
    candidate_submission_ready,
    candidate_submit_only_reasons,
)
from ._evidence import (
    _compact_lifecycle_risk,
    _lifecycle_replay_evidence,
    _merge_existing_scientific_audit_decision_evidence,
    candidate_decision_evidence,
)
from ._decision import (
    DECISION_SCHEMA_VERSION,
    DEFAULT_OFFICIAL_SIMULATION_SCORE,
    _decision,
    candidate_production_decision,
)
from ._annotate import (
    annotate_candidate_decision,
    candidate_decision_action,
    candidate_decision_blocking,
    decision_action_counts,
)

__all__ = [
    # Constants
    "DEFAULT_OFFICIAL_SIMULATION_SCORE",
    "DECISION_SCHEMA_VERSION",
    "_ARCHIVE_STATUS_TOKENS",
    "_GENERIC_POOL_STATUSES",
    # Public API
    "candidate_production_decision",
    "annotate_candidate_decision",
    "decision_action_counts",
    "candidate_decision_action",
    "candidate_decision_blocking",
    "candidate_submission_ready",
    "candidate_score",
    "candidate_has_official_evidence",
    "candidate_submit_only_reasons",
    "candidate_hard_blocking_reasons",
    "candidate_decision_evidence",
    # Private helpers (re-exported for backward compatibility)
    "_is_submit_only_quality_reason",
    "_lifecycle_text",
    "_safe_int",
    "_status",
    "_decision_band",
    "_blocking_pairs",
    "_gate_failed_reasons",
    "_has_human_confirmation_blocker",
    "_only_official_evidence_missing",
    "_decision",
    "_lifecycle_replay_evidence",
    "_compact_lifecycle_risk",
    "_merge_existing_scientific_audit_decision_evidence",
]

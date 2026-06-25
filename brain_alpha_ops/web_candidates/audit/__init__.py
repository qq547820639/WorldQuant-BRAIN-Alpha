"""Scientific audit helpers for Web candidate production.

The audit contract records why an Alpha candidate changed state without using
test outcomes to tune expressions and without weakening the separate BRAIN
submit-readiness gate.

Subpackage split (formerly ``audit.py`` monolith):
  - ``_helpers``: utility functions and constants
  - ``_blocks`` : structured block builders for audit records
  - ``_record`` : audit record creation and attachment
  - ``_summary``: audit summary and policy inspection
"""

from __future__ import annotations

from ._helpers import (
    FORBIDDEN_SCIENTIFIC_AUDIT_FEEDBACK_SOURCE_TOKENS,
    _audit_events,
    _audit_identity,
    _bool_default,
    _bump,
    _feedback_sources_include_test_feedback,
    _first_int,
    _is_int_like,
    _optional_float,
    _scientific_audit_payloads,
)
from ._blocks import (
    _evidence_block,
    _expression_block,
    _explainability_block,
    _lineage_block,
    _metric_sources,
    _parent_similarity,
    _similarity_sources,
)
from ._record import (
    SCIENTIFIC_AUDIT_SCHEMA_VERSION,
    append_scientific_audit_event,
    attach_scientific_audit,
    scientific_audit_record,
)
from ._summary import (
    SCIENTIFIC_AUDIT_SUMMARY_SCHEMA_VERSION,
    scientific_audit_policy_reasons,
    scientific_audit_summary,
)

__all__ = [
    # Constants
    "SCIENTIFIC_AUDIT_SCHEMA_VERSION",
    "SCIENTIFIC_AUDIT_SUMMARY_SCHEMA_VERSION",
    "FORBIDDEN_SCIENTIFIC_AUDIT_FEEDBACK_SOURCE_TOKENS",
    # Public API
    "attach_scientific_audit",
    "append_scientific_audit_event",
    "scientific_audit_record",
    "scientific_audit_summary",
    "scientific_audit_policy_reasons",
    # Private helpers (re-exported for backward compatibility)
    "_audit_events",
    "_audit_identity",
    "_bool_default",
    "_bump",
    "_evidence_block",
    "_expression_block",
    "_explainability_block",
    "_feedback_sources_include_test_feedback",
    "_first_int",
    "_is_int_like",
    "_lineage_block",
    "_metric_sources",
    "_optional_float",
    "_parent_similarity",
    "_scientific_audit_payloads",
    "_similarity_sources",
]

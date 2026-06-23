"""Audit trail for scoring results, gate decisions, and attribution."""

from __future__ import annotations

from brain_alpha_ops.audit_trail.writer import (
    AUDIT_TRAIL_SCHEMA_VERSION,
    AuditTrailEntry,
    AuditTrailWriter,
    write_scoring_audit,
)

__all__ = [
    "AUDIT_TRAIL_SCHEMA_VERSION",
    "AuditTrailEntry",
    "AuditTrailWriter",
    "write_scoring_audit",
]

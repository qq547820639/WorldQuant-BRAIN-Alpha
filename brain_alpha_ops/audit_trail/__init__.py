"""Audit trail for scoring, lifecycle, gate, and simulation events."""

from __future__ import annotations

from brain_alpha_ops.audit_trail.writer import (
    AUDIT_TRAIL_SCHEMA_VERSION,
    AuditTrailEntry,
    AuditTrailWriter,
    write_scoring_audit,
)
from brain_alpha_ops.audit_trail.anti_overfit import (
    make_strategy_audit_sink,
    record_alpha_origin,
    record_mutation_result,
    record_strategy_event,
)
from brain_alpha_ops.audit_trail.lifecycle_writer import (
    LIFECYCLE_AUDIT_SCHEMA_VERSION,
    LifecycleAuditWriter,
    record_gate_decision,
    record_lifecycle_transition,
    record_optimization_suggestion,
    record_simulation_writeback,
)
from brain_alpha_ops.audit_trail.quality_gate import (
    GateResult,
    QualityGateInterceptor,
    get_quality_gate_interceptor,
)
from brain_alpha_ops.audit_trail.query import (
    AuditQuery,
    AuditQueryResult,
    count_records_by_state,
    find_similar_expressions,
    query_audit_records,
)

__all__ = [
    "AUDIT_TRAIL_SCHEMA_VERSION",
    "LIFECYCLE_AUDIT_SCHEMA_VERSION",
    "AuditQuery",
    "AuditQueryResult",
    "AuditTrailEntry",
    "AuditTrailWriter",
    "GateResult",
    "LifecycleAuditWriter",
    "QualityGateInterceptor",
    "count_records_by_state",
    "find_similar_expressions",
    "get_quality_gate_interceptor",
    "make_strategy_audit_sink",
    "query_audit_records",
    "record_alpha_origin",
    "record_gate_decision",
    "record_lifecycle_transition",
    "record_mutation_result",
    "record_optimization_suggestion",
    "record_simulation_writeback",
    "record_strategy_event",
    "write_scoring_audit",
]

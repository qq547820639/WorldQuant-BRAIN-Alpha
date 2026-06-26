"""Retrospective query interface for lifecycle audit records (B5.1).

Provides filtered search over the lifecycle audit trail JSONL with filters
for: state, date range, dataset, region, universe, score range, gate
failure reason, simulation result, and expression similarity.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from brain_alpha_ops.audit_trail.lifecycle_writer import LifecycleAuditWriter
from brain_alpha_ops.research.expression_diversity import ExpressionDiversityGuard

logger = logging.getLogger(__name__)

_DEFAULT_AUDIT_DIR = "data/audit_trail"


@dataclass
class AuditQuery:
    """Filter criteria for retrospective audit-trail queries."""
    alpha_id: str | None = None
    event_type: str | None = None
    state: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    dataset: str | None = None
    region: str | None = None
    universe: str | None = None
    score_min: float | None = None
    score_max: float | None = None
    gate_name: str | None = None
    gate_passed: bool | None = None
    gate_failure_reason: str | None = None
    sim_result: str | None = None
    expression: str | None = None
    trigger_rule: str | None = None
    limit: int = 200

    def to_dict(self) -> dict[str, Any]:
        return {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in self.__dict__.items() if v is not None
        }


@dataclass
class AuditQueryResult:
    """Result of an audit-trail query."""
    records: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    truncated: bool = False
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records, "total": self.total,
            "truncated": self.truncated, "summary": self.summary,
        }


def query_audit_records(
    query: AuditQuery | None = None,
    *,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
) -> AuditQueryResult:
    """Query lifecycle audit records with filters. Returns ``AuditQueryResult``."""
    q = query or AuditQuery()
    writer = LifecycleAuditWriter(audit_dir)
    entries = writer.iter_all_entries()
    skeleton_cache: dict[str, str] = {}
    guard = ExpressionDiversityGuard() if q.expression else None
    if guard and q.expression:
        skeleton_cache[q.expression] = guard.skeleton(q.expression)

    matched: list[dict[str, Any]] = []
    for record in entries:
        if _matches(record, q, skeleton_cache, guard):
            matched.append(record)
            if len(matched) >= q.limit:
                break

    truncated = len(matched) >= q.limit and len(entries) > len(matched)
    summary = _build_summary(matched)
    return AuditQueryResult(
        records=matched, total=len(matched), truncated=truncated, summary=summary,
    )


def _matches(
    record: dict[str, Any], q: AuditQuery,
    skeleton_cache: dict[str, str], guard: ExpressionDiversityGuard | None,
) -> bool:
    """Check if a record matches all non-None query filters."""
    if q.alpha_id and record.get("alpha_id") != q.alpha_id:
        return False
    if q.event_type and record.get("event_type") != q.event_type:
        return False
    if q.state:
        state = record.get("to_state") or record.get("from_state") or ""
        if q.state != state:
            return False
    if q.trigger_rule:
        if record.get("trigger_rule", "") != q.trigger_rule:
            return False
    if q.date_from or q.date_to:
        ts = _parse_timestamp(record.get("written_at", ""))
        if ts is None:
            return False
        if q.date_from and ts < q.date_from:
            return False
        if q.date_to and ts > q.date_to:
            return False
    if q.dataset:
        if _extract_field(record, "dataset_id", "dataset") != q.dataset:
            return False
    if q.region:
        if _extract_field(record, "region") != q.region:
            return False
    if q.universe:
        if _extract_field(record, "universe") != q.universe:
            return False
    if q.score_min is not None or q.score_max is not None:
        score = _extract_score(record)
        if score is None:
            return False
        if q.score_min is not None and score < q.score_min:
            return False
        if q.score_max is not None and score > q.score_max:
            return False
    if q.gate_name and record.get("gate_name", "") != q.gate_name:
        return False
    if q.gate_passed is not None and record.get("passed") != q.gate_passed:
        return False
    if q.gate_failure_reason:
        reason = str(record.get("reason", "") or "")
        if q.gate_failure_reason.lower() not in reason.lower():
            return False
    if q.sim_result:
        result = _extract_field(record, "simulation_result", "result", "status")
        if q.sim_result.lower() not in str(result or "").lower():
            return False
    if q.expression and guard:
        rec_expr = _extract_field(record, "expression")
        if not rec_expr:
            return False
        rec_skel = skeleton_cache.get(rec_expr)
        if rec_skel is None:
            rec_skel = guard.skeleton(rec_expr)
            skeleton_cache[rec_expr] = rec_skel
        query_skel = skeleton_cache.get(q.expression, "")
        if rec_skel != query_skel:
            return False
    return True


def _extract_field(record: dict[str, Any], *keys: str) -> str:
    """Search record context/sim_config/result_summary for a field."""
    contexts = [
        record.get("context") or {},
        record.get("sim_config") or {},
        record.get("result_summary") or {},
        record.get("attribution") or {},
        record,
    ]
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        for key in keys:
            val = ctx.get(key)
            if val:
                return str(val)
    return ""


def _extract_score(record: dict[str, Any]) -> float | None:
    """Extract a numeric score from various locations in a record."""
    contexts = [
        record.get("context") or {},
        record.get("result_summary") or {},
        record.get("attribution") or {},
    ]
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        for key in ("score", "total_score", "sharpe", "search_score"):
            val = ctx.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
    return None


def _parse_timestamp(raw: str) -> datetime | None:
    """Parse an ISO timestamp from the audit record."""
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (ValueError, TypeError):
        return None


def _build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate summary stats from matched records."""
    by_event: dict[str, int] = {}
    by_state: dict[str, int] = {}
    by_alpha: set[str] = set()
    gate_pass = 0
    gate_fail = 0
    for r in records:
        et = str(r.get("event_type", "") or "unknown")
        by_event[et] = by_event.get(et, 0) + 1
        state = r.get("to_state") or ""
        if state:
            by_state[state] = by_state.get(state, 0) + 1
        aid = r.get("alpha_id", "")
        if aid:
            by_alpha.add(aid)
        if r.get("event_type") == "gate_decision":
            if r.get("passed"):
                gate_pass += 1
            else:
                gate_fail += 1
    return {
        "total_records": len(records),
        "unique_alphas": len(by_alpha),
        "by_event_type": by_event,
        "by_state": by_state,
        "gate_pass_count": gate_pass,
        "gate_fail_count": gate_fail,
    }


def count_records_by_state(
    *, audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
) -> dict[str, int]:
    """Quick aggregate: count lifecycle_transition records grouped by to_state."""
    writer = LifecycleAuditWriter(audit_dir)
    counts: dict[str, int] = {}
    for record in writer.iter_all_entries():
        if record.get("event_type") != "lifecycle_transition":
            continue
        state = str(record.get("to_state", "") or "")
        if not state:
            continue
        counts[state] = counts.get(state, 0) + 1
    return counts


def find_similar_expressions(
    expression: str, *, audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
) -> list[dict[str, Any]]:
    """Find audit records whose expression skeleton matches the query."""
    guard = ExpressionDiversityGuard()
    query_skel = guard.skeleton(expression)
    writer = LifecycleAuditWriter(audit_dir)
    matches: list[dict[str, Any]] = []
    for record in writer.iter_all_entries():
        rec_expr = _extract_field(record, "expression")
        if not rec_expr:
            continue
        if guard.skeleton(rec_expr) == query_skel:
            matches.append(record)
    return matches


# Backward-compat re-export: audit trail export lives in ``export.py`` but
# historical callers and verification scripts import it from ``query.py``.
# Re-export here to keep both import paths working (D3.2).
from brain_alpha_ops.audit_trail.export import (  # noqa: F401  E402
    export_audit_trail as export_audit_trail,
    export_alpha_timeline as export_alpha_timeline,
    query_and_export as query_and_export,
)

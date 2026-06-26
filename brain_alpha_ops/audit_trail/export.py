"""Replayable audit-trail export (Workstream D3.2).

``export_audit_trail`` returns a list of normalised dicts covering the full
candidate lifecycle: scoring evaluations, gate decisions, optimization
suggestions, simulation writebacks, and lifecycle transitions.

Each exported entry includes:
  * scoring_version
  * gate_version
  * capability_version
  * sim_config
  * result_summary
  * change_record

Sources are merged from both ``scoring_audit.jsonl`` (writer.py) and
``lifecycle_audit.jsonl`` (lifecycle_writer.py) so the export is a single
replayable timeline.  Optional filters narrow the export by alpha_id or
arbitrary field predicates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.audit_trail.lifecycle_writer import (
    LIFECYCLE_AUDIT_SCHEMA_VERSION,
    LifecycleAuditWriter,
)
from brain_alpha_ops.audit_trail.query import AuditQuery, query_audit_records
from brain_alpha_ops.audit_trail.writer import (
    AUDIT_TRAIL_SCHEMA_VERSION,
    AuditTrailWriter,
)

logger = logging.getLogger(__name__)

_DEFAULT_AUDIT_DIR = "data/audit_trail"
EXPORT_SCHEMA_VERSION = "audit_export.v1"


def export_audit_trail(
    alpha_id: str | None = None,
    filters: dict[str, Any] | None = None,
    *,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Export a replayable audit trail for one or all candidates.

    Args:
        alpha_id: restrict export to a single candidate (None = all).
        filters: optional field predicates, e.g.
            ``{"event_type": "gate_decision", "passed": False}``.
            Each key/value must match on the record (substring for str,
            equality otherwise).
        audit_dir: directory containing the audit JSONL files.
        limit: maximum number of entries to return.

    Returns a list of normalised dicts sorted by ``written_at`` ascending.
    Each entry includes scoring_version, gate_version, capability_version,
    sim_config, result_summary, and change_record.
    """
    pred = _build_predicate(filters)
    entries: list[dict[str, Any]] = []

    # 1. Scoring audit entries (writer.py — scoring_evaluated / gate_decided).
    scoring_writer = AuditTrailWriter(audit_dir)
    for record in scoring_writer.read_entries(alpha_id=None, limit=limit * 2):
        if alpha_id and record.get("alpha_id") != alpha_id:
            continue
        if not pred(record):
            continue
        entries.append(_normalise_scoring_entry(record))

    # 2. Lifecycle audit entries (lifecycle_writer.py — transitions / gates /
    #    optimization / simulation writebacks).
    lifecycle_writer = LifecycleAuditWriter(audit_dir)
    for record in lifecycle_writer.iter_all_entries():
        if alpha_id and record.get("alpha_id") != alpha_id:
            continue
        if not pred(record):
            continue
        entries.append(_normalise_lifecycle_entry(record))
        if len(entries) >= limit:
            break

    entries.sort(key=lambda e: str(e.get("written_at") or ""))
    return entries[:limit]


def export_alpha_timeline(
    alpha_id: str,
    *,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
    limit: int = 500,
) -> dict[str, Any]:
    """Convenience wrapper: full replayable timeline for a single alpha."""
    entries = export_audit_trail(alpha_id=alpha_id, audit_dir=audit_dir, limit=limit)
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "alpha_id": alpha_id,
        "entry_count": len(entries),
        "timeline": entries,
        "capability_version": _first(entries, "capability_version"),
        "scoring_version": _first(entries, "scoring_version"),
        "gate_version": _first(entries, "gate_version"),
    }


def query_and_export(
    query: AuditQuery | None = None,
    *,
    audit_dir: str | Path = _DEFAULT_AUDIT_DIR,
) -> list[dict[str, Any]]:
    """Run an ``AuditQuery`` then export the matched records in normalised form."""
    result = query_audit_records(query, audit_dir=audit_dir)
    return [_normalise_lifecycle_entry(r) for r in result.records]


# --- Normalisation helpers --------------------------------------------------


def _normalise_scoring_entry(record: dict[str, Any]) -> dict[str, Any]:
    """Normalise a scoring_audit.jsonl record to the export schema."""
    return {
        "export_schema": EXPORT_SCHEMA_VERSION,
        "entry_id": record.get("entry_id", ""),
        "alpha_id": record.get("alpha_id", ""),
        "event_type": record.get("event_type", "scoring_evaluated"),
        "written_at": record.get("written_at", ""),
        "source_file": "scoring_audit.jsonl",
        "scoring_version": record.get("scoring_version", ""),
        "gate_version": record.get("threshold_version", ""),
        "capability_version": _capability_version_from(record),
        "sim_config": _extract_sim_config(record),
        "result_summary": {
            "total_score": record.get("total_score", 0.0),
            "decision_band": record.get("decision_band", ""),
            "passed_gate": record.get("passed_gate", False),
            "attribution_summary": record.get("attribution_summary", ""),
        },
        "change_record": {
            "field": "scorecard",
            "gate_decisions": record.get("gate_decisions", []),
            "triggered_rules": record.get("triggered_rules", []),
        },
        "details": record.get("details", {}),
    }


def _normalise_lifecycle_entry(record: dict[str, Any]) -> dict[str, Any]:
    """Normalise a lifecycle_audit.jsonl record to the export schema."""
    event_type = str(record.get("event_type", "") or "")
    return {
        "export_schema": EXPORT_SCHEMA_VERSION,
        "entry_id": record.get("entry_id", ""),
        "alpha_id": record.get("alpha_id", ""),
        "event_type": event_type,
        "written_at": record.get("written_at", ""),
        "source_file": "lifecycle_audit.jsonl",
        "scoring_version": record.get("scoring_version", ""),
        "gate_version": record.get("gate_version", ""),
        "capability_version": record.get("capability_version", ""),
        "sim_config": record.get("sim_config", {}) or {},
        "result_summary": _lifecycle_result_summary(record, event_type),
        "change_record": record.get("change_record", {}) or {},
        "details": {
            "reason": record.get("reason", ""),
            "trigger_rule": record.get("trigger_rule", ""),
            "attribution": record.get("attribution", {}) or {},
            "context": record.get("context", {}) or {},
        },
    }


def _lifecycle_result_summary(record: dict[str, Any], event_type: str) -> dict[str, Any]:
    """Build a result_summary appropriate to the event type."""
    if event_type == "lifecycle_transition":
        return {
            "from_state": record.get("from_state", ""),
            "to_state": record.get("to_state", ""),
            "reason": record.get("reason", ""),
        }
    if event_type == "gate_decision":
        return {
            "gate_name": record.get("gate_name", ""),
            "passed": record.get("passed", False),
            "reason": record.get("reason", ""),
        }
    if event_type == "optimization_suggestion":
        return {
            "suggestion": record.get("suggestion", ""),
            "expected_effect": record.get("expected_effect", ""),
            "parent_failure": record.get("parent_failure", ""),
        }
    if event_type == "simulation_writeback":
        return record.get("result_summary", {}) or {}
    return {}


def _extract_sim_config(record: dict[str, Any]) -> dict[str, Any]:
    sim_config = record.get("sim_config")
    if isinstance(sim_config, dict):
        return sim_config
    details = record.get("details")
    if isinstance(details, dict):
        cfg = details.get("sim_config")
        if isinstance(cfg, dict):
            return cfg
    return {}


def _capability_version_from(record: dict[str, Any]) -> str:
    for key in ("capability_version", "capability_registry_version"):
        val = record.get(key)
        if val:
            return str(val)
    return ""


def _first(entries: list[dict[str, Any]], key: str) -> str:
    for entry in entries:
        val = entry.get(key)
        if val:
            return str(val)
    return ""


def _build_predicate(
    filters: dict[str, Any] | None,
) -> Callable[[dict[str, Any]], bool]:
    """Build a predicate function from a filters dict."""
    if not filters:
        return lambda _record: True

    def _pred(record: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            actual = record.get(key)
            if expected is None:
                continue
            if isinstance(expected, str) and isinstance(actual, str):
                if expected.lower() not in actual.lower():
                    return False
            elif actual != expected:
                return False
        return True

    return _pred


__all__ = [
    "EXPORT_SCHEMA_VERSION",
    "export_alpha_timeline",
    "export_audit_trail",
    "query_and_export",
]

"""Decision annotation and aggregation helpers."""

from __future__ import annotations

from collections import Counter
from typing import Any

from brain_alpha_ops.web_candidates.audit import attach_scientific_audit

from ._decision import DEFAULT_OFFICIAL_SIMULATION_SCORE, candidate_production_decision
from ._evidence import _merge_existing_scientific_audit_decision_evidence
from ._helpers import _GENERIC_POOL_STATUSES, _status


def annotate_candidate_decision(
    row: dict[str, Any],
    *,
    min_official_score: float = DEFAULT_OFFICIAL_SIMULATION_SCORE,
    update_lifecycle: bool = False,
) -> dict[str, Any]:
    """Return a copy of ``row`` with a traceable production decision attached."""

    annotated = dict(row)
    decision = candidate_production_decision(annotated, min_official_score=min_official_score)
    annotated["production_decision"] = decision
    annotated["decision_action"] = decision["action"]
    annotated["decision_reason"] = decision["reason"]
    diagnosis = annotated.get("quality_diagnosis") if isinstance(annotated.get("quality_diagnosis"), dict) else {}
    annotated["quality_diagnosis"] = {**diagnosis, "production_decision": decision}
    extra_fields = annotated.get("extra_fields") if isinstance(annotated.get("extra_fields"), dict) else {}
    annotated["extra_fields"] = {**extra_fields, "production_decision": decision}
    if update_lifecycle and _status(annotated) in _GENERIC_POOL_STATUSES:
        annotated["lifecycle_status"] = decision["next_state"]
    extra_fields = annotated.get("extra_fields") if isinstance(annotated.get("extra_fields"), dict) else {}
    existing_audit = annotated.get("scientific_audit") if isinstance(annotated.get("scientific_audit"), dict) else extra_fields.get("scientific_audit")
    if isinstance(existing_audit, dict):
        audit = _merge_existing_scientific_audit_decision_evidence(existing_audit, decision)
        annotated["scientific_audit"] = audit
        annotated["extra_fields"] = {**extra_fields, "scientific_audit": audit}
    else:
        feedback_sources = ["scorecard", "quality_gate"]
        evidence = decision.get("decision_evidence") if isinstance(decision.get("decision_evidence"), dict) else {}
        if evidence.get("lifecycle_risk"):
            feedback_sources.append("lifecycle_history")
        if evidence.get("scientific_audit_policy_reasons"):
            feedback_sources.append("scientific_audit")
        annotated = attach_scientific_audit(
            annotated,
            operation="production_decision",
            source=str(decision.get("source") or "scorecard_quality_gate"),
            feedback_sources=feedback_sources,
            decision=decision,
        )
    return annotated


def decision_action_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else None
        action = str((decision or candidate_production_decision(row)).get("action") or "retain")
        counts[action] += 1
    return dict(sorted(counts.items()))


def candidate_decision_action(row: dict[str, Any]) -> str:
    decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
    return str((decision or candidate_production_decision(row)).get("action") or "retain")


def candidate_decision_blocking(row: dict[str, Any]) -> bool:
    decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
    return bool((decision or candidate_production_decision(row)).get("blocking"))

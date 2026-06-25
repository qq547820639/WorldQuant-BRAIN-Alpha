"""Decision evidence and lifecycle risk normalization."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_candidates.audit import scientific_audit_policy_reasons
from brain_alpha_ops.web_candidates.lifecycle_risk import (
    LIFECYCLE_RISK_SCHEMA_VERSION,
    existing_lifecycle_risk,
)

from ._helpers import _lifecycle_text, _safe_int


def candidate_decision_evidence(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize local evidence that should affect non-submit decisions."""

    lifecycle_risk = existing_lifecycle_risk(row)
    hard_reasons = set(scientific_audit_policy_reasons(row))
    evidence = {
        "schema_version": "candidate-decision-evidence-v1",
        "source": "local_candidate_evidence",
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "hard_blocking_reasons": sorted(hard_reasons),
        "scientific_audit_policy_reasons": scientific_audit_policy_reasons(row),
    }
    if lifecycle_risk:
        compact_risk = _compact_lifecycle_risk(lifecycle_risk)
        evidence["lifecycle_risk"] = compact_risk
        evidence["lifecycle_replay"] = _lifecycle_replay_evidence(compact_risk)
    return evidence


def _lifecycle_replay_evidence(lifecycle_risk: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "candidate-lifecycle-replay-evidence-v1",
        "source": _lifecycle_text(lifecycle_risk.get("source"), default="lifecycle_jsonl"),
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "recovered_from_local_history": True,
        "matched_event_count": _safe_int(lifecycle_risk.get("matched_event_count")),
        "matched_by": _lifecycle_text(lifecycle_risk.get("matched_by")),
        "latest_stage": _lifecycle_text(lifecycle_risk.get("latest_stage")),
        "latest_status": _lifecycle_text(lifecycle_risk.get("latest_status")),
        "latest_status_category": _lifecycle_text(lifecycle_risk.get("latest_status_category")),
        "latest_event_at": _lifecycle_text(lifecycle_risk.get("latest_event_at")),
        "action_hint": _lifecycle_text(lifecycle_risk.get("action_hint")),
        "reason_code": _lifecycle_text(lifecycle_risk.get("reason_code")),
    }


def _compact_lifecycle_risk(lifecycle_risk: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": _lifecycle_text(lifecycle_risk.get("schema_version"), default=LIFECYCLE_RISK_SCHEMA_VERSION),
        "source": _lifecycle_text(lifecycle_risk.get("source"), default="lifecycle_jsonl"),
        "local_only": lifecycle_risk.get("local_only") is not False,
        "official_api_called": lifecycle_risk.get("official_api_called") is True,
        "submit_allowed": lifecycle_risk.get("submit_allowed") is True,
        "matched_event_count": _safe_int(lifecycle_risk.get("matched_event_count")),
        "matched_by": _lifecycle_text(lifecycle_risk.get("matched_by")),
        "latest_stage": _lifecycle_text(lifecycle_risk.get("latest_stage")),
        "latest_status": _lifecycle_text(lifecycle_risk.get("latest_status")),
        "latest_status_category": _lifecycle_text(lifecycle_risk.get("latest_status_category")),
        "latest_event_at": _lifecycle_text(lifecycle_risk.get("latest_event_at")),
        "action_hint": _lifecycle_text(lifecycle_risk.get("action_hint")),
        "blocking": lifecycle_risk.get("blocking") is True,
        "reason_code": _lifecycle_text(lifecycle_risk.get("reason_code")),
    }


def _merge_existing_scientific_audit_decision_evidence(
    existing_audit: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    decision_evidence = decision.get("decision_evidence") if isinstance(decision.get("decision_evidence"), dict) else {}
    lifecycle_replay = (
        decision_evidence.get("lifecycle_replay")
        if isinstance(decision_evidence.get("lifecycle_replay"), dict)
        else {}
    )
    if not lifecycle_replay:
        return existing_audit

    audit = dict(existing_audit)
    evidence = dict(audit.get("evidence") if isinstance(audit.get("evidence"), dict) else {})
    sources = {str(item) for item in evidence.get("feedback_sources") or [] if str(item)}
    sources.add("lifecycle_history")
    evidence["feedback_sources"] = sorted(sources)
    evidence["lifecycle_replay"] = lifecycle_replay
    audit["evidence"] = evidence
    return audit

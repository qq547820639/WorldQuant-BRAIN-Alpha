"""Scientific audit summary and policy inspection."""

from __future__ import annotations

from typing import Any

from ._helpers import (
    _audit_events,
    _bump,
    _feedback_sources_include_test_feedback,
    _scientific_audit_payloads,
)
from ._record import SCIENTIFIC_AUDIT_SCHEMA_VERSION

SCIENTIFIC_AUDIT_SUMMARY_SCHEMA_VERSION = "candidate-scientific-audit-summary-v1"


def scientific_audit_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    audited = 0
    missing = 0
    audit_payloads = 0
    official_calls = 0
    submit_allowed = 0
    real_submit_performed = 0
    test_feedback = 0
    operations: dict[str, int] = {}
    sources: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        total += 1
        audits = [
            audit
            for audit in _scientific_audit_payloads(row)
            if audit.get("schema_version") == SCIENTIFIC_AUDIT_SCHEMA_VERSION
        ]
        if not audits:
            missing += 1
            continue
        audited += 1
        audit_payloads += len(audits)
        row_official_api_called = False
        row_submit_allowed = False
        row_real_submit_performed = False
        row_test_feedback = False
        for audit in audits:
            boundary = audit.get("safety_boundary") if isinstance(audit.get("safety_boundary"), dict) else {}
            anti = audit.get("anti_overfit") if isinstance(audit.get("anti_overfit"), dict) else {}
            evidence = audit.get("evidence") if isinstance(audit.get("evidence"), dict) else {}
            if boundary.get("official_api_called") is True:
                row_official_api_called = True
            if boundary.get("submit_allowed") is True:
                row_submit_allowed = True
            if boundary.get("real_submit_performed") is True:
                row_real_submit_performed = True
            for event in _audit_events(audit):
                details = event.get("details") if isinstance(event.get("details"), dict) else {}
                if event.get("official_api_called") is True or details.get("official_api_called") is True:
                    row_official_api_called = True
                if event.get("submit_allowed") is True or details.get("submit_allowed") is True:
                    row_submit_allowed = True
                if event.get("real_submit_performed") is True or details.get("real_submit_performed") is True:
                    row_real_submit_performed = True
            if (
                anti.get("test_script_outcomes_used") is True
                or anti.get("test_feedback_allowed") is True
                or _feedback_sources_include_test_feedback(evidence.get("feedback_sources") or [])
            ):
                row_test_feedback = True
            _bump(operations, str(audit.get("operation") or "unknown"))
            _bump(sources, str(audit.get("source") or "unknown"))
        if row_official_api_called:
            official_calls += 1
        if row_submit_allowed:
            submit_allowed += 1
        if row_real_submit_performed:
            real_submit_performed += 1
        if row_test_feedback:
            test_feedback += 1
    return {
        "schema_version": SCIENTIFIC_AUDIT_SUMMARY_SCHEMA_VERSION,
        "candidate_count": total,
        "audited_count": audited,
        "missing_audit_count": missing,
        "audit_payload_count": audit_payloads,
        "official_api_called_count": official_calls,
        "submit_allowed_count": submit_allowed,
        "real_submit_performed_count": real_submit_performed,
        "test_feedback_used_count": test_feedback,
        "operations": dict(sorted(operations.items())),
        "sources": dict(sorted(sources.items())),
        "non_submit_boundary_intact": (
            official_calls == 0
            and submit_allowed == 0
            and real_submit_performed == 0
            and test_feedback == 0
        ),
    }


def scientific_audit_policy_reasons(row: dict[str, Any]) -> list[str]:
    """Return hard policy blockers from every persisted audit copy."""

    reasons: set[str] = set()
    for audit in _scientific_audit_payloads(row):
        anti = audit.get("anti_overfit") if isinstance(audit.get("anti_overfit"), dict) else {}
        boundary = audit.get("safety_boundary") if isinstance(audit.get("safety_boundary"), dict) else {}
        evidence = audit.get("evidence") if isinstance(audit.get("evidence"), dict) else {}
        explainability = audit.get("explainability") if isinstance(audit.get("explainability"), dict) else {}
        optimization = (
            explainability.get("optimization_explanation")
            if isinstance(explainability.get("optimization_explanation"), dict)
            else {}
        )
        official_context = optimization.get("official_context") if isinstance(optimization.get("official_context"), dict) else {}
        official_proof = explainability.get("official_context_proof") if isinstance(explainability.get("official_context_proof"), dict) else {}
        if anti.get("test_script_outcomes_used") is True or anti.get("test_feedback_allowed") is True:
            reasons.add("scientific_audit_test_feedback_used")
        if _feedback_sources_include_test_feedback(evidence.get("feedback_sources") or []):
            reasons.add("scientific_audit_test_feedback_used")
        if boundary.get("submit_allowed") is True or boundary.get("real_submit_performed") is True:
            reasons.add("scientific_audit_submit_boundary_breached")
        for event in _audit_events(audit):
            details = event.get("details") if isinstance(event.get("details"), dict) else {}
            if (
                event.get("submit_allowed") is True
                or event.get("real_submit_performed") is True
                or details.get("submit_allowed") is True
                or details.get("real_submit_performed") is True
            ):
                reasons.add("scientific_audit_submit_boundary_breached")
        if official_context.get("passed") is False or official_proof.get("passed") is False:
            reasons.add("official_context_proof_failed")
    return sorted(reasons)

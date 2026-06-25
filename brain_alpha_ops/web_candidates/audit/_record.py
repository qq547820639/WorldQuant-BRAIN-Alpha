"""Scientific audit record creation and attachment."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.expression_ast import expression_profile_summary

from ._blocks import (
    _evidence_block,
    _expression_block,
    _explainability_block,
    _lineage_block,
    _parent_similarity,
    _similarity_sources,
)
from ._helpers import _bool_default, _first_int

SCIENTIFIC_AUDIT_SCHEMA_VERSION = "candidate-scientific-audit-v1"


def attach_scientific_audit(
    row: dict[str, Any],
    *,
    operation: str,
    source: str,
    feedback_sources: list[str] | None = None,
    parent: dict[str, Any] | None = None,
    search_row: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``row`` with a compact, redacted scientific audit envelope.

    The audit is intentionally descriptive. It preserves provenance and safety
    boundaries, but it never introduces a rule that can tune Alpha expressions
    from unit-test or browser-smoke outcomes.
    """

    candidate = dict(row or {})
    audit = scientific_audit_record(
        candidate,
        operation=operation,
        source=source,
        feedback_sources=feedback_sources,
        parent=parent,
        search_row=search_row,
        decision=decision,
    )
    candidate["scientific_audit"] = audit
    extra_fields = candidate.get("extra_fields") if isinstance(candidate.get("extra_fields"), dict) else {}
    candidate["extra_fields"] = {**extra_fields, "scientific_audit": audit}
    return candidate


def append_scientific_audit_event(
    row: dict[str, Any],
    *,
    operation: str,
    source: str,
    feedback_sources: list[str] | None = None,
    official_api_called: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a redacted scientific-audit event without changing submit safety.

    Official simulation and pre-submit checks are validation evidence, not submit
    permission.  Event-level ``official_api_called`` records that evidence while
    the top-level safety boundary remains non-submit.
    """

    candidate = dict(row or {})
    extra_fields = candidate.get("extra_fields") if isinstance(candidate.get("extra_fields"), dict) else {}
    existing = candidate.get("scientific_audit") if isinstance(candidate.get("scientific_audit"), dict) else extra_fields.get("scientific_audit")
    created = not isinstance(existing, dict) or existing.get("schema_version") != SCIENTIFIC_AUDIT_SCHEMA_VERSION
    if created:
        candidate = attach_scientific_audit(
            candidate,
            operation=operation,
            source=source,
            feedback_sources=feedback_sources,
        )
        existing = candidate["scientific_audit"]
        extra_fields = candidate.get("extra_fields") if isinstance(candidate.get("extra_fields"), dict) else {}

    audit = dict(existing)
    events = [] if created else [dict(event) for event in audit.get("events") or [] if isinstance(event, dict)]
    events.append({
        "operation": str(operation or "candidate_production"),
        "source": str(source or "web_candidate_pool"),
        "timestamp": utc_now(),
        "official_api_called": bool(official_api_called),
        "details": details if isinstance(details, dict) else {},
    })
    audit["events"] = events
    evidence = dict(audit.get("evidence") if isinstance(audit.get("evidence"), dict) else {})
    merged_sources = set(str(item) for item in evidence.get("feedback_sources") or [] if str(item))
    merged_sources.update(str(item) for item in feedback_sources or [] if str(item))
    evidence["feedback_sources"] = sorted(merged_sources)
    audit["evidence"] = evidence
    boundary = dict(audit.get("safety_boundary") if isinstance(audit.get("safety_boundary"), dict) else {})
    boundary["submit_allowed"] = False
    boundary["real_submit_performed"] = False
    audit["safety_boundary"] = boundary
    clean = redact_data(audit)
    final_audit = clean if isinstance(clean, dict) else audit
    candidate["scientific_audit"] = final_audit
    candidate["extra_fields"] = {**extra_fields, "scientific_audit": final_audit}
    return candidate


def scientific_audit_record(
    row: dict[str, Any],
    *,
    operation: str,
    source: str,
    feedback_sources: list[str] | None = None,
    parent: dict[str, Any] | None = None,
    search_row: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expression = str(row.get("expression") or "")
    parent_expression = str((parent or {}).get("expression") or row.get("parent_expression") or "")
    expression_summary = expression_profile_summary(expression) if expression else {}
    search_metadata = search_row.get("metadata") if isinstance(search_row, dict) and isinstance(search_row.get("metadata"), dict) else {}
    quality_diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    submission = row.get("submission") if isinstance(row.get("submission"), dict) else {}
    audit = {
        "schema_version": SCIENTIFIC_AUDIT_SCHEMA_VERSION,
        "created_at": utc_now(),
        "operation": str(operation or "candidate_production"),
        "source": str(source or "web_candidate_pool"),
        "candidate": {
            "alpha_id": str(row.get("alpha_id") or ""),
            "dataset_id": str(row.get("dataset_id") or ""),
            "family": str(row.get("family") or ""),
            "lifecycle_status": str(row.get("lifecycle_status") or ""),
            "source_tags": [str(tag) for tag in row.get("source_tags") or [] if str(tag)],
        },
        "expression": _expression_block(expression_summary),
        "lineage": _lineage_block(row, parent=parent, search_row=search_row, search_metadata=search_metadata),
        "explainability": _explainability_block(row),
        "evidence": _evidence_block(
            row,
            feedback_sources=feedback_sources,
            scorecard=scorecard,
            quality_diagnosis=quality_diagnosis,
            local_quality=local_quality,
            decision=decision,
        ),
        "anti_overfit": {
            "test_script_outcomes_used": False,
            "test_feedback_allowed": False,
            "feedback_policy": "system-tests-verify-behavior-only",
            "parent_similarity": _parent_similarity(expression, parent_expression),
            "duplicate_or_similarity_sources": _similarity_sources(row),
        },
        "retry": {
            "retry_count": _first_int(submission.get("retry_count"), row.get("retry_count"), default=0),
            "poll_count": _first_int(submission.get("poll_count"), row.get("poll_count"), default=0),
            "bounded": True,
        },
        "safety_boundary": {
            "local_only": _bool_default(row.get("local_only"), True),
            "official_api_called": bool(row.get("official_api_called") is True),
            "submit_allowed": False,
            "real_submit_performed": False,
        },
        "events": [
            {
                "operation": str(operation or "candidate_production"),
                "source": str(source or "web_candidate_pool"),
                "timestamp": utc_now(),
            }
        ],
    }
    clean = redact_data(audit)
    return clean if isinstance(clean, dict) else audit

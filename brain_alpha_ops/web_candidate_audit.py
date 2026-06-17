"""Scientific audit helpers for Web candidate production.

The audit contract records why an Alpha candidate changed state without using
test outcomes to tune expressions and without weakening the separate BRAIN
submit-readiness gate.
"""

from __future__ import annotations

import json
from typing import Any

from brain_alpha_ops.models import utc_now
from brain_alpha_ops.redaction import redact_data
from brain_alpha_ops.research.expression_ast import expression_profile_summary, expression_similarity


SCIENTIFIC_AUDIT_SCHEMA_VERSION = "candidate-scientific-audit-v1"
SCIENTIFIC_AUDIT_SUMMARY_SCHEMA_VERSION = "candidate-scientific-audit-summary-v1"
FORBIDDEN_SCIENTIFIC_AUDIT_FEEDBACK_SOURCE_TOKENS = (
    "pytest",
    "fixture",
    "fixtures",
    "unit_test",
    "unit-test",
    "test_result",
    "browser_smoke",
    "browser-smoke",
    "vitest",
)


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


def _audit_events(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in audit.get("events") or [] if isinstance(event, dict)]


def _scientific_audit_payloads(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Return unique audit payloads from all persisted candidate locations.

    Older writeback paths can leave a stale copy under ``extra_fields`` while a
    newer top-level copy looks safe.  Summaries must inspect both locations so
    the research workflow fails closed instead of hiding unsafe provenance.
    """

    payloads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for audit in (
        row.get("scientific_audit"),
        (row.get("extra_fields") or {}).get("scientific_audit")
        if isinstance(row.get("extra_fields"), dict)
        else None,
    ):
        if not isinstance(audit, dict):
            continue
        identity = _audit_identity(audit)
        if identity in seen:
            continue
        seen.add(identity)
        payloads.append(audit)
    return payloads


def _audit_identity(audit: dict[str, Any]) -> str:
    try:
        return json.dumps(audit, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return repr(audit)


def _feedback_sources_include_test_feedback(sources: Any) -> bool:
    for source in sources if isinstance(sources, list) else []:
        normalized = str(source or "").strip().lower()
        if any(token in normalized for token in FORBIDDEN_SCIENTIFIC_AUDIT_FEEDBACK_SOURCE_TOKENS):
            return True
    return False


def _expression_block(summary: dict[str, Any]) -> dict[str, Any]:
    profile = summary.get("expression_profile") if isinstance(summary.get("expression_profile"), dict) else {}
    return {
        "expression_canonical": str(summary.get("expression_canonical") or ""),
        "expression_fingerprint": str(summary.get("expression_fingerprint") or ""),
        "operators": [str(item) for item in profile.get("operators") or [] if str(item)],
        "fields": [str(item) for item in profile.get("fields") or [] if str(item)],
        "windows": [int(item) for item in profile.get("windows") or [] if _is_int_like(item)],
        "parsed": bool(profile.get("parsed")),
    }


def _lineage_block(
    row: dict[str, Any],
    *,
    parent: dict[str, Any] | None,
    search_row: dict[str, Any] | None,
    search_metadata: dict[str, Any],
) -> dict[str, Any]:
    lineage = search_metadata.get("lineage") if isinstance(search_metadata.get("lineage"), dict) else {}
    variant_reason = (
        search_metadata.get("reason")
        or (search_row or {}).get("reason")
        or ((row.get("submission") or {}) if isinstance(row.get("submission"), dict) else {}).get("variant_reason")
        or ""
    )
    return {
        "parent_alpha_id": str((parent or {}).get("alpha_id") or lineage.get("parent_alpha_id") or row.get("parent_id") or ""),
        "parent_expression_fingerprint": str(
            expression_profile_summary(str((parent or {}).get("expression") or lineage.get("parent_expression") or "")).get("expression_fingerprint")
            if ((parent or {}).get("expression") or lineage.get("parent_expression"))
            else ""
        ),
        "mutation_type": str(row.get("mutation_type") or (search_row or {}).get("mutation_mode") or ""),
        "variant_reason": str(variant_reason or ""),
    }


def _explainability_block(row: dict[str, Any]) -> dict[str, Any]:
    extra_fields = row.get("extra_fields") if isinstance(row.get("extra_fields"), dict) else {}
    proof = row.get("official_context_proof") if isinstance(row.get("official_context_proof"), dict) else extra_fields.get("official_context_proof")
    delta = row.get("expression_delta") if isinstance(row.get("expression_delta"), dict) else extra_fields.get("expression_delta")
    optimization_explanation = (
        row.get("optimization_explanation")
        if isinstance(row.get("optimization_explanation"), dict)
        else extra_fields.get("optimization_explanation")
    )
    return {
        "official_context_proof": proof if isinstance(proof, dict) else {},
        "expression_delta": delta if isinstance(delta, dict) else {},
        "optimization_explanation": optimization_explanation if isinstance(optimization_explanation, dict) else {},
    }


def _evidence_block(
    row: dict[str, Any],
    *,
    feedback_sources: list[str] | None,
    scorecard: dict[str, Any],
    quality_diagnosis: dict[str, Any],
    local_quality: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    production_decision = decision if isinstance(decision, dict) else (
        row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
    )
    evidence = {
        "feedback_sources": sorted({str(item) for item in feedback_sources or [] if str(item)}),
        "metric_sources": _metric_sources(row, local_quality=local_quality),
        "score": _optional_float(scorecard.get("total_score", row.get("score"))),
        "decision_band": str(scorecard.get("decision_band") or row.get("decision_band") or ""),
        "production_action": str(production_decision.get("action") or ""),
        "production_reason_codes": [
            str(code)
            for code in production_decision.get("reason_codes") or quality_diagnosis.get("blocking_reasons") or []
            if str(code)
        ],
        "quality_status": str(quality_diagnosis.get("status") or row.get("lifecycle_status") or ""),
    }
    decision_evidence = (
        production_decision.get("decision_evidence")
        if isinstance(production_decision.get("decision_evidence"), dict)
        else {}
    )
    lifecycle_replay = (
        decision_evidence.get("lifecycle_replay")
        if isinstance(decision_evidence.get("lifecycle_replay"), dict)
        else {}
    )
    if lifecycle_replay:
        evidence["lifecycle_replay"] = lifecycle_replay
    return evidence


def _metric_sources(row: dict[str, Any], *, local_quality: dict[str, Any]) -> list[str]:
    sources = {"scorecard"}
    if local_quality:
        sources.add("local_quality")
    if isinstance(local_quality.get("local_backtest"), dict):
        sources.add("local_backtest_prefilter")
    if row.get("official_alpha_id") or row.get("simulation_id") or row.get("official_metrics"):
        sources.add("official_evidence")
    return sorted(sources)


def _parent_similarity(expression: str, parent_expression: str) -> float | None:
    if not expression or not parent_expression:
        return None
    return expression_similarity(expression, parent_expression)


def _similarity_sources(row: dict[str, Any]) -> list[str]:
    sources: set[str] = set()
    for key in ("cloud_correlation_risk", "cloud_similarity_risk", "similarity_risk"):
        if isinstance(row.get(key), dict):
            sources.add(key)
    extra_fields = row.get("extra_fields") if isinstance(row.get("extra_fields"), dict) else {}
    if isinstance(extra_fields.get("expression_index"), dict):
        sources.add("expression_index")
    return sorted(sources)


def _first_int(*values: Any, default: int) -> int:
    for value in values:
        if _is_int_like(value):
            return int(value)
    return int(default)


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _bool_default(value: Any, default: bool) -> bool:
    return default if value is None else bool(value)


def _is_int_like(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key or "unknown"] = counter.get(key or "unknown", 0) + 1

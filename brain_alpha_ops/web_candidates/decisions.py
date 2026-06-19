"""Production decisions for Web candidate-pool rows."""

from __future__ import annotations

from collections import Counter
from typing import Any

from brain_alpha_ops.redaction import redact_text
from brain_alpha_ops.web_candidates.audit import (
    attach_scientific_audit,
    scientific_audit_policy_reasons,
)
from brain_alpha_ops.web_candidates.lifecycle_risk import (
    LIFECYCLE_RISK_SCHEMA_VERSION,
    existing_lifecycle_risk,
    lifecycle_history_requires_rework,
    lifecycle_history_should_archive,
)

DEFAULT_OFFICIAL_SIMULATION_SCORE = 70.0
DECISION_SCHEMA_VERSION = "candidate-production-decision-v1"


def _is_submit_only_quality_reason(code: str, category: str = "") -> bool:
    """Lazy import wrapper avoiding circular import through web_backtest_slots."""
    from brain_alpha_ops.web.misc.web_backtest_slots import is_submit_only_quality_reason as _fn

    return _fn(code, category)


_ARCHIVE_STATUS_TOKENS = (
    "local_prefilter_rejected",
    "local_standard_rejected",
    "official_standard_rejected",
    "candidate_pool_pruned",
    "high_cloud_similarity",
    "hard_gate_blocked",
    "rejected",
    "failed",
)
_GENERIC_POOL_STATUSES = {
    "",
    "created",
    "candidate_pool_retained",
    "locally_scored",
}


def candidate_production_decision(
    row: dict[str, Any],
    *,
    min_official_score: float = DEFAULT_OFFICIAL_SIMULATION_SCORE,
) -> dict[str, Any]:
    """Return the service decision that drives candidate-pool state transitions.

    The decision is deliberately local and non-submit. It routes candidates to
    optimization, official-validation queue, archive, or human review without
    weakening the separate live-submit readiness gate.
    """

    score = candidate_score(row)
    band = _decision_band(row)
    hard_reasons = candidate_hard_blocking_reasons(row)
    submit_only_reasons = candidate_submit_only_reasons(row)
    status = _status(row)
    official_evidence = candidate_has_official_evidence(row)
    decision_evidence = candidate_decision_evidence(row)
    evidence_hard_reasons = decision_evidence.get("hard_blocking_reasons", [])

    if evidence_hard_reasons:
        return _decision(
            "archive",
            "archived",
            "scientific audit or lifecycle evidence failed the local decision policy",
            score=score,
            decision_band=band,
            blocking=True,
            reason_codes=list(evidence_hard_reasons),
            decision_evidence=decision_evidence,
            source="scorecard_quality_gate_decision_evidence",
        )

    if hard_reasons or any(token in status for token in _ARCHIVE_STATUS_TOKENS):
        return _decision(
            "archive",
            "archived",
            "quality gate found hard local or official blockers",
            score=score,
            decision_band=band,
            blocking=True,
            reason_codes=hard_reasons or [status],
            decision_evidence=decision_evidence,
        )

    if lifecycle_history_should_archive(row):
        risk = existing_lifecycle_risk(row)
        return _decision(
            "archive",
            "archived",
            "latest local lifecycle history says this candidate should not occupy production capacity",
            score=score,
            decision_band=band,
            blocking=True,
            reason_codes=[str(risk.get("reason_code") or "lifecycle_history_blocked")],
            decision_evidence=decision_evidence,
            source="scorecard_quality_gate_lifecycle_history",
        )

    if lifecycle_history_requires_rework(row):
        risk = existing_lifecycle_risk(row)
        return _decision(
            "optimize",
            "needs_optimization",
            "latest local lifecycle history requires rework before official validation or main-pool retention",
            score=score,
            decision_band=band,
            blocking=False,
            reason_codes=[str(risk.get("reason_code") or "lifecycle_history_failed")],
            decision_evidence=decision_evidence,
            source="scorecard_quality_gate_lifecycle_history",
        )

    if _has_human_confirmation_blocker(row):
        return _decision(
            "needs_human_confirmation",
            "ready_for_review",
            "candidate qualifies but requires explicit human confirmation before submit",
            score=score,
            decision_band=band,
            blocking=False,
            reason_codes=submit_only_reasons or ["needs_human_confirmation"],
            decision_evidence=decision_evidence,
        )

    if candidate_submission_ready(row):
        return _decision(
            "submit_review_blocked",
            "ready_for_review",
            "submission evidence is ready, but Web production stays non-submit until live readiness and human approval",
            score=score,
            decision_band=band,
            blocking=False,
            reason_codes=submit_only_reasons or ["manual_submit_review_required"],
            decision_evidence=decision_evidence,
        )

    if band == "hard_gate_blocked":
        return _decision(
            "archive",
            "archived",
            "scorecard hard gate blocked the candidate",
            score=score,
            decision_band=band,
            blocking=True,
            reason_codes=["hard_gate_blocked"],
            decision_evidence=decision_evidence,
        )

    if band == "submit_candidate" and not official_evidence and score >= float(min_official_score):
        return _decision(
            "official_validation_queue",
            "queued_for_simulation",
            "scorecard ranks this as the next best use of scarce official validation capacity",
            score=score,
            decision_band=band,
            blocking=False,
            reason_codes=submit_only_reasons or ["missing_official_evidence"],
            decision_evidence=decision_evidence,
        )

    if band in {"optimize_before_submit", "optimize"}:
        return _decision(
            "optimize",
            "needs_optimization",
            "scorecard says the candidate should be improved before official validation or review",
            score=score,
            decision_band=band,
            blocking=False,
            reason_codes=submit_only_reasons or ["decision_band_not_submit_candidate"],
            decision_evidence=decision_evidence,
        )

    if band in {"research_only", "abandon_or_rebuild"}:
        action = "optimize" if score >= 50 else "archive"
        return _decision(
            action,
            "needs_optimization" if action == "optimize" else "archived",
            "scorecard keeps the candidate out of official validation until its local evidence improves",
            score=score,
            decision_band=band,
            blocking=(action == "archive"),
            reason_codes=submit_only_reasons or ["decision_band_not_submit_candidate"],
            decision_evidence=decision_evidence,
        )

    if not official_evidence and _only_official_evidence_missing(row) and score >= float(min_official_score):
        return _decision(
            "official_validation_queue",
            "queued_for_simulation",
            "local gate is valid and the remaining blocker is missing official evidence",
            score=score,
            decision_band=band,
            blocking=False,
            reason_codes=submit_only_reasons or ["missing_official_evidence"],
            decision_evidence=decision_evidence,
        )

    return _decision(
        "retain",
        "candidate_pool_retained",
        "candidate remains in the ranked local pool while more evidence accumulates",
        score=score,
        decision_band=band,
        blocking=False,
        reason_codes=submit_only_reasons,
        decision_evidence=decision_evidence,
    )


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


def candidate_submission_ready(row: dict[str, Any]) -> bool:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return bool(
        str(row.get("lifecycle_status") or "").lower() == "submission_ready"
        or diagnosis.get("submission_ready") is True
        or gate.get("submission_ready") is True
    )


def candidate_score(row: dict[str, Any]) -> float:
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    try:
        value = float(scorecard.get("total_score", row.get("score")) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return value if value == value else 0.0


def candidate_has_official_evidence(row: dict[str, Any]) -> bool:
    return bool(
        str(row.get("official_alpha_id") or "").strip()
        or str(row.get("simulation_id") or "").strip()
        or (isinstance(row.get("official_metrics"), dict) and bool(row.get("official_metrics")))
    )


def candidate_submit_only_reasons(row: dict[str, Any]) -> list[str]:
    return sorted({
        code
        for code, category in _blocking_pairs(row)
        if _is_submit_only_quality_reason(code, category)
    } | {
        reason
        for reason in _gate_failed_reasons(row)
        if _is_submit_only_quality_reason(reason, "")
    })


def candidate_hard_blocking_reasons(row: dict[str, Any]) -> list[str]:
    reasons: set[str] = set()
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        reasons.add("local_quality_failed")
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    if local_backtest.get("pass_local") is False:
        reasons.add("local_backtest_failed")
    for code, category in _blocking_pairs(row):
        if not _is_submit_only_quality_reason(code, category):
            reasons.add(code)
    for reason in _gate_failed_reasons(row):
        if not _is_submit_only_quality_reason(reason, ""):
            reasons.add(reason)
    return sorted(reason for reason in reasons if reason)


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


def _decision(
    action: str,
    next_state: str,
    reason: str,
    *,
    score: float,
    decision_band: str,
    blocking: bool,
    reason_codes: list[str],
    decision_evidence: dict[str, Any] | None = None,
    source: str = "scorecard_quality_gate",
) -> dict[str, Any]:
    payload = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "action": action,
        "next_state": next_state,
        "reason": reason,
        "blocking": bool(blocking),
        "score": round(float(score or 0.0), 4),
        "decision_band": decision_band,
        "reason_codes": sorted({str(code) for code in reason_codes if str(code or "").strip()}),
        "source": source,
        "official_api_called": False,
        "submit_allowed": False,
    }
    if decision_evidence and (
        decision_evidence.get("hard_blocking_reasons")
        or decision_evidence.get("scientific_audit_policy_reasons")
        or decision_evidence.get("lifecycle_risk")
        or decision_evidence.get("lifecycle_replay")
    ):
        payload["decision_evidence"] = decision_evidence
    return payload


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


def _lifecycle_text(value: Any, *, default: str = "", max_length: int = 160) -> str:
    return redact_text(value if value is not None else default, max_length=max_length).strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _status(row: dict[str, Any]) -> str:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return str(row.get("lifecycle_status") or diagnosis.get("status") or gate.get("status") or "").strip().lower()


def _decision_band(row: dict[str, Any]) -> str:
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    return str(scorecard.get("decision_band") or row.get("decision_band") or "").strip()


def _blocking_pairs(row: dict[str, Any]) -> list[tuple[str, str]]:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    pairs: set[tuple[str, str]] = set()
    primary = diagnosis.get("primary_reason") if isinstance(diagnosis.get("primary_reason"), dict) else {}
    code = str(primary.get("code") or "").strip()
    if code:
        pairs.add((code, str(primary.get("category") or "").strip()))
    for reason in diagnosis.get("blocking_reasons") or []:
        text = str(reason or "").strip()
        if text:
            pairs.add((text, ""))
    reason_rows = diagnosis.get("reasons") if isinstance(diagnosis.get("reasons"), list) else []
    for item in reason_rows:
        if not isinstance(item, dict):
            continue
        if item.get("severity") and item.get("severity") != "blocking":
            continue
        code = str(item.get("code") or "").strip()
        if code:
            pairs.add((code, str(item.get("category") or "").strip()))
    return sorted(pairs)


def _gate_failed_reasons(row: dict[str, Any]) -> list[str]:
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return sorted({
        str(reason or "").strip()
        for reason in gate.get("failed_reasons") or []
        if str(reason or "").strip()
    })


def _has_human_confirmation_blocker(row: dict[str, Any]) -> bool:
    reasons = set(candidate_submit_only_reasons(row))
    return bool(reasons & {"needs_human_confirmation", "human_confirmation_required", "manual_confirmation_required"})


def _only_official_evidence_missing(row: dict[str, Any]) -> bool:
    hard = candidate_hard_blocking_reasons(row)
    if hard:
        return False
    submit_only = set(candidate_submit_only_reasons(row))
    return bool(submit_only & {"missing_official_alpha_id", "missing_official_metrics", "missing_official_metric_fields"})

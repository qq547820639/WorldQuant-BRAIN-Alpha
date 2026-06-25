"""Core production decision logic for candidate-pool rows."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_candidates.lifecycle_risk import (
    existing_lifecycle_risk,
    lifecycle_history_requires_rework,
    lifecycle_history_should_archive,
)

from ._evidence import candidate_decision_evidence
from ._helpers import (
    _ARCHIVE_STATUS_TOKENS,
    _decision_band,
    _has_human_confirmation_blocker,
    _only_official_evidence_missing,
    _status,
    candidate_hard_blocking_reasons,
    candidate_has_official_evidence,
    candidate_score,
    candidate_submission_ready,
    candidate_submit_only_reasons,
)

DEFAULT_OFFICIAL_SIMULATION_SCORE = 70.0
DECISION_SCHEMA_VERSION = "candidate-production-decision-v1"


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

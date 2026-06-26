"""Production gap analysis helpers."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.live_submit_readiness_assessment import (
    scientific_audit_gap_messages as _scientific_audit_gap_messages,
)

from ._candidates import _blocking_reason_counts, _merge_chain_summaries


def _candidate_evidence_incomplete(ledger_audits: list[dict[str, Any]]) -> bool:
    for audit in ledger_audits:
        for finding in audit.get("candidate_evidence_findings") or []:
            if (finding or {}).get("code") == "candidate_pool_truncated":
                return True
    return False


def _production_gap_summary(
    *,
    primary_audit: dict[str, Any],
    latest_blocking_reason_counts: dict[str, int],
    family_blocking_reason_counts: dict[str, int],
    primary_chain_summary: dict[str, Any],
    family_chain_summary: dict[str, Any],
    candidate_evidence_incomplete: bool = False,
    current_ready_to_submit: bool | None = None,
) -> dict[str, Any]:
    gaps: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        if not any(item["code"] == code for item in gaps):
            gaps.append({"code": code, "message": message})

    if primary_audit.get("ready_to_submit") and current_ready_to_submit is not False:
        return {
            "gap_count": 0,
            "gaps": [],
            "latest_blocking_reason_counts": latest_blocking_reason_counts,
            "job_family_blocking_reason_counts": family_blocking_reason_counts,
            "primary_chain_summary": dict(primary_chain_summary),
            "job_family_chain_summary": dict(family_chain_summary),
            "ledger_ready_to_submit": bool(primary_audit.get("ledger_ready_to_submit")),
        }

    if primary_chain_summary.get("official_validation_passed") and not primary_chain_summary.get("officially_simulated"):
        add(
            "official_validation_without_simulation",
            "latest production ledger has official validation evidence but no official simulation metrics",
        )
    if family_chain_summary.get("local_only_jobs"):
        add(
            "local_only_candidate_jobs",
            "related job ledgers include local-only candidate generation jobs that cannot prove submit readiness",
        )
    if candidate_evidence_incomplete:
        add(
            "candidate_evidence_incomplete",
            "candidate ledger evidence is incomplete; rerun with full submission evidence before submit",
        )
    if latest_blocking_reason_counts.get("high_turnover_generation_risk"):
        add("latest_candidate_generation_risk", "latest candidate has a known high-turnover generation pattern")
    if latest_blocking_reason_counts.get("local_backtest_failed"):
        add("latest_candidate_local_backtest_failed", "latest candidate failed local backtest constraints")
    if latest_blocking_reason_counts.get("lifecycle_history_blocked"):
        add("latest_candidate_lifecycle_history_blocked", "latest candidate has local lifecycle history that requires archive before submit")
    if latest_blocking_reason_counts.get("lifecycle_history_failed"):
        add("latest_candidate_lifecycle_history_failed", "latest candidate has local lifecycle history that requires rework before submit")
    if latest_blocking_reason_counts.get("production_decision_lifecycle_blocked"):
        add("latest_candidate_lifecycle_decision_blocked", "latest candidate production decision contains lifecycle-history blocking evidence")
    if latest_blocking_reason_counts.get("production_decision_blocked"):
        add("latest_candidate_production_decision_blocked", "latest candidate production decision is blocked")
    for reason, message in _scientific_audit_gap_messages().items():
        if latest_blocking_reason_counts.get(reason):
            add(f"latest_candidate_{reason}", f"latest candidate {message}")
    if latest_blocking_reason_counts.get("high_cloud_similarity"):
        add("latest_candidate_high_cloud_similarity", "latest candidate is too similar to an existing cloud alpha")
    if family_blocking_reason_counts.get("missing_official_alpha_id"):
        add("candidate_family_missing_official_alpha_id", "candidate family lacks official alpha identifiers")
    if family_blocking_reason_counts.get("missing_official_metrics"):
        add("candidate_family_missing_official_metrics", "candidate family lacks official simulation metrics")
    if family_blocking_reason_counts.get("lifecycle_history_blocked"):
        add("candidate_family_lifecycle_history_blocked", "candidate family contains local lifecycle history that requires archive before submit")
    if family_blocking_reason_counts.get("lifecycle_history_failed"):
        add("candidate_family_lifecycle_history_failed", "candidate family contains local lifecycle history that requires rework before submit")
    for reason, message in _scientific_audit_gap_messages().items():
        if family_blocking_reason_counts.get(reason):
            add(f"candidate_family_{reason}", f"candidate family {message}")
    if family_blocking_reason_counts.get("missing_cloud_similarity"):
        add("candidate_family_missing_cloud_similarity", "candidate family has candidates without cloud similarity evidence")
    if family_blocking_reason_counts.get("decision_band_not_submit_candidate"):
        add("candidate_family_not_submit_band", "candidate family has no candidate in submit_candidate decision band")

    return {
        "gap_count": len(gaps),
        "gaps": gaps,
        "latest_blocking_reason_counts": latest_blocking_reason_counts,
        "job_family_blocking_reason_counts": family_blocking_reason_counts,
        "primary_chain_summary": dict(primary_chain_summary),
        "job_family_chain_summary": dict(family_chain_summary),
        "ledger_ready_to_submit": bool(primary_audit.get("ledger_ready_to_submit")),
    }


def _production_gap_findings(
    primary_audit: dict[str, Any],
    ledger_audits: list[dict[str, Any]],
    family_candidates: list[dict[str, Any]],
) -> list[dict[str, str]]:
    primary_chain_summary = dict(primary_audit.get("chain_summary") or {})
    family_chain_summary = _merge_chain_summaries(ledger_audits)
    latest_counts = _blocking_reason_counts(primary_audit.get("latest_candidates") or [])
    family_counts = _blocking_reason_counts(family_candidates)
    return [
        {
            "code": gap["code"],
            "message": gap["message"],
        }
        for gap in _production_gap_summary(
            primary_audit=primary_audit,
            latest_blocking_reason_counts=latest_counts,
            family_blocking_reason_counts=family_counts,
            primary_chain_summary=primary_chain_summary,
            family_chain_summary=family_chain_summary,
            candidate_evidence_incomplete=_candidate_evidence_incomplete([primary_audit]),
        )["gaps"]
    ]

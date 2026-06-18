"""Queue planning for decoupled Web candidate production and validation."""

from __future__ import annotations

from collections import Counter
from typing import Any

from brain_alpha_ops.web_candidates.decisions import (
    candidate_decision_action,
    candidate_production_decision,
    candidate_score,
)

DEFAULT_VALIDATOR_BATCH_SIZE = 3
WORKFLOW_SCHEMA_VERSION = "candidate-pool-workflow-v1"
READINESS_EVIDENCE_SCHEMA_VERSION = "candidate-workflow-readiness-evidence-v1"

QUEUE_TO_BLOCKER_MAPPING = {
    "producer": [
        "pool_deficit",
        "no_submit_band_candidate",
    ],
    "validator": [
        "missing_official_evidence",
        "missing_official_alpha_id",
        "missing_official_metrics",
        "missing_official_metric_fields",
        "official_pass_fail_not_pass",
        "official_checks_pending",
    ],
    "rework": [
        "decision_band_not_submit_candidate",
        "local_backtest_failed",
        "unsupported_local_backtest_fields",
        "unsupported_local_backtest_operators",
        "lifecycle_history_failed",
    ],
    "review": [
        "needs_human_confirmation",
        "human_confirmation_required",
        "manual_confirmation_required",
        "manual_submit_review_required",
    ],
    "archive": [
        "local_quality_failed",
        "high_cloud_similarity",
        "hard_gate_blocked",
        "lifecycle_history_blocked",
        "scientific_audit_test_feedback_used",
    ],
}


def candidate_workflow_plan(
    rows: list[dict[str, Any]],
    *,
    target_size: int,
    main_pool: list[dict[str, Any]] | None = None,
    validator_batch_size: int = DEFAULT_VALIDATOR_BATCH_SIZE,
) -> dict[str, Any]:
    """Build a queue snapshot that separates producer, validator, and rework work.

    The plan is read-only. It tells the Web UI and background jobs which queue
    should move next, without calling official APIs or changing submit policy.
    """

    target = max(1, int(target_size or 1))
    batch_size = max(0, int(validator_batch_size or 0))
    main_pool = list(main_pool or [])
    active_ids = _candidate_ids(main_pool)
    active_count = len(main_pool)
    deficit = max(0, target - active_count)

    validator_candidates = _ranked_candidates(
        rows,
        action="official_validation_queue",
        exclude_ids=set(),
    )
    rework_candidates = _ranked_candidates(
        rows,
        action="optimize",
        exclude_ids=set(),
    )
    archive_candidates = _ranked_candidates(
        rows,
        action="archive",
        exclude_ids=set(),
    )
    review_candidates = _ranked_candidates(
        rows,
        action="needs_human_confirmation",
        exclude_ids=set(),
    ) + _ranked_candidates(
        rows,
        action="submit_review_blocked",
        exclude_ids=set(),
    )

    validator_batch = validator_candidates[:batch_size] if batch_size else []
    next_action = _next_action(
        deficit=deficit,
        validator_count=len(validator_batch),
        rework_count=len(rework_candidates),
        review_count=len(review_candidates),
    )
    readiness_evidence = _readiness_evidence(
        rows,
        target=target,
        active_count=active_count,
        deficit=deficit,
        next_action=next_action,
        validator_candidates=validator_candidates,
        validator_batch=validator_batch,
        rework_candidates=rework_candidates,
        review_candidates=review_candidates,
        archive_candidates=archive_candidates,
    )
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "official_api_called": False,
        "submit_allowed": False,
        "target_pool_size": target,
        "next_action": next_action,
        "readiness_evidence": readiness_evidence,
        "execution_readiness": readiness_evidence,
        "producer": {
            "queue": "candidate_producer",
            "active_pool_count": active_count,
            "active_candidate_ids": active_ids,
            "deficit": deficit,
            "replenish_needed": deficit > 0,
            "can_continue_while_validator_runs": True,
        },
        "validator": {
            "queue": "official_validator",
            "candidate_count": len(validator_candidates),
            "candidate_ids": _candidate_ids(validator_candidates),
            "next_batch_size": len(validator_batch),
            "next_candidate_ids": _candidate_ids(validator_batch),
            "batch_limit": batch_size,
            "resource": "official_simulation_slots",
        },
        "rework": {
            "queue": "local_optimizer",
            "candidate_count": len(rework_candidates),
            "candidate_ids": _candidate_ids(rework_candidates),
        },
        "review": {
            "queue": "human_review",
            "candidate_count": len(review_candidates),
            "candidate_ids": _candidate_ids(review_candidates),
        },
        "archive": {
            "queue": "archive",
            "candidate_count": len(archive_candidates),
            "candidate_ids": _candidate_ids(archive_candidates),
        },
    }


def _ranked_candidates(
    rows: list[dict[str, Any]],
    *,
    action: str,
    exclude_ids: set[str],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or candidate_decision_action(row) != action:
            continue
        key = _candidate_key(row)
        if not key or key in seen or key in exclude_ids:
            continue
        seen.add(key)
        selected.append(row)
    return sorted(selected, key=candidate_score, reverse=True)


def _candidate_ids(rows: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for row in rows:
        value = _candidate_key(row)
        if value and value not in ids:
            ids.append(value)
    return ids


def _candidate_key(row: dict[str, Any]) -> str:
    for field in ("alpha_id", "official_alpha_id", "simulation_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    expression = " ".join(str(row.get("expression") or "").strip().lower().split())
    return expression


def _readiness_evidence(
    rows: list[dict[str, Any]],
    *,
    target: int,
    active_count: int,
    deficit: int,
    next_action: str,
    validator_candidates: list[dict[str, Any]],
    validator_batch: list[dict[str, Any]],
    rework_candidates: list[dict[str, Any]],
    review_candidates: list[dict[str, Any]],
    archive_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    execution_gap_counts = _execution_gap_counts(rows, deficit=deficit)
    action_counts = _decision_action_counts(rows)
    return {
        "schema_version": READINESS_EVIDENCE_SCHEMA_VERSION,
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "ready_to_submit": False,
        "stop_rule_required": True,
        "authoritative_stop_rule": "scripts/check_live_submit_readiness.py",
        "candidate_count": len([row for row in rows if isinstance(row, dict)]),
        "target_pool_size": target,
        "active_pool_count": active_count,
        "active_pool_deficit": deficit,
        "next_safe_action": next_action,
        "decision_action_counts": action_counts,
        "blocker_counts": _reason_counts(rows),
        "execution_gap_counts": execution_gap_counts,
        "queue_to_blocker_mapping": QUEUE_TO_BLOCKER_MAPPING,
        "queue_evidence": {
            "producer": {
                "queue": "candidate_producer",
                "candidate_count": deficit,
                "candidate_ids": [],
                "blocker_counts": execution_gap_counts,
                "closes_blockers": QUEUE_TO_BLOCKER_MAPPING["producer"],
            },
            "validator": _queue_readiness_evidence(
                "official_validator",
                validator_candidates,
                closes_blockers=QUEUE_TO_BLOCKER_MAPPING["validator"],
                next_candidates=validator_batch,
            ),
            "rework": _queue_readiness_evidence(
                "local_optimizer",
                rework_candidates,
                closes_blockers=QUEUE_TO_BLOCKER_MAPPING["rework"],
            ),
            "review": _queue_readiness_evidence(
                "human_review",
                review_candidates,
                closes_blockers=QUEUE_TO_BLOCKER_MAPPING["review"],
            ),
            "archive": _queue_readiness_evidence(
                "archive",
                archive_candidates,
                closes_blockers=QUEUE_TO_BLOCKER_MAPPING["archive"],
            ),
        },
    }


def _queue_readiness_evidence(
    queue: str,
    candidates: list[dict[str, Any]],
    *,
    closes_blockers: list[str],
    next_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence = {
        "queue": queue,
        "candidate_count": len(candidates),
        "candidate_ids": _candidate_ids(candidates),
        "blocker_counts": _reason_counts(candidates),
        "closes_blockers": closes_blockers,
    }
    if next_candidates is not None:
        evidence["next_candidate_ids"] = _candidate_ids(next_candidates)
    return evidence


def _reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for reason in _row_reason_codes(row):
            counts[reason] += 1
    return dict(sorted(counts.items()))


def _row_reason_codes(row: dict[str, Any]) -> list[str]:
    decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
    if not decision:
        decision = candidate_production_decision(row)
    return sorted({
        str(reason or "").strip()
        for reason in decision.get("reason_codes") or []
        if str(reason or "").strip()
    })


def _decision_action_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in rows:
        if isinstance(row, dict):
            counts[candidate_decision_action(row)] += 1
    return dict(sorted(counts.items()))


def _execution_gap_counts(rows: list[dict[str, Any]], *, deficit: int) -> dict[str, int]:
    gaps: dict[str, int] = {}
    if deficit > 0:
        gaps["pool_deficit"] = deficit
    if not any(_decision_band(row) == "submit_candidate" for row in rows if isinstance(row, dict)):
        gaps["no_submit_band_candidate"] = 1
    return gaps


def _decision_band(row: dict[str, Any]) -> str:
    scorecard = row.get("scorecard") if isinstance(row.get("scorecard"), dict) else {}
    return str(scorecard.get("decision_band") or row.get("decision_band") or "").strip()


def _next_action(*, deficit: int, validator_count: int, rework_count: int, review_count: int) -> str:
    if validator_count > 0:
        return "run_official_validator"
    if deficit > 0 and rework_count > 0:
        return "optimize_then_replenish"
    if deficit > 0:
        return "replenish_candidate_pool"
    if rework_count > 0:
        return "optimize_rework_queue"
    if review_count > 0:
        return "human_review_required"
    return "monitor_pool"

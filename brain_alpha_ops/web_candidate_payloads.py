"""Shared candidate payload helpers for Web route surfaces."""

from __future__ import annotations

from typing import Any

from brain_alpha_ops.web_backtest_slots import is_submit_only_quality_reason
from brain_alpha_ops.web_candidate_audit import scientific_audit_summary
from brain_alpha_ops.web_candidate_optimization_explainability import optimization_explanation_summary
from brain_alpha_ops.web_candidate_decisions import (
    annotate_candidate_decision,
    candidate_decision_action,
    candidate_hard_blocking_reasons,
    candidate_score as production_candidate_score,
    candidate_submission_ready as production_candidate_submission_ready,
    decision_action_counts,
)
from brain_alpha_ops.web_candidate_lifecycle_risk import (
    enrich_candidates_with_lifecycle_risk,
    lifecycle_history_requires_rework,
    lifecycle_history_should_archive,
)
from brain_alpha_ops.web_candidate_workflow import candidate_workflow_plan

DEFAULT_MAIN_POOL_SIZE = 10


def candidate_payload(
    rows: list[dict[str, Any]],
    *,
    source: str,
    total: int | None = None,
    path: str = "",
    summary_only: bool = False,
    partial: bool = False,
    warning: str = "",
    target_pool_size: int = DEFAULT_MAIN_POOL_SIZE,
    lifecycle_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    total_count = len(rows) if total is None else int(total)
    annotated_rows = annotate_candidate_rows(rows, lifecycle_rows=lifecycle_rows)
    summary = candidate_summary(annotated_rows, total=total_count)
    pool_summary = candidate_pool_summary(annotated_rows, target_size=target_pool_size)
    main_pool = [] if summary_only else candidate_main_pool(annotated_rows, target_size=target_pool_size)
    workflow_plan = candidate_workflow_plan(
        annotated_rows,
        target_size=target_pool_size,
        main_pool=main_pool,
    )
    returned_rows = [] if summary_only else annotated_rows
    return {
        "ok": True,
        "source": source,
        "path": path,
        "summary_only": summary_only,
        "candidates": returned_rows,
        "items": returned_rows,
        "count": len(returned_rows),
        "returned_count": len(returned_rows),
        "total_count": total_count,
        "total": total_count,
        "main_pool_candidates": main_pool,
        "pool_summary": pool_summary,
        "scientific_audit": scientific_audit_summary(annotated_rows),
        "optimization_explanations": optimization_explanation_summary(annotated_rows),
        "workflow_plan": workflow_plan,
        "candidate_workflow": workflow_plan,
        "partial": partial,
        "warning": warning,
        **summary,
    }


def candidate_summary(rows: list[dict[str, Any]], *, total: int | None = None) -> dict[str, Any]:
    return candidate_summary_from_iter(rows, total=total)


def candidate_summary_from_iter(rows: Any, *, total: int | None = None) -> dict[str, Any]:
    counted = 0
    ready_count = 0
    blocked_count = 0
    running_backtest_count = 0
    pending_backtest_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        counted += 1
        if candidate_submission_ready(row):
            ready_count += 1
        if candidate_blocked(row):
            blocked_count += 1
        status = candidate_status(row)
        if status in {"running_backtest", "running"}:
            running_backtest_count += 1
        if status == "pending_backtest":
            pending_backtest_count += 1
    return {
        "candidate_count": int(total if total is not None else counted),
        "ready_count": ready_count,
        "blocked_count": blocked_count,
        "running_backtest_count": running_backtest_count,
        "pending_backtest_count": pending_backtest_count,
    }


def candidate_submission_ready(row: dict[str, Any]) -> bool:
    return production_candidate_submission_ready(row)


def candidate_blocked(row: dict[str, Any]) -> bool:
    status = candidate_status(row)
    hard_status = any(token in status for token in (
        "simulation_failed",
        "official_standard_rejected",
        "local_prefilter_rejected",
        "local_standard_rejected",
        "candidate_pool_pruned",
        "high_cloud_similarity",
        "rejected",
        "failed",
    ))
    if hard_status:
        return True
    if "blocked" in status and not candidate_has_submit_only_blockers(row):
        return True
    if "blocked" in status and candidate_hard_blocked(row):
        return True
    return candidate_hard_blocked(row)


def candidate_hard_blocked(row: dict[str, Any]) -> bool:
    return bool(candidate_hard_blocking_reasons(row))


def candidate_status(row: dict[str, Any]) -> str:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return str(row.get("lifecycle_status") or diagnosis.get("status") or gate.get("status") or "").lower()


def candidate_main_pool(rows: list[dict[str, Any]], *, target_size: int = DEFAULT_MAIN_POOL_SIZE) -> list[dict[str, Any]]:
    target = max(1, int(target_size or DEFAULT_MAIN_POOL_SIZE))
    best_by_expression: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not candidate_pool_eligible(row):
            continue
        key = candidate_expression_key(row)
        existing = best_by_expression.get(key)
        if existing is None or candidate_score(row) > candidate_score(existing):
            best_by_expression[key] = row
    return sorted(best_by_expression.values(), key=candidate_score, reverse=True)[:target]


def candidate_pool_summary(rows: list[dict[str, Any]], *, target_size: int = DEFAULT_MAIN_POOL_SIZE) -> dict[str, Any]:
    target = max(1, int(target_size or DEFAULT_MAIN_POOL_SIZE))
    eligible = [row for row in rows if isinstance(row, dict) and candidate_pool_eligible(row)]
    main_pool = candidate_main_pool(rows, target_size=target)
    blocked = sum(1 for row in rows if isinstance(row, dict) and not candidate_pool_eligible(row))
    action_counts = decision_action_counts([row for row in rows if isinstance(row, dict)])
    lifecycle_rework = sum(1 for row in rows if isinstance(row, dict) and lifecycle_history_requires_rework(row))
    return {
        "schema_version": "candidate-pool-summary-v1",
        "target_pool_size": target,
        "main_pool_count": len(main_pool),
        "promotable_count": len(eligible),
        "blocked_or_archived_count": blocked,
        "lifecycle_rework_count": lifecycle_rework,
        "remaining_deficit": max(0, target - len(main_pool)),
        "decision_action_counts": action_counts,
        "official_validation_queue_count": action_counts.get("official_validation_queue", 0),
        "optimization_count": action_counts.get("optimize", 0),
        "human_confirmation_count": action_counts.get("needs_human_confirmation", 0),
        "submit_review_blocked_count": action_counts.get("submit_review_blocked", 0),
        "archived_count": action_counts.get("archive", 0),
    }


def candidate_pool_eligible(row: dict[str, Any]) -> bool:
    status = candidate_status(row)
    if candidate_decision_action(row) == "archive":
        return False
    if lifecycle_history_requires_rework(row) or lifecycle_history_should_archive(row):
        return False
    if any(token in status for token in (
        "submitted",
        "submission_ready",
        "simulation_failed",
        "official_standard_rejected",
        "local_prefilter_rejected",
        "local_standard_rejected",
        "candidate_pool_pruned",
        "rejected",
        "failed",
        "high_cloud_similarity",
    )):
        return False
    if "blocked" in status and not candidate_has_submit_only_blockers(row):
        return False
    return not candidate_hard_blocked(row)


def candidate_score(row: dict[str, Any]) -> float:
    return production_candidate_score(row)


def candidate_expression_key(row: dict[str, Any]) -> str:
    expression = str(row.get("expression") or row.get("alpha_id") or "").strip().lower()
    return " ".join(expression.split())


def local_quality_failed(row: dict[str, Any]) -> bool:
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    if local_quality.get("passed") is False:
        return True
    local_backtest = local_quality.get("local_backtest") if isinstance(local_quality.get("local_backtest"), dict) else {}
    return local_backtest.get("pass_local") is False


def candidate_blocking_codes(row: dict[str, Any]) -> list[str]:
    return sorted({code for code, _category in candidate_blocking_pairs(row)})


def candidate_blocking_pairs(row: dict[str, Any]) -> list[tuple[str, str]]:
    diagnosis = row.get("quality_diagnosis") if isinstance(row.get("quality_diagnosis"), dict) else {}
    pairs: set[tuple[str, str]] = set()
    primary = diagnosis.get("primary_reason") if isinstance(diagnosis.get("primary_reason"), dict) else {}
    primary_code = str(primary.get("code") or "").strip()
    if primary_code:
        pairs.add((primary_code, str(primary.get("category") or "").strip()))
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
    local_quality = row.get("local_quality") if isinstance(row.get("local_quality"), dict) else {}
    for reason in local_quality.get("reasons") or []:
        text = str(reason or "").split(":", 1)[0].strip()
        if text:
            pairs.add((text, "local_quality_failed"))
    return sorted(pairs)


def candidate_gate_failed_reasons(row: dict[str, Any]) -> list[str]:
    gate = row.get("gate") if isinstance(row.get("gate"), dict) else {}
    return sorted({
        str(reason or "").strip()
        for reason in gate.get("failed_reasons") or []
        if str(reason or "").strip()
    })


def candidate_has_submit_only_blockers(row: dict[str, Any]) -> bool:
    return bool(
        any(is_submit_only_quality_reason(code, category) for code, category in candidate_blocking_pairs(row))
        or any(is_submit_only_quality_reason(code, "") for code in candidate_gate_failed_reasons(row))
    )


def annotate_candidate_rows(
    rows: list[dict[str, Any]],
    *,
    lifecycle_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    candidate_rows = [row for row in rows if isinstance(row, dict)]
    enriched = enrich_candidates_with_lifecycle_risk(candidate_rows, lifecycle_rows)
    return [annotate_candidate_decision(row) if isinstance(row, dict) else row for row in enriched]


def has_candidate_like_rows(rows: list[Any]) -> bool:
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else row
        if candidate.get("alpha_id") or candidate.get("official_alpha_id") or candidate.get("expression"):
            return True
    return False


def candidate_result_total(result: dict[str, Any], fallback: int) -> int:
    for key in ("candidates_count", "candidate_count", "count", "total", "total_count"):
        value = result.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return max(number, fallback)
    return fallback


def compact_job_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload
    compact_result = dict(result)
    for key in ("alphas", "cloud_alphas"):
        rows = compact_result.get(key)
        if isinstance(rows, list):
            compact_result[key + "_count"] = len(rows)
            compact_result.pop(key, None)
    return {**payload, "result": compact_result}

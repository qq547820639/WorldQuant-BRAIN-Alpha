"""Batch submission orchestration for the local web console."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.submission_readiness import live_submit_readiness_hard_gate

RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ObservabilityPreflight = Callable[[str], dict[str, Any]]
SubmitCandidate = Callable[[dict[str, Any]], dict[str, Any]]
CandidateFromPayload = Callable[[dict[str, Any]], dict[str, Any]]
SubmissionPreflight = Callable[[dict[str, Any], RunConfig], dict[str, Any]]
SubmitReadinessHardGate = Callable[[dict[str, Any], RunConfig], dict[str, Any]]
WebError = Callable[[Exception, str], dict[str, Any]]
PayloadTruthy = Callable[[object], bool]
ProgressCallback = Callable[[dict[str, Any]], None]


def submit_batch_payload(
    payload: dict[str, Any],
    *,
    run_config_from_payload: RunConfigFromPayload,
    observability_submission_preflight: ObservabilityPreflight,
    submit_candidate: SubmitCandidate,
    candidate_from_payload: CandidateFromPayload,
    web_error: WebError,
    payload_truthy: PayloadTruthy,
    submission_preflight_advisory: SubmissionPreflight | None = None,
    submit_readiness_hard_gate: SubmitReadinessHardGate = live_submit_readiness_hard_gate,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    alpha_ids = [str(item) for item in payload.get("alpha_ids", []) if str(item)]
    raw_candidates = payload.get("submit_candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    by_id = {str(candidate.get("alpha_id", "")): candidate for candidate in candidates if isinstance(candidate, dict)}
    run_config = run_config_from_payload(payload)
    if not payload_truthy(payload.get("confirm_submit")):
        return {
            "ok": False,
            "schema_version": "submission_batch_result.v2",
            "status": "BLOCKED",
            "error_code": "SUBMIT_CONFIRMATION_REQUIRED",
            "error": "Production batch submit requires explicit confirm_submit=true.",
            "error_category": "confirmation",
            "action": "Complete readiness review first; real batch submit is outside the ordinary Web flow and requires separate approval.",
            "state_navigation": {
                "schema_version": "abnormal_state_navigation.v1",
                "state": "blocked",
                "reason_code": "SUBMIT_CONFIRMATION_REQUIRED",
                "title": "需要单独批量提交审批",
                "summary": "普通 Web 就绪复核流程不会执行批量真实提交；后端已在调用官方提交 API 前阻断。",
                "target_view": "submit",
                "primary_action": "先完成全部候选的提交前就绪复核；如需真实批量提交，走单独审批路径。",
            },
        }
    observability_preflight = observability_submission_preflight(run_config.ops.storage_dir)
    if observability_preflight.get("requires_confirmation") and not payload_truthy(payload.get("confirm_observability_risk")):
        risk_explanation = observability_preflight.get("risk_explanation") if isinstance(observability_preflight.get("risk_explanation"), dict) else {}
        return {
            "ok": False,
            "schema_version": "submission_batch_result.v2",
            "status": "BLOCKED",
            "error_code": "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED",
            "error": "Observability diagnostics recommend pausing submission until blocking flags are acknowledged.",
            "observability_preflight": observability_preflight,
            "risk_explanation": risk_explanation,
            "risk_explanations": [risk_explanation] if risk_explanation else [],
            "state_navigation": observability_preflight.get("state_navigation") if isinstance(observability_preflight.get("state_navigation"), dict) else {},
        }
    if submission_preflight_advisory is not None:
        blocked = _candidate_preflight_blocks(
            alpha_ids,
            by_id,
            run_config,
            candidate_from_payload=candidate_from_payload,
            submission_preflight_advisory=submission_preflight_advisory,
            progress_callback=progress_callback,
        )
        if blocked:
            return _batch_preflight_block_payload(blocked)
    readiness_blocked = _candidate_readiness_blocks(
        alpha_ids,
        by_id,
        run_config,
        candidate_from_payload=candidate_from_payload,
        submit_readiness_hard_gate=submit_readiness_hard_gate,
        progress_callback=progress_callback,
    )
    if readiness_blocked:
        return _batch_preflight_block_payload(readiness_blocked)
    results = []
    submitted_set: set[str] = set()
    total = len(alpha_ids)
    if progress_callback:
        progress_callback({"phase": "submitting", "message": f"Preparing batch submission for {total} alpha(s).", "submitted": 0, "failed": 0, "total": total, "percent": 0 if total else 100})
    for index, alpha_id in enumerate(alpha_ids, start=1):
        if progress_callback:
            progress_callback({"phase": "submitting", "message": f"Submitting alpha {index}/{total}: {alpha_id}", "current_alpha_id": alpha_id, "submitted": len(submitted_set), "failed": sum(1 for item in results if not item.get("ok")), "done": index - 1, "total": total})
        if alpha_id in submitted_set:
            results.append({"alpha_id": alpha_id, "ok": True, "submission": {"status": "ALREADY_SUBMITTED", "message": "Already submitted in this batch"}})
            continue
        item_payload = dict(payload)
        item_payload["alpha_id"] = alpha_id
        item_payload["candidate"] = by_id.get(alpha_id) or candidate_from_payload({"job_id": payload.get("job_id", ""), "alpha_id": alpha_id})
        try:
            result = submit_candidate(item_payload)
        except Exception as exc:
            result = web_error(exc, "SUBMIT_BATCH_ERROR")
        if result.get("ok"):
            submitted_set.add(alpha_id)
        results.append({"alpha_id": alpha_id, **result})
        if progress_callback:
            progress_callback({"phase": "submitting", "message": f"Submitted {index}/{total}; accepted {len(submitted_set)}, failed {sum(1 for item in results if not item.get('ok'))}.", "current_alpha_id": alpha_id, "submitted": len(submitted_set), "failed": sum(1 for item in results if not item.get("ok")), "done": index, "total": total})
    return {
        "ok": True,
        "schema_version": "submission_batch_result.v2",
        "status": "COMPLETED" if all(item.get("ok") for item in results) else "PARTIAL_FAILED",
        "submitted": len(submitted_set),
        "failed": sum(1 for item in results if not item.get("ok")),
        "submitted_alpha_ids": sorted(submitted_set),
        "failed_alpha_ids": [item.get("alpha_id", "") for item in results if not item.get("ok") and item.get("alpha_id")],
        "state_counts": _state_counts(results),
        "results": results,
    }


def _candidate_preflight_blocks(
    alpha_ids: list[str],
    by_id: dict[str, dict[str, Any]],
    run_config: RunConfig,
    *,
    candidate_from_payload: CandidateFromPayload,
    submission_preflight_advisory: SubmissionPreflight,
    progress_callback: ProgressCallback | None,
) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    seen: set[str] = set()
    unique_alpha_ids = [alpha_id for alpha_id in alpha_ids if not (alpha_id in seen or seen.add(alpha_id))]
    total = len(unique_alpha_ids)
    if progress_callback:
        progress_callback(
            {
                "phase": "preflight",
                "message": f"Checking submit preflight for {total} alpha(s).",
                "submitted": 0,
                "failed": 0,
                "total": total,
                "percent": 0 if total else 100,
            }
        )
    for index, alpha_id in enumerate(unique_alpha_ids, start=1):
        candidate = by_id.get(alpha_id) or candidate_from_payload({"alpha_id": alpha_id})
        advisory = submission_preflight_advisory(candidate, run_config)
        if not advisory.get("ok"):
            blocked.append(_candidate_preflight_block(alpha_id, candidate, advisory))
        if progress_callback:
            progress_callback(
                {
                    "phase": "preflight",
                    "message": f"Checked submit preflight {index}/{total}: {alpha_id}",
                    "current_alpha_id": alpha_id,
                    "submitted": 0,
                    "failed": len(blocked),
                    "done": index,
                    "total": total,
                }
            )
    return blocked


def _candidate_readiness_blocks(
    alpha_ids: list[str],
    by_id: dict[str, dict[str, Any]],
    run_config: RunConfig,
    *,
    candidate_from_payload: CandidateFromPayload,
    submit_readiness_hard_gate: SubmitReadinessHardGate,
    progress_callback: ProgressCallback | None,
) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    seen: set[str] = set()
    unique_alpha_ids = [alpha_id for alpha_id in alpha_ids if not (alpha_id in seen or seen.add(alpha_id))]
    total = len(unique_alpha_ids)
    if progress_callback:
        progress_callback(
            {
                "phase": "readiness",
                "message": f"Checking live submit readiness for {total} alpha(s).",
                "submitted": 0,
                "failed": 0,
                "total": total,
                "percent": 0 if total else 100,
            }
        )
    for index, alpha_id in enumerate(unique_alpha_ids, start=1):
        candidate = by_id.get(alpha_id) or candidate_from_payload({"alpha_id": alpha_id})
        gate = submit_readiness_hard_gate(candidate, run_config)
        if not gate.get("ok"):
            blocked.append(_candidate_preflight_block(alpha_id, candidate, gate))
        if progress_callback:
            progress_callback(
                {
                    "phase": "readiness",
                    "message": f"Checked submit readiness {index}/{total}: {alpha_id}",
                    "current_alpha_id": alpha_id,
                    "submitted": 0,
                    "failed": len(blocked),
                    "done": index,
                    "total": total,
                }
            )
    return blocked


def _candidate_preflight_block(alpha_id: str, candidate: dict[str, Any], advisory: dict[str, Any]) -> dict[str, Any]:
    return {
        "alpha_id": alpha_id,
        "official_alpha_id": str(candidate.get("official_alpha_id") or advisory.get("official_alpha_id") or ""),
        "error_code": str(advisory.get("error_code") or "SUBMIT_PREFLIGHT_FAILED"),
        "error": str(advisory.get("error") or "Submit preflight failed."),
        "action": str(advisory.get("action") or ""),
    }


def _batch_preflight_block_payload(blocked: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": False,
        "schema_version": "submission_batch_result.v2",
        "status": "BLOCKED",
        "error_code": "SUBMIT_BATCH_PREFLIGHT_FAILED",
        "error": "One or more candidates failed submit preflight.",
        "error_category": "validation",
        "action": "Fix blocked candidates and rerun submit readiness before batch submission.",
        "blocked_candidates": blocked,
        "state_counts": _state_counts(blocked),
        "results": [
            {
                "alpha_id": item.get("alpha_id", ""),
                "official_alpha_id": item.get("official_alpha_id", ""),
                "ok": False,
                "status": "BLOCKED",
                "error_code": item.get("error_code", "SUBMIT_PREFLIGHT_FAILED"),
                "error": item.get("error", "Submit preflight failed."),
                "action": item.get("action", ""),
            }
            for item in blocked
        ],
        "state_navigation": {
            "schema_version": "abnormal_state_navigation.v1",
            "state": "blocked",
            "reason_code": "SUBMIT_BATCH_PREFLIGHT_FAILED",
            "title": "批量提交前置检查未通过",
            "summary": "至少一个候选缺少官方证据或未达到可提交状态，批量提交已在调用官方 API 前阻断。",
            "target_view": "submit",
            "primary_action": "回到候选管理，补齐官方回测和质量门禁后再提交。",
        },
    }


def _state_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        raw_submission = item.get("submission")
        submission = raw_submission if isinstance(raw_submission, dict) else {}
        key = str(item.get("status") or submission.get("status") or ("SUBMITTED" if item.get("ok") else item.get("error_code") or "FAILED"))
        counts[key] = counts.get(key, 0) + 1
    return counts

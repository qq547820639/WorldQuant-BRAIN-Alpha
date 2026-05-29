"""Batch submission orchestration for the local web console."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import RunConfig


RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ObservabilityPreflight = Callable[[str], dict[str, Any]]
SubmitCandidate = Callable[[dict[str, Any]], dict[str, Any]]
CandidateFromPayload = Callable[[dict[str, Any]], dict[str, Any]]
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
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    alpha_ids = [str(item) for item in payload.get("alpha_ids", []) if str(item)]
    raw_candidates = payload.get("submit_candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    by_id = {str(candidate.get("alpha_id", "")): candidate for candidate in candidates if isinstance(candidate, dict)}
    run_config = run_config_from_payload(payload)
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
    results = []
    submitted_set: set[str] = set()
    total = len(alpha_ids)
    if progress_callback:
        progress_callback({
            "phase": "submitting",
            "message": f"Preparing batch submission for {total} alpha(s).",
            "submitted": 0,
            "failed": 0,
            "total": total,
            "percent": 0 if total else 100,
        })
    for index, alpha_id in enumerate(alpha_ids, start=1):
        if progress_callback:
            progress_callback({
                "phase": "submitting",
                "message": f"Submitting alpha {index}/{total}: {alpha_id}",
                "current_alpha_id": alpha_id,
                "submitted": len(submitted_set),
                "failed": sum(1 for item in results if not item.get("ok")),
                "done": index - 1,
                "total": total,
            })
        if alpha_id in submitted_set:
            results.append({
                "alpha_id": alpha_id,
                "ok": True,
                "submission": {"status": "ALREADY_SUBMITTED", "message": "Already submitted in this batch"},
            })
            continue
        item_payload = dict(payload)
        item_payload["alpha_id"] = alpha_id
        item_payload["candidate"] = by_id.get(alpha_id) or candidate_from_payload(
            {"job_id": payload.get("job_id", ""), "alpha_id": alpha_id}
        )
        try:
            result = submit_candidate(item_payload)
        except Exception as exc:
            result = web_error(exc, "SUBMIT_BATCH_ERROR")
        if result.get("ok"):
            submitted_set.add(alpha_id)
        results.append({"alpha_id": alpha_id, **result})
        if progress_callback:
            progress_callback({
                "phase": "submitting",
                "message": f"Submitted {index}/{total}; accepted {len(submitted_set)}, failed {sum(1 for item in results if not item.get('ok'))}.",
                "current_alpha_id": alpha_id,
                "submitted": len(submitted_set),
                "failed": sum(1 for item in results if not item.get("ok")),
                "done": index,
                "total": total,
            })
    return {
        "ok": True,
        "schema_version": "submission_batch_result.v2",
        "status": "COMPLETED" if all(item.get("ok") for item in results) else "PARTIAL_FAILED",
        "submitted": sum(1 for item in results if item.get("ok")),
        "failed": sum(1 for item in results if not item.get("ok")),
        "submitted_alpha_ids": [item.get("alpha_id", "") for item in results if item.get("ok") and item.get("alpha_id")],
        "failed_alpha_ids": [item.get("alpha_id", "") for item in results if not item.get("ok") and item.get("alpha_id")],
        "state_counts": _state_counts(results),
        "results": results,
    }


def _state_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        raw_submission = item.get("submission")
        submission = raw_submission if isinstance(raw_submission, dict) else {}
        key = str(item.get("status") or submission.get("status") or ("SUBMITTED" if item.get("ok") else item.get("error_code") or "FAILED"))
        counts[key] = counts.get(key, 0) + 1
    return counts

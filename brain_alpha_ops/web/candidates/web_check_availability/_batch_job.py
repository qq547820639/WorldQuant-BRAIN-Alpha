"""Batch check background job service for the local web console."""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any

from brain_alpha_ops.web_candidates.check_evidence import (
    persist_candidate_check_evidence,
)

from ._batch_helpers import (
    ApiFromRunConfig,
    CheckAvailability,
    ErrorPayload,
    JobStoreLike,
    LedgerFactory,
    ObservabilityPreflight,
    PassedCandidates,
    PayloadTruthy,
    RefreshCloudContext,
    RepositoryFactory,
    RunConfigFromPayload,
    SafeErrorMessage,
    _store_is_cancelled,
    _timing_payload,
    _update_check_batch_cancelled,
)

logger = logging.getLogger(__name__)


def run_check_batch_job_service(
    job_id: str,
    payload: dict[str, Any],
    *,
    store: JobStoreLike,
    passed_candidates_from_payload: PassedCandidates,
    run_config_from_payload: RunConfigFromPayload,
    api_from_run_config: ApiFromRunConfig,
    repository_factory: RepositoryFactory,
    ledger_factory: LedgerFactory,
    refresh_cloud_context_for_check: RefreshCloudContext,
    payload_truthy: PayloadTruthy,
    check_candidate_availability: CheckAvailability,
    observability_submission_preflight: ObservabilityPreflight,
    safe_error_message: SafeErrorMessage,
    error_payload: ErrorPayload,
) -> None:
    mode = str(payload.get("mode", "quick"))
    sync_range = str(payload.get("syncRange", "all"))
    candidates = passed_candidates_from_payload(payload)
    total = len(candidates)
    checked = 0
    submittable = 0
    blocked = 0
    failed = 0
    blocker_counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    cloud_alphas: list[dict[str, Any]] = []
    cloud_error = ""
    started_at = time.time()
    try:
        store.update(
            job_id,
            status="running",
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "check_batch",
                "phase": "cloud_sync",
                "status_code": "CHECK_CLOUD_SYNC",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "percent": 0 if total else 100,
                "percent_complete": 0 if total else 100,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "status_message": f"Preparing real-time checks for {total} passed alpha(s).",
                "message": f"Preparing real-time checks for {total} passed alpha(s).",
                **_timing_payload(started_at, done=0, total=total),
                "items": [],
            },
        )
        if _store_is_cancelled(store, job_id):
            _update_check_batch_cancelled(
                store,
                job_id,
                mode=mode,
                sync_range=sync_range,
                total=total,
                checked=checked,
                submittable=submittable,
                blocked=blocked,
                failed=failed,
                started_at=started_at,
                results=results,
            )
            return
        run_config = run_config_from_payload(payload)
        if _store_is_cancelled(store, job_id):
            _update_check_batch_cancelled(
                store,
                job_id,
                mode=mode,
                sync_range=sync_range,
                total=total,
                checked=checked,
                submittable=submittable,
                blocked=blocked,
                failed=failed,
                started_at=started_at,
                results=results,
            )
            return
        api = api_from_run_config(run_config)
        repo = repository_factory(run_config.ops.storage_dir)
        api.authenticate()
        if _store_is_cancelled(store, job_id):
            _update_check_batch_cancelled(
                store,
                job_id,
                mode=mode,
                sync_range=sync_range,
                total=total,
                checked=checked,
                submittable=submittable,
                blocked=blocked,
                failed=failed,
                started_at=started_at,
                results=results,
            )
            return
        cloud_alphas, cloud_error = refresh_cloud_context_for_check(
            api,
            repo,
            sync_range,
            job_id,
            total,
            mode,
            run_config.ops.settings.region,
            refresh_remote=payload_truthy(payload.get("refreshCloudForCheck")),
        )
        ledger = ledger_factory(run_config.ops.storage_dir)
        observability_preflight = observability_submission_preflight(run_config.ops.storage_dir)

        for index, candidate in enumerate(candidates, start=1):
            if _store_is_cancelled(store, job_id):
                _update_check_batch_cancelled(
                    store,
                    job_id,
                    mode=mode,
                    sync_range=sync_range,
                    total=total,
                    checked=checked,
                    submittable=submittable,
                    blocked=blocked,
                    failed=failed,
                    started_at=started_at,
                    results=results,
                )
                return
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "check_batch",
                    "phase": "checking",
                    "status_code": "CHECK_RUNNING",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "percent": (checked / total * 100) if total else 100,
                    "percent_complete": (checked / total * 100) if total else 100,
                    "checked": checked,
                    "submittable": submittable,
                    "blocked": blocked,
                    "failed": failed,
                    "current_alpha_id": candidate.get("alpha_id", ""),
                    "status_message": f"Checking {index}/{total}: {candidate.get('alpha_id', '')}",
                    "message": f"Checking {index}/{total}: {candidate.get('alpha_id', '')}",
                    **_timing_payload(started_at, done=checked, total=total),
                    "items": results,
                },
            )
            if _store_is_cancelled(store, job_id):
                _update_check_batch_cancelled(
                    store,
                    job_id,
                    mode=mode,
                    sync_range=sync_range,
                    total=total,
                    checked=checked,
                    submittable=submittable,
                    blocked=blocked,
                    failed=failed,
                    started_at=started_at,
                    results=results,
                )
                return
            result = check_candidate_availability(
                candidate,
                mode,
                api,
                ledger,
                cloud_alphas,
                cloud_error,
                observability_preflight=observability_preflight,
            )
            results.append(result)
            checked += 1
            if result.get("submittable", result.get("passed")):
                submittable += 1
            elif result.get("error"):
                failed += 1
            else:
                blocked += 1
                for check in result.get("checks") or []:
                    if isinstance(check, dict) and check.get("passed") is False:
                        blocker_counts[str(check.get("name") or "unknown")] += 1
            repo.save_check_record({"job_id": str(payload.get("job_id", "")), **result})
            persist_candidate_check_evidence(run_config.ops.storage_dir, candidate, result)
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "check_batch",
                    "phase": "checking",
                    "status_code": "CHECK_RUNNING",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "percent": (checked / total * 100) if total else 100,
                    "percent_complete": (checked / total * 100) if total else 100,
                    "checked": checked,
                    "submittable": submittable,
                    "blocked": blocked,
                    "failed": failed,
                    "blockers": dict(blocker_counts.most_common(5)),
                    "current_alpha_id": candidate.get("alpha_id", ""),
                    "status_message": f"Checked {checked}/{total}; submittable {submittable}, blocked {blocked}, failed {failed}.",
                    "message": f"Checked {checked}/{total}; submittable {submittable}, blocked {blocked}, failed {failed}.",
                    **_timing_payload(started_at, done=checked, total=total),
                    "items": results,
                },
            )

        if _store_is_cancelled(store, job_id):
            _update_check_batch_cancelled(
                store,
                job_id,
                mode=mode,
                sync_range=sync_range,
                total=total,
                checked=checked,
                submittable=submittable,
                blocked=blocked,
                failed=failed,
                started_at=started_at,
                results=results,
            )
            return

        summary = {
            "mode": mode,
            "range": sync_range,
            "total": total,
            "checked": checked,
            "submittable": submittable,
            "blocked": blocked,
            "failed": failed,
            "cloud_count": len(cloud_alphas),
            "cloud_error": cloud_error,
            "blockers": dict(blocker_counts.most_common(5)),
        }
        store.update(
            job_id,
            status="completed",
            result={"ok": True, "summary": summary, "items": results},
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "check_batch",
                "phase": "completed",
                "status_code": "CHECK_COMPLETED",
                "percent": 100,
                "percent_complete": 100,
                "status_message": "Batch check completed.",
                "message": "Batch check completed.",
                **_timing_payload(started_at, done=checked, total=total),
                "items": results,
                **summary,
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="CHECK_BATCH_JOB_FAILED", job_id=job_id, phase="check_batch_job")
        logger.error("check batch job failed: %s", error_context, exc_info=True)
        store.update(
            job_id,
            status="failed",
            error=message,
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "check_batch",
                "phase": "failed",
                "status_code": "CHECK_FAILED",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "percent": 100,
                "percent_complete": 100,
                "checked": checked,
                "submittable": submittable,
                "blocked": blocked,
                "failed": failed + 1,
                "status_message": message,
                "message": message,
                **_timing_payload(started_at, done=checked, total=total),
                "items": results,
                "error_context": error_context,
            },
        )

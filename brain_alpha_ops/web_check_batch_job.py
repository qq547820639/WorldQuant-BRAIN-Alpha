"""Batch check background job service for the local web console."""

from __future__ import annotations

from collections import Counter
import logging
from typing import Any, Callable, Protocol

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger


logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


PassedCandidates = Callable[[dict[str, Any]], list[dict[str, Any]]]
RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ApiFromRunConfig = Callable[[RunConfig], Any]
RepositoryFactory = Callable[[str], ResearchRepository]
LedgerFactory = Callable[[str], SubmissionLedger]
PayloadTruthy = Callable[[object], bool]
RefreshCloudContext = Callable[..., tuple[list[dict[str, Any]], str]]
CheckAvailability = Callable[..., dict[str, Any]]
ObservabilityPreflight = Callable[[str], dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]
ErrorPayload = Callable[..., dict[str, Any]]


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
    sync_range = str(payload.get("syncRange", "3d"))
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
    try:
        store.update(
            job_id,
            status="running",
            progress={
                "phase": "cloud_sync",
                "status_code": "CHECK_CLOUD_SYNC",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "message": f"Preparing real-time checks for {total} passed alpha(s).",
                "items": [],
            },
        )
        run_config = run_config_from_payload(payload)
        api = api_from_run_config(run_config)
        repo = repository_factory(run_config.ops.storage_dir)
        api.authenticate()
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
            store.update(
                job_id,
                status="running",
                progress={
                    "phase": "checking",
                    "status_code": "CHECK_RUNNING",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "checked": checked,
                    "submittable": submittable,
                    "blocked": blocked,
                    "failed": failed,
                    "current_alpha_id": candidate.get("alpha_id", ""),
                    "message": f"Checking {index}/{total}: {candidate.get('alpha_id', '')}",
                    "items": results,
                },
            )
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
            store.update(
                job_id,
                status="running",
                progress={
                    "phase": "checking",
                    "status_code": "CHECK_RUNNING",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "checked": checked,
                    "submittable": submittable,
                    "blocked": blocked,
                    "failed": failed,
                    "blockers": dict(blocker_counts.most_common(5)),
                    "current_alpha_id": candidate.get("alpha_id", ""),
                    "message": f"Checked {checked}/{total}; submittable {submittable}, blocked {blocked}, failed {failed}.",
                    "items": results,
                },
            )

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
                "phase": "completed",
                "status_code": "CHECK_COMPLETED",
                "message": "Batch check completed.",
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
                "phase": "failed",
                "status_code": "CHECK_FAILED",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "checked": checked,
                "submittable": submittable,
                "blocked": blocked,
                "failed": failed + 1,
                "message": message,
                "items": results,
                "error_context": error_context,
            },
        )

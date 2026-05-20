"""Single candidate check orchestration for the local web console."""

from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger


logger = logging.getLogger(__name__)

CandidateFromPayload = Callable[[dict[str, Any]], dict[str, Any]]
RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ApiFromRunConfig = Callable[[RunConfig], Any]
RepositoryFactory = Callable[[str], ResearchRepository]
LedgerFactory = Callable[[str], SubmissionLedger]
PayloadTruthy = Callable[[object], bool]
RefreshCloudContext = Callable[..., tuple[list[dict[str, Any]], str]]
CheckAvailability = Callable[..., dict[str, Any]]
ObservabilityPreflight = Callable[[str], dict[str, Any]]
WebError = Callable[[Exception, str], dict[str, Any]]


def check_candidate_payload(
    payload: dict[str, Any],
    *,
    candidate_from_payload: CandidateFromPayload,
    run_config_from_payload: RunConfigFromPayload,
    api_from_run_config: ApiFromRunConfig,
    repository_factory: RepositoryFactory,
    ledger_factory: LedgerFactory,
    refresh_cloud_context_for_check: RefreshCloudContext,
    payload_truthy: PayloadTruthy,
    check_candidate_availability: CheckAvailability,
    observability_submission_preflight: ObservabilityPreflight,
    web_error: WebError,
) -> dict[str, Any]:
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict) or not candidate:
        candidate = candidate_from_payload(payload)
    if not candidate:
        return {"ok": False, "error_code": "VALIDATION_ERROR", "error": "candidate not found"}

    mode = str(payload.get("mode", "quick"))
    sync_range = str(payload.get("syncRange", "3d"))
    run_config = run_config_from_payload(payload)
    api = api_from_run_config(run_config)
    repo = repository_factory(run_config.ops.storage_dir)

    try:
        api.authenticate()
    except Exception as exc:
        return web_error(exc, "AUTH_FAILED")

    cloud_alphas, cloud_error = refresh_cloud_context_for_check(
        api,
        repo,
        sync_range,
        job_id=str(payload.get("job_id", "manual_check")),
        total=1,
        mode=mode,
        region=run_config.ops.settings.region,
        refresh_remote=payload_truthy(payload.get("refreshCloudForCheck")),
    )

    ledger = ledger_factory(run_config.ops.storage_dir)
    result = check_candidate_availability(
        candidate,
        mode,
        api,
        ledger,
        cloud_alphas,
        cloud_error,
        observability_preflight=observability_submission_preflight(run_config.ops.storage_dir),
    )

    try:
        repo.save_check_record({"job_id": str(payload.get("job_id", "")), **result})
    except Exception:
        logger.warning("failed to persist check record for alpha_id=%s", result.get("alpha_id", "?"), exc_info=True)

    return result

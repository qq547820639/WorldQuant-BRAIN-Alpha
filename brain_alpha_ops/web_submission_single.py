"""Single candidate submission orchestration for the local web console."""

from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate, utc_now
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger


logger = logging.getLogger(__name__)

RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
CandidateFromPayload = Callable[[dict[str, Any]], dict[str, Any]]
Preflight = Callable[[dict[str, Any], RunConfig], dict[str, Any]]
RecordBlocked = Callable[[dict[str, Any], dict[str, Any], RunConfig, str], None]
OfficialAlphaId = Callable[[dict[str, Any]], str]
ObservabilityPreflight = Callable[[str], dict[str, Any]]
PayloadTruthy = Callable[[object], bool]
ApiFromRunConfig = Callable[[RunConfig], Any]
LedgerFactory = Callable[[str], SubmissionLedger]
RepositoryFactory = Callable[[str], ResearchRepository]


def submit_candidate_payload(
    payload: dict[str, Any],
    *,
    candidate_from_payload: CandidateFromPayload,
    run_config_from_payload: RunConfigFromPayload,
    submission_preflight_advisory: Preflight,
    record_submit_blocked: RecordBlocked,
    official_alpha_id: OfficialAlphaId,
    observability_submission_preflight: ObservabilityPreflight,
    payload_truthy: PayloadTruthy,
    api_from_run_config: ApiFromRunConfig,
    ledger_factory: LedgerFactory = SubmissionLedger,
    repository_factory: RepositoryFactory = ResearchRepository,
) -> dict[str, Any]:
    candidate = candidate_from_payload(payload)
    if not candidate:
        return {"ok": False, "error_code": "VALIDATION_ERROR", "error": "candidate not found"}
    run_config = run_config_from_payload(payload)
    preflight = submission_preflight_advisory(candidate, run_config)
    if not preflight.get("ok"):
        record_submit_blocked(payload, candidate, run_config, str(preflight.get("error") or "Submission blocked."))
        return preflight
    official_id = official_alpha_id(candidate)
    observability_preflight = observability_submission_preflight(run_config.ops.storage_dir)
    if observability_preflight.get("requires_confirmation") and not payload_truthy(payload.get("confirm_observability_risk")):
        error = "Observability diagnostics recommend pausing submission until blocking flags are acknowledged."
        return {
            "ok": False,
            "error_code": "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED",
            "error": error,
            "observability_preflight": observability_preflight,
        }
    api = api_from_run_config(run_config)
    api.authenticate()
    result = api.submit_alpha(official_id, candidate.get("expression", ""), run_config.ops.settings.to_platform_dict()["settings"])
    try:
        ledger_factory(run_config.ops.storage_dir).record(
            Candidate.from_dict(candidate),
            result,
            mode=str(payload.get("submit_mode", "manual")),
        )
    except Exception:
        logger.warning("failed to record submission ledger for alpha_id=%s", candidate.get("alpha_id", "?"), exc_info=True)
    repository_factory(run_config.ops.storage_dir).save_lifecycle_record(
        str(payload.get("job_id", "")) or "manual_submit",
        {
            "timestamp": utc_now(),
            "alpha_id": candidate.get("alpha_id", ""),
            "official_alpha_id": official_id,
            "stage": "submitted",
            "status": result.get("status", "SUBMITTED"),
            "family": candidate.get("family", ""),
            "score": (candidate.get("scorecard") or {}).get("total_score", 0.0),
            "simulation_id": candidate.get("simulation_id", ""),
            "expression": candidate.get("expression", ""),
            "note": "manual",
        },
    )
    return {"ok": True, "submission": result}

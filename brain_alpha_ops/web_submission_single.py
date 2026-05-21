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
        return _submission_contract_payload(preflight, candidate, official_alpha_id(candidate))
    official_id = official_alpha_id(candidate)
    observability_preflight = observability_submission_preflight(run_config.ops.storage_dir)
    if observability_preflight.get("requires_confirmation") and not payload_truthy(payload.get("confirm_observability_risk")):
        error = "Observability diagnostics recommend pausing submission until blocking flags are acknowledged."
        risk_explanation = observability_preflight.get("risk_explanation") if isinstance(observability_preflight.get("risk_explanation"), dict) else {}
        return _submission_contract_payload({
            "ok": False,
            "error_code": "SUBMIT_OBSERVABILITY_CONFIRMATION_REQUIRED",
            "error": error,
            "observability_preflight": observability_preflight,
            "risk_explanation": risk_explanation,
            "risk_explanations": [risk_explanation] if risk_explanation else [],
            "state_navigation": observability_preflight.get("state_navigation") if isinstance(observability_preflight.get("state_navigation"), dict) else {},
        }, candidate, official_id)
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
    return _submission_contract_payload(
        {
            "ok": True,
            "submission": result,
            "status": result.get("status", "SUBMITTED"),
            "state_navigation": {
                "schema_version": "abnormal_state_navigation.v1",
                "state": "completed",
                "reason_code": "SUBMISSION_ACCEPTED",
                "title": "提交已受理",
                "summary": "官方提交请求已完成，本地提交账本和生命周期已记录。",
                "target_view": "submitted",
                "primary_action": "查看已提交列表或云端状态。",
                "steps": [
                    {"id": "submitted", "label": "提交完成", "status": "done", "view": "submitted"},
                    {"id": "sync_cloud", "label": "刷新云端状态", "status": "pending", "view": "cloud"},
                ],
            },
        },
        candidate,
        official_id,
    )


def _submission_contract_payload(payload: dict[str, Any], candidate: dict[str, Any], official_id: str) -> dict[str, Any]:
    enriched = dict(payload)
    enriched.setdefault("schema_version", "submission_result.v2")
    enriched.setdefault("alpha_id", candidate.get("alpha_id", ""))
    enriched.setdefault("official_alpha_id", official_id)
    enriched.setdefault("status", "SUBMITTED" if enriched.get("ok") else "BLOCKED")
    if "state_navigation" not in enriched:
        enriched["state_navigation"] = {}
    if "risk_explanations" not in enriched and isinstance(enriched.get("risk_explanation"), dict) and enriched.get("risk_explanation"):
        enriched["risk_explanations"] = [enriched["risk_explanation"]]
    return enriched

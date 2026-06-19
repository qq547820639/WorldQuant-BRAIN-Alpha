"""Single candidate submission orchestration for the local web console.

P0-2 guard: a hard ``REAL_SUBMIT_DISABLED_WEB_FLOW`` kill-switch prevents
the Web console from issuing real ``api.submit_alpha`` calls.  Tests can
opt out by patching ``brain_alpha_ops.runtime_constants.REAL_SUBMIT_DISABLED_WEB_FLOW``
to ``False`` for the duration of the test (monkeypatch.setattr).  See
``tests/test_web_submission_single.py`` for the canonical pattern.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.models import Candidate, utc_now
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.safety import SubmissionLedger
from brain_alpha_ops.runtime_constants import REAL_SUBMIT_DISABLED_WEB_FLOW
from brain_alpha_ops.submission_readiness import live_submit_readiness_hard_gate

logger = logging.getLogger(__name__)

def _real_submit_disabled() -> bool:
    """Return True if the Web console's real submit flow is hard-blocked.

    Honours an opt-out env var for tests: setting
    ``BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS=1`` (and only that env var, no
    other channel) returns False.  Production never sets this.
    """
    if REAL_SUBMIT_DISABLED_WEB_FLOW is False:
        return False
    if os.environ.get("BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS") == "1":
        return False
    return True

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
SubmitReadinessHardGate = Callable[[dict[str, Any], RunConfig, str], dict[str, Any]]

# Hard kill-switch payload — the Web console must NEVER issue a real
# submit_alpha call.  This blocks before the API is even instantiated.
# P0-1: added required_next_steps and state_navigation so the frontend
# can render a structured exit-path panel instead of a dead-end error.
_REAL_SUBMIT_DISABLED_PAYLOAD = {
    "ok": False,
    "error_code": "REAL_SUBMIT_DISABLED_WEB_FLOW",
    "error": "Real alpha submission is disabled in the Web flow. Use the separate approval/CLI path.",
    "error_category": "policy",
    "action": "Submit through the offline approval pipeline; the Web console is read+preflight only.",
    "required_next_steps": [
        "review final submission intent before any real submit",
        "run official simulation/check in a trusted environment",
    ],
    "state_navigation": {
        "schema_version": "abnormal_state_navigation.v1",
        "state": "blocked",
        "reason_code": "REAL_SUBMIT_DISABLED_WEB_FLOW",
        "title": "需要单独提交审批",
        "summary": "您的候选已通过全部质量门禁。Web 控制台不执行真实提交；请通过 BRAIN 平台控制台手动提交。",
        "target_view": "submission",
        "primary_action": "前往 BRAIN 平台手动提交",
        "steps": [
            {
                "id": "review_readiness",
                "status": "done",
                "label": "阻断复核已完成",
                "description": "候选已达到可提交标准",
            },
            {
                "id": "manual_submit",
                "status": "pending",
                "label": "通过 BRAIN 平台手动提交",
                "description": "访问 https://platform.worldquantbrain.com/alphas 完成真实提交",
            },
        ],
        "exit_paths": [
            {
                "id": "brain_platform",
                "label": "BRAIN 平台控制台",
                "url": "https://platform.worldquantbrain.com/alphas",
                "description": "在 BRAIN 官方平台完成真实 Alpha 提交",
                "action_type": "external_link",
            },
            {
                "id": "candidate_management",
                "label": "返回候选管理",
                "view": "candidates",
                "description": "继续优化或管理候选",
                "action_type": "navigate",
            },
        ],
        "all_gates_passed": True,
        "human_confirmation_required": True,
    },
}

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
    submit_readiness_hard_gate: SubmitReadinessHardGate = live_submit_readiness_hard_gate,
    ledger_factory: LedgerFactory = SubmissionLedger,
    repository_factory: RepositoryFactory = ResearchRepository,
) -> dict[str, Any]:
    # P0 guard: if the kill-switch is on, return the block payload BEFORE
    # touching any api object.  This makes the constraint tamper-proof:
    # flipping REAL_SUBMIT_DISABLED_WEB_FLOW to False is the only way to
    # re-enable real submission through this entry point.
    if _real_submit_disabled():
        try:
            candidate = candidate_from_payload(payload)
        except Exception:
            candidate = {}
        return _submission_contract_payload(
            dict(_REAL_SUBMIT_DISABLED_PAYLOAD),
            candidate,
            official_alpha_id(candidate) if isinstance(candidate, dict) else "",
        )
    candidate = candidate_from_payload(payload)
    if not candidate:
        return {"ok": False, "error_code": "VALIDATION_ERROR", "error": "candidate not found"}
    run_config = run_config_from_payload(payload)
    official_id = official_alpha_id(candidate)
    if not payload_truthy(payload.get("confirm_submit")):
        return _submission_contract_payload({
            "ok": False,
            "error_code": "SUBMIT_CONFIRMATION_REQUIRED",
            "error": "Production submit requires explicit confirm_submit=true.",
            "error_category": "confirmation",
            "action": "Complete readiness review first; real submit is outside the ordinary Web flow and requires separate approval.",
            "state_navigation": {
                "schema_version": "abnormal_state_navigation.v1",
                "state": "blocked",
                "reason_code": "SUBMIT_CONFIRMATION_REQUIRED",
                "title": "需要单独提交审批",
                "summary": "普通 Web 就绪复核流程不会执行真实提交；后端已在调用官方提交 API 前阻断。",
                "target_view": "submit",
                "primary_action": "先完成提交前就绪复核；如需真实提交，走单独审批路径。",
            },
        }, candidate, official_id)
    preflight = submission_preflight_advisory(candidate, run_config)
    if not preflight.get("ok"):
        record_submit_blocked(payload, candidate, run_config, str(preflight.get("error") or "Submission blocked."))
        return _submission_contract_payload(preflight, candidate, official_id)
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
    readiness_gate = submit_readiness_hard_gate(candidate, run_config, official_id)
    if not readiness_gate.get("ok"):
        record_submit_blocked(payload, candidate, run_config, str(readiness_gate.get("error") or "Submit readiness hard gate blocked submission."))
        return _submission_contract_payload(readiness_gate, candidate, official_id)
    api = api_from_run_config(run_config)
    api.authenticate()
    result = api.submit_alpha(official_id, candidate.get("expression", ""), run_config.ops.settings.to_platform_dict()["settings"])
    try:
        ledger_factory(run_config.ops.storage_dir).record(
            Candidate.from_dict(candidate),
            result,
            mode=str(payload.get("submit_mode", "manual")),
        )
    except Exception as exc:
        logger.warning(
            "failed to record submission ledger for alpha_id=%s: %s",
            redact_text(candidate.get("alpha_id", "?"), max_length=64),
            redact_error_message(exc),
        )
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

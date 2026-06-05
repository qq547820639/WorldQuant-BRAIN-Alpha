"""Candidate generation, check, and selection."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from brain_alpha_ops.agent_tools import BrainAlphaToolbox
from brain_alpha_ops.config import RunConfig, resolve_default_dataset_id
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.errors import ValidationError
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.alpha_quality import (
    build_alpha_output_config,
    diagnose_alpha_candidate,
    summarize_quality_diagnostics,
)
from brain_alpha_ops.research.generator import extract_fields, extract_operators, local_quality
from brain_alpha_ops.research.fallback_generation import high_turnover_generation_risk_reasons
from brain_alpha_ops.research.guidance import (
    assistant_guidance_candidate_metadata,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.local_backtest_engine import LocalBacktestEngine
from brain_alpha_ops.research.local_backtest_gate import apply_local_backtest_gate, blocked_local_gate
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.scoring import build_scorecard
from brain_alpha_ops.web_config import (
    _MAX_CANDIDATES,
    bounded_query_float,
    bounded_query_int,
    payload_truthy,
)


class ToolboxLike(Protocol):
    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ToolboxFactory = Callable[[RunConfig], ToolboxLike]
RepositoryFactory = Callable[[str], ResearchRepository]


def _default_toolbox_factory(run_config: RunConfig) -> ToolboxLike:
    return BrainAlphaToolbox(run_config=run_config, allow_live_api=False, allow_submit=False)


def generate_candidates_payload(
    payload: dict[str, Any],
    *,
    run_config_from_payload: RunConfigFromPayload,
    toolbox_factory: ToolboxFactory = _default_toolbox_factory,
    repository_factory: RepositoryFactory = ResearchRepository,
) -> dict[str, Any]:
    payload = dict(payload or {})
    run_config = run_config_from_payload(payload)
    dataset_id = str(payload.get("dataset_id") or run_config.ops.settings.dataset or "").strip()
    if not dataset_id:
        dataset_id = resolve_default_dataset_id(run_config.ops.storage_dir)
        run_config.ops.settings.dataset = dataset_id
    args = {
        "count": bounded_query_int(payload.get("count", payload.get("candidates", 10)), 1, _MAX_CANDIDATES),
        "dataset_id": dataset_id,
        "use_research_memory": payload_truthy(payload.get("use_research_memory", True)),
        "top_n": bounded_query_int(payload.get("top_n", 10), 1, 50),
        "min_success_rate": bounded_query_float(payload.get("min_success_rate", 0.0), 0.0, 1.0),
        "assistant_min_confidence": bounded_query_float(payload.get("assistant_min_confidence", 0.0), 0.0, 1.0),
    }
    for key in ("assistant_response", "assistant_raw_output", "assistant_guidance"):
        if key in payload:
            args[key] = payload[key]
    try:
        result = toolbox_factory(run_config).call("generate_candidates", args)
    except Exception as exc:
        return user_error_payload(
            exc,
            error_code="GENERATE_CANDIDATES_TOOLBOX_ERROR",
            phase="web_generate_candidates",
        )
    if not isinstance(result, dict):
        return user_error_payload(
            ValidationError("candidate generator returned a non-object response"),
            error_code="GENERATE_CANDIDATES_VALIDATION_ERROR",
            phase="web_generate_candidates",
        )
    if not result.get("ok"):
        return result

    alpha_output_config = build_alpha_output_config(
        run_config,
        dataset_id=dataset_id,
        generation_args=args,
    )
    candidates: list[dict[str, Any]] = []
    local_backtest_engine = LocalBacktestEngine()
    raw_assistant_guidance = result.get("assistant_guidance")
    assistant_guidance = raw_assistant_guidance if isinstance(raw_assistant_guidance, dict) else {}
    assistant_guidance_applied = bool(assistant_guidance.get("applied"))
    assistant_guidance = ensure_assistant_guidance_digest(assistant_guidance) if assistant_guidance else {}
    for row in result.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        candidate = Candidate.from_dict(row)
        if not candidate.dataset_id:
            candidate.dataset_id = dataset_id
        candidate.local_quality = local_quality(candidate, run_config.ops.budget.min_local_quality_score)
        apply_local_backtest_gate(
            candidate,
            engine=local_backtest_engine,
            cache_key=candidate.dataset_id or run_config.ops.settings.dataset or "default",
            extract_fields=extract_fields,
            extract_operators=extract_operators,
        )
        candidate.scorecard = build_scorecard(candidate, run_config.ops.thresholds, run_config.ops.scoring)
        candidate.alpha_output_config = alpha_output_config
        generation_risks = high_turnover_generation_risk_reasons(candidate.expression)
        if candidate.local_quality.get("passed") is False:
            candidate.lifecycle_status = "local_prefilter_rejected"
            candidate.gate = blocked_local_gate(list(candidate.local_quality.get("reasons") or []))
        else:
            candidate.lifecycle_status = "assistant_generated" if assistant_guidance_applied else "generated"
        tags = list(candidate.source_tags or [])
        tag_values = ["local_only"]
        if assistant_guidance_applied:
            tag_values.extend(["assistant_guided", f"assistant_guidance_{assistant_guidance.get('guidance_digest', '')}"])
            submission = dict(candidate.submission or {})
            submission.update(assistant_guidance_candidate_metadata(assistant_guidance))
            candidate.submission = submission
        if generation_risks:
            tag_values.append("generation_risk_blocked")
        for tag in tag_values:
            if tag not in tags:
                tags.append(tag)
        candidate.source_tags = tags
        candidate.quality_diagnosis = diagnose_alpha_candidate(
            candidate,
            run_config=run_config,
            output_config=alpha_output_config,
        )
        candidates.append(candidate.to_dict())

    quality_summary = summarize_quality_diagnostics(candidates)
    summary = {
        "generated_count": len(candidates),
        "source": "local_candidate_generator",
        "assistant_guidance": assistant_guidance or result.get("assistant_guidance"),
        "local_only": True,
        "official_api_called": False,
        "alpha_output_config": alpha_output_config,
        "quality_summary": quality_summary,
        "qualified_count": quality_summary.get("qualified_count", 0),
        "invalid_count": quality_summary.get("invalid_count", 0),
        "local_valid_count": quality_summary.get("local_valid_count", 0),
    }
    if assistant_guidance_applied and assistant_guidance:
        repository_factory(run_config.ops.storage_dir).save_assistant_guidance(
            assistant_guidance,
            source="web_generate_candidates",
        )
    return {
        "ok": True,
        "count": len(candidates),
        "candidates": candidates,
        "summary": summary,
        "assistant_guidance": assistant_guidance or result.get("assistant_guidance"),
    }

"""Single candidate check orchestration for the local web console."""

import logging
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.redaction import redact_error_message, redact_text
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
    except Exception as exc:
        logger.warning(
            "failed to persist check record for alpha_id=%s: %s",
            redact_text(result.get("alpha_id", "?"), max_length=64),
            redact_error_message(exc),
        )

    return result

"""Candidate selection helpers shared by web check and submit flows."""

from typing import Any, Protocol


class JobStoreLike(Protocol):
    def get(self, job_id: str) -> dict[str, Any] | None:
        ...


def candidate_from_payload(payload: dict[str, Any], job_store: JobStoreLike) -> dict[str, Any]:
    candidate = payload.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    alpha_id = str(payload.get("alpha_id", ""))
    job = job_store.get(str(payload.get("job_id", ""))) or {}
    pools: list[dict[str, Any]] = []
    result = job.get("result") or {}
    pools.extend(result.get("candidates") or [])
    pools.extend((result.get("summary") or {}).get("passed_candidates") or [])
    data = (job.get("progress") or {}).get("data") or {}
    pools.extend(data.get("candidates") or [])
    pools.extend(data.get("passed_candidates") or [])
    for item in pools:
        if isinstance(item, dict) and item.get("alpha_id") == alpha_id:
            return item
    return {}


def passed_candidates_from_payload(payload: dict[str, Any], job_store: JobStoreLike) -> list[dict[str, Any]]:
    candidates = payload.get("check_candidates")
    if not isinstance(candidates, list):
        candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        job = job_store.get(str(payload.get("job_id", ""))) or {}
        result = job.get("result") or {}
        data = (job.get("progress") or {}).get("data") or {}
        candidates = []
        candidates.extend((result.get("summary") or {}).get("passed_candidates") or [])
        candidates.extend(data.get("passed_candidates") or [])
        candidates.extend(result.get("candidates") or [])
        candidates.extend(data.get("candidates") or [])
    seen = set()
    passed: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        alpha_id = str(candidate.get("alpha_id", ""))
        if not alpha_id or alpha_id in seen:
            continue
        if is_passed_candidate_for_check(candidate):
            seen.add(alpha_id)
            passed.append(candidate)
    return passed


def candidate_official_metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = candidate.get("official_metrics")
    if isinstance(metrics, dict):
        return metrics
    metrics = candidate.get("metrics")
    return metrics if isinstance(metrics, dict) else {}


def official_alpha_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("official_alpha_id") or (candidate.get("official_metrics") or {}).get("official_alpha_id") or "")


def is_passed_candidate_for_check(candidate: dict[str, Any]) -> bool:
    gate = candidate.get("gate") or {}
    return bool(gate.get("submission_ready") or candidate.get("lifecycle_status") == "submission_ready")
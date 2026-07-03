"""Shared agent-facing helpers for the research tool surface."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.alerting import AlertDeliveryService, AlertRouter
from brain_alpha_ops.scoring.anti_overfit import AntiOverfitService
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    build_assistant_request_pack,
    parse_assistant_response,
)
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.guidance import (
    assistant_guidance_candidate_metadata,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.llm_review import cross_review_assistant_response
from brain_alpha_ops.research.market_data_cache import build_market_data_cache
from brain_alpha_ops.research.market_data_vector import build_vectorized_market_data
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.parallel_backtest import (
    ParallelBacktestExecutor,
    ParallelBacktestPlanner,
)
from brain_alpha_ops.research.parameter_search import ParameterSearchService
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.rolling_validation import RollingValidationService
from brain_alpha_ops.research.search_orchestrator import ParameterSearchOrchestrator
from brain_alpha_ops.shared_bounds import (
    bounded_float,
    bounded_int,
    candidate_argument,
    expression_batch_argument,
    list_text,
    required_text,
    truthy,
)

logger = logging.getLogger(__name__)


def query_research_observability_snapshot(
    storage_dir: str | Path,
    *,
    limit: int,
    top_n: int,
    include_cloud: bool,
    job_rows: list[dict[str, Any]] | None = None,
    job_diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_research_observability_snapshot(
        storage_dir,
        limit=limit,
        top_n=top_n,
        include_cloud=include_cloud,
        job_rows=job_rows,
        job_diagnostics=job_diagnostics,
    )


def build_market_data_cache_tool(
    storage_dir: str | Path,
    *,
    refresh: bool,
    source_file: str,
    limit: int | None,
) -> dict[str, Any]:
    cache = build_market_data_cache(storage_dir)
    if refresh:
        if source_file:
            source_path = Path(source_file)
            if source_path.is_absolute():
                return cache.refresh_from_path(source_path, source=source_path.name, limit=limit)
            return cache.refresh_from_jsonl(source_file, limit=limit)
        rows = ResearchRepository(storage_dir).latest_backtest_records(limit=limit if limit is not None else 5000)
        if rows:
            return cache.refresh_from_records(rows, source="backtests.jsonl")
    return cache.summary()


def build_vectorized_market_data_from_args(storage_dir: str | Path, args: dict[str, Any]) -> dict[str, Any]:
    field_list = list_text(args.get("fields"))
    return build_vectorized_market_data_tool(
        storage_dir,
        fields=field_list,
        limit_symbols=bounded_int(args.get("limit_symbols", 200), 1, 5000),
        min_field_coverage=bounded_float(args.get("min_field_coverage", 0.0), 0.0, 1.0),
        normalize=truthy(args.get("normalize", False)),
    )


def build_vectorized_market_data_tool(
    storage_dir: str | Path,
    *,
    fields: list[str] | None,
    limit_symbols: int,
    min_field_coverage: float = 0.0,
    normalize: bool = False,
) -> dict[str, Any]:
    return build_vectorized_market_data(
        storage_dir,
        fields=fields,
        limit_symbols=limit_symbols,
        min_field_coverage=min_field_coverage,
        normalize=normalize,
    )


def search_parameters_tool(candidate: Candidate, *, max_mutations: int) -> dict[str, Any]:
    return ParameterSearchService().search(candidate, max_mutations=max_mutations)


def orchestrate_parameter_search_from_args(args: dict[str, Any]) -> dict[str, Any]:
    return orchestrate_parameter_search_tool(
        Candidate.from_dict(candidate_argument(args)),
        rounds=bounded_int(args.get("rounds", 2), 1, 8),
        max_mutations=bounded_int(args.get("max_mutations", 4), 1, 12),
        keep_top=bounded_int(args.get("keep_top", 3), 1, 20),
    )


def orchestrate_parameter_search_tool(
    candidate: Candidate,
    *,
    rounds: int,
    max_mutations: int,
    keep_top: int,
) -> dict[str, Any]:
    return ParameterSearchOrchestrator().run(
        candidate,
        rounds=rounds,
        max_mutations=max_mutations,
        keep_top=keep_top,
    )


def plan_parallel_backtest_tool(
    expressions: list[str],
    *,
    markets: list[str] | None,
    max_workers: int,
    max_batches: int,
    per_account_limit: int,
) -> dict[str, Any]:
    return ParallelBacktestPlanner().plan(
        expressions,
        markets=markets,
        max_workers=max_workers,
        max_batches=max_batches,
        per_account_limit=per_account_limit,
    )


def plan_parallel_backtest_from_args(args: dict[str, Any]) -> dict[str, Any]:
    markets = list_text(args.get("markets")) or None
    return plan_parallel_backtest_tool(
        expression_batch_argument(args),
        markets=markets,
        max_workers=bounded_int(args.get("max_workers", 4), 1, 32),
        max_batches=bounded_int(args.get("max_batches", 10), 1, 100),
        per_account_limit=bounded_int(args.get("per_account_limit", 20), 1, 1000),
    )


def run_parallel_backtest_from_args(
    args: dict[str, Any],
    *,
    runner: Any,
    default_market: str,
) -> dict[str, Any]:
    return ParallelBacktestExecutor().execute(
        expression_batch_argument(args),
        runner=runner,
        markets=list_text(args.get("markets")) or [default_market],
        max_workers=bounded_int(args.get("max_workers", 1), 1, 3),
        max_batches=bounded_int(args.get("max_batches", 1), 1, 10),
        per_account_limit=bounded_int(args.get("per_account_limit", 10), 1, 10),
    )


def send_alert_tool(
    storage_dir: str | Path,
    *,
    title: str,
    message: str,
    severity: str,
    channel: str,
    webhook_url: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return AlertDeliveryService(storage_dir=storage_dir, webhook_url=webhook_url).alert(
        title,
        message,
        severity=severity,
        channel=channel,
        metadata=metadata,
    )


def route_alert_from_args(storage_dir: str | Path, args: dict[str, Any]) -> dict[str, Any]:
    return route_alert_tool(
        storage_dir,
        title=required_text(args, "title"),
        message=required_text(args, "message"),
        severity=str(args.get("severity", "info") or "info").strip() or "info",
        channels=list_text(args.get("channels")) or ["local"],
        routes=dict(args.get("routes") or {}),
        metadata=dict(args.get("metadata") or {}),
    )


def route_alert_tool(
    storage_dir: str | Path,
    *,
    title: str,
    message: str,
    severity: str,
    channels: list[str],
    routes: dict[str, str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return AlertRouter(storage_dir=storage_dir, routes=routes).route(
        title,
        message,
        severity=severity,
        channels=channels,
        metadata=metadata,
    )


def build_assistant_context_tool(run_config: RunConfig, args: dict[str, Any]) -> dict[str, Any]:
    return build_assistant_context_pack(
        run_config,
        limit=bounded_int(args.get("limit", 5000), 1, 50000),
        top_n=bounded_int(args.get("top_n", 10), 1, 50),
        include_prompt=truthy(args.get("include_prompt", True)),
        include_sensitive=truthy(args.get("include_sensitive", False)),
    )


def build_assistant_request_tool(run_config: RunConfig, args: dict[str, Any]) -> dict[str, Any]:
    context = build_assistant_context_pack(
        run_config,
        limit=bounded_int(args.get("limit", 5000), 1, 50000),
        top_n=bounded_int(args.get("top_n", 10), 1, 50),
        include_prompt=True,
        include_sensitive=truthy(args.get("include_sensitive", False)),
    )
    return build_assistant_request_pack(
        context,
        include_prompt=truthy(args.get("include_prompt", True)),
        include_offline_draft=truthy(args.get("include_offline_draft", True)),
    )


def parse_assistant_response_tool(args: dict[str, Any]) -> dict[str, Any]:
    raw_output = str(args.get("raw_output") or args.get("text") or "")
    try:
        return parse_assistant_response(raw_output)
    except AssistantResponseParseError as exc:
        return user_error_payload(exc, error_code="ASSISTANT_RESPONSE_PARSE_ERROR")


def assistant_response_guidance_tool(args: dict[str, Any]) -> dict[str, Any]:
    raw_output = str(args.get("raw_output") or args.get("text") or "")
    try:
        response = parse_assistant_response(raw_output)
        return assistant_response_to_generation_guidance(
            response,
            min_confidence=bounded_float(args.get("min_confidence", 0.0), 0.0, 1.0),
        )
    except AssistantResponseParseError as exc:
        return user_error_payload(exc, error_code="ASSISTANT_RESPONSE_PARSE_ERROR")


def run_anti_overfit_tool(args: dict[str, Any]) -> dict[str, Any]:
    return AntiOverfitService().evaluate(candidate_argument(args))


def run_rolling_validation_tool(args: dict[str, Any]) -> dict[str, Any]:
    return RollingValidationService().evaluate(
        candidate_argument(args),
        windows=bounded_int(args.get("windows", 4), 2, 20),
    )


def cross_review_assistant_response_tool(args: dict[str, Any]) -> dict[str, Any]:
    request_pack = args.get("request_pack")
    if not isinstance(request_pack, dict):
        return user_error_payload(ValueError("request_pack must be an object"), error_code="INVALID_REQUEST_PACK")
    primary = args.get("primary_response") or args.get("primary")
    reviewer = args.get("reviewer_response") or args.get("reviewer")
    try:
        return cross_review_assistant_response(
            request_pack,
            primary if primary is not None else "",
            reviewer_response=reviewer,
            min_confidence=bounded_float(args.get("min_confidence", 0.6), 0.0, 1.0),
        )
    except AssistantResponseParseError as exc:
        return user_error_payload(exc, error_code="ASSISTANT_CROSS_REVIEW_PARSE_ERROR")


def collect_job_rows(job_stores: Mapping[str, Any], *, limit: int) -> list[dict[str, Any]]:
    return collect_job_rows_with_diagnostics(job_stores, limit=limit)["rows"]


def collect_job_rows_with_diagnostics(job_stores: Mapping[str, Any], *, limit: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for kind, store in job_stores.items():
        all_jobs = getattr(store, "all", None)
        if not callable(all_jobs):
            continue
        try:
            for job_id, job in all_jobs(limit=limit):
                rows.append({"source": f"{kind}_job", "job_id": job_id, **job})
        except Exception as exc:
            message = redact_error_message(exc, max_length=240)
            logger.warning("failed to collect %s job rows for agent research context", kind, exc_info=True)
            diagnostics.append({
                "source": f"{kind}_job",
                "status": "collection_failed",
                "error": message,
                "error_context": {
                    "error_code": "JOB_ROWS_COLLECTION_FAILED",
                    "error": message,
                    "source": f"{kind}_job",
                },
            })
            continue
    return {
        "ok": not diagnostics,
        "partial": bool(diagnostics),
        "rows": rows[-limit:],
        "diagnostics": diagnostics,
    }


# ── Assistant guidance helpers (merged from ``agent_guidance_tools.py``) ──


def has_generator_bias(guidance: dict[str, Any] | None) -> bool:
    """Return True when guidance contains bias keys that the generator applies.

    Covers both the keys that ``assistant_guidance_for_generator`` consumes
    (top_operators, preferred_windows, field_combinations, top_fields) and
    any raw guidance key that directly biases generation.
    """
    if not guidance:
        return False
    return bool(
        guidance.get("top_operators")
        or guidance.get("preferred_windows")
        or guidance.get("field_combinations")
        or guidance.get("top_fields")
    )


def assistant_guidance_for_generator(guidance: dict[str, Any]) -> dict[str, Any]:
    if guidance.get("ok") is False or not _truthy(guidance.get("usable", True)):
        return {}

    top_operators = _unique_text_items(guidance.get("top_operators"))
    preferred_windows = _unique_number_items(guidance.get("preferred_windows"))
    field_combinations = _field_combinations(guidance.get("field_combinations"))
    top_fields = _unique_text_items(guidance.get("top_fields"))
    if top_fields:
        field_combinations.append({"fields": top_fields, "rationale": "assistant top fields"})
        field_combinations = _unique_field_combinations(field_combinations)

    if not top_operators and not preferred_windows and not field_combinations:
        return {}

    return {
        "sample_size": max(3, _safe_int(guidance.get("sample_size"), 0)),
        "top_operators": top_operators,
        "preferred_windows": preferred_windows,
        "field_combinations": field_combinations,
    }


def merge_generation_guidance(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    return {
        "sample_size": max(
            3,
            _safe_int(base.get("sample_size"), 0) + _safe_int(overlay.get("sample_size"), 0),
        ),
        "top_operators": _unique_text_items(
            _text_items(base.get("top_operators")) + _text_items(overlay.get("top_operators"))
        ),
        "preferred_windows": _unique_number_items(
            _number_items(base.get("preferred_windows")) + _number_items(overlay.get("preferred_windows"))
        ),
        "field_combinations": _unique_field_combinations(
            _field_combinations(base.get("field_combinations")) + _field_combinations(overlay.get("field_combinations"))
        ),
    }


def assistant_guidance_summary(guidance: dict[str, Any], *, applied: bool) -> dict[str, Any]:
    guidance = ensure_assistant_guidance_digest(guidance)
    metadata = assistant_guidance_candidate_metadata(guidance)
    usable = guidance.get("ok") is not False and _truthy(guidance.get("usable", True))
    if applied:
        reason = "applied_to_generator"
    elif not usable:
        reason = "not_usable"
    else:
        reason = "no_generator_bias"
    return {
        "ok": guidance.get("ok", True),
        "source": guidance.get("source", ""),
        "usable": usable,
        "applied": applied,
        "reason": reason,
        "guidance_digest": guidance.get("guidance_digest"),
        "confidence": guidance.get("confidence"),
        "min_confidence": guidance.get("min_confidence"),
        "sample_size": guidance.get("sample_size"),
        "top_fields": _unique_text_items(guidance.get("top_fields"))[:10],
        "top_operators": _unique_text_items(guidance.get("top_operators"))[:10],
        "preferred_windows": _unique_number_items(guidance.get("preferred_windows"))[:10],
        "field_combinations": _field_combinations(guidance.get("field_combinations"))[:10],
        "field_combinations_count": len(_field_combinations(guidance.get("field_combinations"))),
        "risk_flags": _unique_text_items(guidance.get("risk_flags"))[:10],
        "operational_flags": guidance.get("operational_flags") if isinstance(guidance.get("operational_flags"), dict) else {},
        "historical_outcome_status": metadata.get("assistant_guidance_outcome_status", "unknown"),
        "historical_outcome": metadata.get("assistant_guidance_outcome", {}),
    }


def attach_assistant_guidance(candidate: Candidate, guidance: dict[str, Any]) -> None:
    guidance = ensure_assistant_guidance_digest(guidance)
    digest = str(guidance.get("guidance_digest") or "")
    tags = list(candidate.source_tags or [])
    for tag in ("assistant_guided", f"assistant_guidance_{digest}"):
        if tag and tag not in tags:
            tags.append(tag)
    candidate.source_tags = tags
    submission = dict(candidate.submission or {})
    submission.update(assistant_guidance_candidate_metadata(guidance))
    candidate.submission = submission


def guidance_sample_size(guidance: dict[str, Any]) -> int:
    return max(
        len(_text_items(guidance.get("top_fields"))),
        len(_text_items(guidance.get("top_operators"))),
        len(_number_items(guidance.get("preferred_windows"))),
        len(_field_combinations(guidance.get("field_combinations"))),
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _text_items(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def _unique_text_items(value: Any) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in _text_items(value):
        marker = item.lower()
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def _number_items(value: Any) -> list[int | float]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    rows: list[int | float] = []
    for item in values:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if number != number or number in (float("inf"), float("-inf")):
            continue
        rows.append(int(number) if number.is_integer() else number)
    return rows


def _unique_number_items(value: Any) -> list[int | float]:
    seen: set[float] = set()
    unique: list[int | float] = []
    for item in _number_items(value):
        marker = float(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def _field_combinations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            fields = _unique_text_items(item.get("fields") or item.get("field") or item.get("value"))
            rationale = str(item.get("rationale") or "")
        else:
            fields = _unique_text_items(item)
            rationale = ""
        if fields:
            rows.append({"fields": fields, "rationale": rationale})
    return rows


def _unique_field_combinations(value: Any) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, Any]] = []
    for combo in _field_combinations(value):
        fields = _unique_text_items(combo.get("fields"))
        marker = tuple(field.lower() for field in fields)
        if not marker or marker in seen:
            continue
        seen.add(marker)
        unique.append({"fields": fields, "rationale": str(combo.get("rationale") or "")})
    return unique


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

"""Shared agent-facing helpers for the research tool surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.shared_bounds import (
    bounded_float,
    bounded_int,
    candidate_argument,
    expression_batch_argument,
    list_text,
    required_text,
    truthy,
)
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    build_assistant_request_pack,
    parse_assistant_response,
)
from brain_alpha_ops.research.alerting import AlertDeliveryService, AlertRouter
from brain_alpha_ops.research.anti_overfit import AntiOverfitService
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.llm_review import cross_review_assistant_response
from brain_alpha_ops.research.market_data_cache import build_market_data_cache
from brain_alpha_ops.research.market_data_vector import build_vectorized_market_data
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.parallel_backtest import ParallelBacktestExecutor, ParallelBacktestPlanner
from brain_alpha_ops.research.parameter_search import ParameterSearchService
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.rolling_validation import RollingValidationService
from brain_alpha_ops.research.search_orchestrator import ParameterSearchOrchestrator


def query_research_observability_snapshot(
    storage_dir: str | Path,
    *,
    limit: int,
    top_n: int,
    include_cloud: bool,
    job_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return build_research_observability_snapshot(
        storage_dir,
        limit=limit,
        top_n=top_n,
        include_cloud=include_cloud,
        job_rows=job_rows,
    )


def build_market_data_cache_tool(
    storage_dir: str | Path,
    *,
    refresh: bool,
    source_file: str,
    limit: int,
) -> dict[str, Any]:
    cache = build_market_data_cache(storage_dir)
    if refresh:
        if source_file:
            source_path = Path(source_file)
            if source_path.is_absolute():
                return cache.refresh_from_path(source_path, source=source_path.name, limit=limit)
            return cache.refresh_from_jsonl(source_file, limit=limit)
        rows = ResearchRepository(storage_dir).latest_backtest_records(limit=limit)
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
    rows: list[dict[str, Any]] = []
    for kind, store in job_stores.items():
        all_jobs = getattr(store, "all", None)
        if not callable(all_jobs):
            continue
        try:
            for job_id, job in all_jobs(limit=limit):
                rows.append({"source": f"{kind}_job", "job_id": job_id, **job})
        except Exception:
            continue
    return rows[-limit:]

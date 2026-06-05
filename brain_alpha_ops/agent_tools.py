"""Whitelisted agent tool facade for Brain Alpha Ops.

This module is intentionally protocol-agnostic.  MCP, a web API, or a local
assistant can expose these same tool definitions without letting the model call
arbitrary Python code.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from brain_alpha_ops.agent_live_tools import (
    MAX_BATCH_SIMULATION_WORKERS,
    MAX_BATCH_SIMULATIONS,
    MAX_SYNC_RANGE,
    AgentLiveToolsMixin,
)
from brain_alpha_ops.agent_tool_errors import tool_error
from brain_alpha_ops.agent_tool_registry import resolve_tool_name, tool_definitions
from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.shared_bounds import (
    bounded_float,
    bounded_int,
    candidate_argument,
    required_text,
    truthy,
)
from brain_alpha_ops.agent_guidance_tools import (
    assistant_guidance_for_generator,
    assistant_guidance_summary,
    attach_assistant_guidance,
    guidance_sample_size,
    has_generator_bias,
    merge_generation_guidance,
)
from brain_alpha_ops.agent_research_tools import (
    assistant_response_guidance_tool,
    build_market_data_cache_tool,
    build_assistant_context_tool,
    build_assistant_request_tool,
    build_vectorized_market_data_from_args,
    collect_job_rows_with_diagnostics,
    cross_review_assistant_response_tool,
    orchestrate_parameter_search_from_args,
    plan_parallel_backtest_from_args,
    parse_assistant_response_tool,
    query_research_observability_snapshot,
    route_alert_from_args,
    run_anti_overfit_tool,
    run_rolling_validation_tool,
    search_parameters_tool,
    send_alert_tool,
)
from brain_alpha_ops.redaction import redact_data, redact_error_message
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    parse_assistant_response,
)
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.generator import CandidateGenerator, extract_fields, extract_operators
from brain_alpha_ops.research.guidance import ensure_assistant_guidance_digest
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.observability import actionable_duplicate_expression_records
from brain_alpha_ops.research.scoring import build_scorecard
from brain_alpha_ops.research.validated_generator import validate_expression as local_validate_expression
from brain_alpha_ops.runner import api_from_run_config
from brain_alpha_ops.tasks import JobStore


MAX_TOOL_CANDIDATES = 100

logger = logging.getLogger(__name__)


class BrainAlphaToolbox(AgentLiveToolsMixin):
    """A safe callable surface for LLM/agent integration."""

    def __init__(
        self,
        *,
        run_config: RunConfig | None = None,
        api: Any | None = None,
        job_stores: Mapping[str, JobStore] | None = None,
        allow_live_api: bool = False,
        allow_submit: bool = False,
        use_research_memory_guidance: bool = True,
    ):
        self.run_config = run_config or load_run_config()
        self.api = api
        self.job_stores = dict(job_stores or {})
        self.allow_live_api = bool(allow_live_api)
        self.allow_submit = bool(allow_submit)
        self.use_research_memory_guidance = bool(use_research_memory_guidance)
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "list_context": self._list_context,
            "generate_candidates": self._generate_candidates,
            "validate_expression": self._validate_expression,
            "score_candidate": self._score_candidate,
            "run_simulation": self._run_simulation,
            "run_simulation_batch": self._run_simulation_batch,
            "check_alpha": self._check_alpha,
            "submit_alpha": self._submit_alpha,
            "sync_cloud_alphas": self._sync_cloud_alphas,
            "get_job_status": self._get_job_status,
            "query_research_memory": self._query_research_memory,
            "query_expression_index": self._query_expression_index,
            "query_research_observability": self._query_research_observability,
            "build_market_data_cache": self._build_market_data_cache,
            "build_vectorized_market_data": self._build_vectorized_market_data,
            "search_parameters": self._search_parameters,
            "orchestrate_parameter_search": self._orchestrate_parameter_search,
            "plan_parallel_backtest": self._plan_parallel_backtest,
            "run_parallel_backtest": self._run_parallel_backtest,
            "send_alert": self._send_alert,
            "route_alert": self._route_alert,
            "build_assistant_context": self._build_assistant_context,
            "build_assistant_request": self._build_assistant_request,
            "parse_assistant_response": self._parse_assistant_response,
            "assistant_response_guidance": self._assistant_response_guidance,
            "run_anti_overfit": self._run_anti_overfit,
            "run_rolling_validation": self._run_rolling_validation,
            "cross_review_assistant_response": self._cross_review_assistant_response,
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.to_dict() for tool in tool_definitions()]

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        requested_name = str(name or "")
        resolved_name = resolve_tool_name(requested_name)
        handler = self._handlers.get(resolved_name)
        if not handler:
            return _tool_error(ValueError(f"unknown tool: {name}"), "TOOL_NOT_FOUND")
        try:
            payload = redact_data(handler(dict(arguments or {})))
            if isinstance(payload, dict) and resolved_name != requested_name:
                payload.setdefault("tool_alias", requested_name)
                payload.setdefault("canonical_tool", resolved_name)
            return payload
        except Exception as exc:
            return _tool_error(exc, "TOOL_ERROR", tool=requested_name, canonical_tool=resolved_name)

    def _list_context(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", "all") or "all")
        limit = bounded_int(args.get("limit", 20), 1, 200)
        fields: list[dict[str, Any]]
        operators: list[dict[str, Any]]
        datasets: list[dict[str, Any]]
        source = "official_loader"
        try:
            from brain_alpha_ops.data import OfficialDataLoader

            loader = OfficialDataLoader.instance()
            fields = [_field_to_dict(field) for field in loader.get_fields()]
            operators = [_operator_to_dict(operator) for operator in loader.get_operators()]
            datasets = [_dataset_to_dict(dataset) for dataset in loader.get_datasets()]
        except Exception:
            logger.warning("official context loader unavailable; using default agent context", exc_info=True)
            from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS, DEFAULT_OPERATORS

            source = "context_defaults"
            fields = [dict(field) for field in DEFAULT_FIELDS]
            operators = [{"name": str(operator)} for operator in DEFAULT_OPERATORS]
            datasets = []

        if query not in ("", "all"):
            lowered = query.lower()
            fields = [
                field for field in fields
                if lowered in str(field.get("id") or field.get("name") or "").lower()
                or lowered in str(field.get("category") or "").lower()
            ]
            operators = [
                op for op in operators
                if lowered in str(op.get("name") or op.get("id") or "").lower()
                or lowered in str(op.get("category") or op.get("op_type") or "").lower()
            ]
        return {
            "ok": True,
            "source": source,
            "fields_count": len(fields),
            "operators_count": len(operators),
            "datasets_count": len(datasets),
            "fields": fields[:limit],
            "operators": operators[:limit],
            "datasets": datasets[:limit],
        }

    def _generate_candidates(self, args: dict[str, Any]) -> dict[str, Any]:
        count = bounded_int(args.get("count", 10), 1, MAX_TOOL_CANDIDATES)
        dataset_id = str(args.get("dataset_id", "") or "")
        generator = CandidateGenerator()
        memory_guidance: dict[str, Any] = {}
        use_memory = self.use_research_memory_guidance and truthy(args.get("use_research_memory", True))
        if use_memory:
            memory_guidance = self._research_memory_guidance(args)
            if memory_guidance:
                if has_generator_bias(memory_guidance):
                    generator.set_experience_guidance(memory_guidance)

        assistant_guidance: dict[str, Any] | None = None
        assistant_guidance_applied = False
        try:
            assistant_guidance = self._assistant_generation_guidance(args)
        except AssistantResponseParseError as exc:
            return _tool_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR")

        if assistant_guidance:
            assistant_guidance = ensure_assistant_guidance_digest(assistant_guidance)
            assistant_generator_guidance = assistant_guidance_for_generator(assistant_guidance)
            if has_generator_bias(assistant_generator_guidance):
                if memory_guidance:
                    assistant_generator_guidance = merge_generation_guidance(
                        memory_guidance,
                        assistant_generator_guidance,
                    )
                generator.set_experience_guidance(assistant_generator_guidance)
                assistant_guidance_applied = True

        candidates = generator.generate(count, dataset_id=dataset_id)
        if assistant_guidance_applied and assistant_guidance:
            for candidate in candidates:
                attach_assistant_guidance(candidate, assistant_guidance)
        payload = {
            "ok": True,
            "count": len(candidates),
            "candidates": [candidate.to_dict() for candidate in candidates],
        }
        if assistant_guidance is not None:
            payload["assistant_guidance"] = assistant_guidance_summary(
                assistant_guidance,
                applied=assistant_guidance_applied,
            )
        return payload

    def _validate_expression(self, args: dict[str, Any]) -> dict[str, Any]:
        expression = required_text(args, "expression")
        result = {
            "ok": True,
            "expression": expression,
            "local": local_validate_expression(expression),
        }
        if args.get("use_api"):
            blocked = self._live_api_blocked(args, tool="validate_expression")
            if not blocked:
                blocked = self._duplicate_live_expression_block(expression, tool="validate_expression")
            if blocked:
                result["api"] = blocked
            else:
                api = self._api()
                api.authenticate()
                result["api"] = api.validate_expression(
                    expression,
                    self.run_config.ops.settings.to_platform_dict()["settings"],
                )
        return result

    def _score_candidate(self, args: dict[str, Any]) -> dict[str, Any]:
        expression = required_text(args, "expression")
        candidate = Candidate(
            alpha_id=str(args.get("alpha_id", "agent_candidate") or "agent_candidate"),
            expression=expression,
            family=str(args.get("family", "Agent") or "Agent"),
            hypothesis=str(args.get("hypothesis", "Agent supplied expression") or "Agent supplied expression"),
            data_fields=extract_fields(expression),
            operators=extract_operators(expression),
            official_metrics=dict(args.get("official_metrics") or {}),
        )
        scorecard = build_scorecard(candidate, self.run_config.ops.thresholds, self.run_config.ops.scoring)
        candidate.scorecard = scorecard
        return {"ok": True, "candidate": candidate.to_dict(), "scorecard": scorecard}

    def _get_job_status(self, args: dict[str, Any]) -> dict[str, Any]:
        kind = str(args.get("kind", "production") or "production")
        store = self.job_stores.get(kind)
        if not store:
            return {"ok": False, "error_code": "JOB_STORE_NOT_CONFIGURED", "kind": kind}
        job_id = str(args.get("job_id", "") or "")
        if job_id:
            job = store.get(job_id)
            return {"ok": bool(job), "job_id": job_id, **(job or {"error": "unknown job"})}
        latest = store.latest_active() or store.latest_any()
        if not latest:
            return {"ok": True, "job_id": "", "status": "idle"}
        latest_id, job = latest
        return {"ok": True, "job_id": latest_id, **job}

    def _query_research_memory(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = bounded_int(args.get("top_n", 10), 1, 50)
        persist = bool(args.get("persist"))
        memory = ResearchMemory(self.run_config.ops.storage_dir)
        summary = memory.summary(limit=limit, top_n=top_n)
        if persist:
            summary["written_to"] = str(memory.write_summary(limit=limit, top_n=top_n))
        return summary

    def _query_expression_index(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = bounded_int(args.get("top_n", 10), 1, 50)
        include_cloud = truthy(args.get("include_cloud", True))
        index = ExpressionHistoryIndex(self.run_config.ops.storage_dir)
        expression = str(args.get("expression") or "").strip()
        if expression:
            return index.lookup(
                expression,
                limit=limit,
                top_n=top_n,
                include_cloud=include_cloud,
                min_similarity=bounded_float(args.get("min_similarity", 0.75), 0.0, 1.0),
            )
        return index.summary(limit=limit, top_n=top_n, include_cloud=include_cloud)

    def _query_research_observability(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = bounded_int(args.get("top_n", 10), 1, 50)
        include_cloud = truthy(args.get("include_cloud", True))
        job_payload = collect_job_rows_with_diagnostics(self.job_stores, limit=min(limit, 1000))
        return query_research_observability_snapshot(
            self.run_config.ops.storage_dir,
            limit=limit,
            top_n=top_n,
            include_cloud=include_cloud,
            job_rows=job_payload["rows"],
            job_diagnostics=job_payload["diagnostics"],
        )

    def _build_market_data_cache(self, args: dict[str, Any]) -> dict[str, Any]:
        refresh = truthy(args.get("refresh", True))
        source_file = str(args.get("source_file", "") or "").strip()
        limit = bounded_int(args.get("limit", 5000), 1, 50000)
        return build_market_data_cache_tool(
            self.run_config.ops.storage_dir,
            refresh=refresh,
            source_file=source_file,
            limit=limit,
        )

    def _build_vectorized_market_data(self, args: dict[str, Any]) -> dict[str, Any]:
        return build_vectorized_market_data_from_args(self.run_config.ops.storage_dir, args)

    def _search_parameters(self, args: dict[str, Any]) -> dict[str, Any]:
        candidate = Candidate.from_dict(candidate_argument(args))
        max_mutations = bounded_int(args.get("max_mutations", 4), 1, 12)
        return search_parameters_tool(candidate, max_mutations=max_mutations)

    def _orchestrate_parameter_search(self, args: dict[str, Any]) -> dict[str, Any]:
        return orchestrate_parameter_search_from_args(args)

    def _plan_parallel_backtest(self, args: dict[str, Any]) -> dict[str, Any]:
        return plan_parallel_backtest_from_args(args)

    def _send_alert(self, args: dict[str, Any]) -> dict[str, Any]:
        title = required_text(args, "title")
        message = required_text(args, "message")
        severity = str(args.get("severity", "info") or "info").strip() or "info"
        channel = str(args.get("channel", "local") or "local").strip() or "local"
        webhook_url = str(args.get("webhook_url", "") or "").strip()
        metadata = dict(args.get("metadata") or {})
        return send_alert_tool(
            self.run_config.ops.storage_dir,
            title=title,
            message=message,
            severity=severity,
            channel=channel,
            webhook_url=webhook_url,
            metadata=metadata,
        )

    def _route_alert(self, args: dict[str, Any]) -> dict[str, Any]:
        return route_alert_from_args(self.run_config.ops.storage_dir, args)

    def _build_assistant_context(self, args: dict[str, Any]) -> dict[str, Any]:
        return build_assistant_context_tool(self.run_config, args)

    def _build_assistant_request(self, args: dict[str, Any]) -> dict[str, Any]:
        return build_assistant_request_tool(self.run_config, args)

    def _parse_assistant_response(self, args: dict[str, Any]) -> dict[str, Any]:
        return parse_assistant_response_tool(args)

    def _assistant_response_guidance(self, args: dict[str, Any]) -> dict[str, Any]:
        return assistant_response_guidance_tool(args)

    def _run_anti_overfit(self, args: dict[str, Any]) -> dict[str, Any]:
        return run_anti_overfit_tool(args)

    def _run_rolling_validation(self, args: dict[str, Any]) -> dict[str, Any]:
        return run_rolling_validation_tool(args)

    def _cross_review_assistant_response(self, args: dict[str, Any]) -> dict[str, Any]:
        return cross_review_assistant_response_tool(args)

    def _assistant_generation_guidance(self, args: dict[str, Any]) -> dict[str, Any] | None:
        min_confidence = bounded_float(args.get("assistant_min_confidence", 0.0), 0.0, 1.0)
        supplied_guidance = args.get("assistant_guidance")
        if isinstance(supplied_guidance, dict):
            guidance = dict(supplied_guidance)
            guidance.setdefault("ok", True)
            guidance.setdefault("source", "assistant_guidance_argument")
            guidance.setdefault("min_confidence", min_confidence)
            guidance.setdefault("sample_size", guidance_sample_size(guidance))
            guidance = ensure_assistant_guidance_digest(guidance)
            confidence = guidance.get("confidence")
            confidence_ok = True
            if confidence is not None:
                confidence_ok = bounded_float(confidence, 0.0, 1.0) >= min_confidence
            guidance["usable"] = truthy(guidance.get("usable", True)) and confidence_ok
            return guidance

        raw_output = args.get("assistant_response") or args.get("assistant_raw_output")
        if raw_output is None or not str(raw_output).strip():
            return None
        response = parse_assistant_response(str(raw_output))
        return assistant_response_to_generation_guidance(response, min_confidence=min_confidence)

    def _research_memory_guidance(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(args or {})
        limit = bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = bounded_int(args.get("top_n", 10), 1, 50)
        min_success_rate = float(args.get("min_success_rate", 0.0) or 0.0)
        memory = ResearchMemory(self.run_config.ops.storage_dir)
        try:
            return memory.generation_guidance(limit=limit, top_n=top_n, min_success_rate=min_success_rate)
        except Exception:
            logger.warning("research memory guidance unavailable; using empty guidance", exc_info=True)
            return {}

    def _api(self):
        if self.api is not None:
            return self.api
        return api_from_run_config(self.run_config)

    def _live_api_blocked(self, args: dict[str, Any], *, tool: str) -> dict[str, Any] | None:
        if not self.allow_live_api or not bool(args.get("confirm_live_api")):
            return {
                "ok": False,
                "error_code": "LIVE_API_NOT_ALLOWED",
                "tool": tool,
                "environment": "production",
                "error": f"{tool} requires allow_live_api=True and confirm_live_api=True",
            }
        return None

    def _duplicate_live_expression_block(self, expression: str, *, tool: str) -> dict[str, Any] | None:
        if not str(expression or "").strip():
            return None
        try:
            lookup = ExpressionHistoryIndex(self.run_config.ops.storage_dir).lookup(
                expression,
                limit=5000,
                top_n=10,
                include_cloud=True,
            )
        except Exception as exc:
            return {
                "ok": False,
                "error_code": "OBSERVABILITY_DUPLICATE_PREFLIGHT_UNAVAILABLE",
                "tool": tool,
                "error": "observability duplicate-expression preflight failed; live API call was not attempted",
                "expression_canonical": expression_key(expression),
                "detail": redact_error_message(exc, max_length=180),
            }
        exact_records = [row for row in lookup.get("exact_records") or [] if isinstance(row, dict)]
        actionable_records = actionable_duplicate_expression_records(exact_records, expression)
        if not actionable_records:
            return None
        return {
            "ok": False,
            "error_code": "OBSERVABILITY_DUPLICATE_EXPRESSION_BLOCKED",
            "tool": tool,
            "error": "observability duplicate expression history blocked live API call",
            "expression_canonical": lookup.get("expression_canonical") or expression_key(expression),
            "exact_count": lookup.get("exact_count", len(exact_records)),
            "matching_records": actionable_records[:5],
        }

def _tool_error(exc: Exception, error_code: str, **context: Any) -> dict[str, Any]:
    return tool_error(exc, error_code=error_code, **context)


def _field_to_dict(field: Any) -> dict[str, Any]:
    return {
        "id": getattr(field, "id", ""),
        "name": getattr(field, "name", ""),
        "category": getattr(field, "category", ""),
        "type": getattr(field, "type", ""),
        "dataset_id": getattr(getattr(field, "dataset", None), "id", ""),
        "coverage": getattr(field, "coverage", None),
    }


def _operator_to_dict(operator: Any) -> dict[str, Any]:
    return {
        "id": getattr(operator, "id", ""),
        "name": getattr(operator, "name", ""),
        "category": getattr(operator, "category", getattr(operator, "op_type", "")),
        "arity": getattr(operator, "arity", None),
    }


def _dataset_to_dict(dataset: Any) -> dict[str, Any]:
    return {
        "id": getattr(dataset, "id", ""),
        "name": getattr(dataset, "name", ""),
        "category": getattr(dataset, "category", ""),
        "field_count": getattr(dataset, "field_count", None),
    }

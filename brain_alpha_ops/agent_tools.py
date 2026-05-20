"""Whitelisted agent tool facade for Brain Alpha Ops.

This module is intentionally protocol-agnostic.  MCP, a web API, or a local
assistant can expose these same tool definitions without letting the model call
arbitrary Python code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

from brain_alpha_ops.brain_api import MockBrainAPI
from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.error_payloads import user_error_payload
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.redaction import redact_data, redact_error_message
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    build_assistant_request_pack,
    parse_assistant_response,
)
from brain_alpha_ops.research.anti_overfit import AntiOverfitService
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.generator import CandidateGenerator, extract_fields, extract_operators
from brain_alpha_ops.research.guidance import assistant_guidance_candidate_metadata, ensure_assistant_guidance_digest
from brain_alpha_ops.research.llm_review import cross_review_assistant_response
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.observability import (
    actionable_duplicate_expression_records,
    build_research_observability_snapshot,
)
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.research.scoring import build_scorecard
from brain_alpha_ops.research.rolling_validation import RollingValidationService
from brain_alpha_ops.research.validated_generator import validate_expression as local_validate_expression
from brain_alpha_ops.runner import api_from_run_config
from brain_alpha_ops.tasks import JobStore


MAX_TOOL_CANDIDATES = 100
MAX_SYNC_RANGE = {"1d", "3d", "7d", "all"}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    live_api: bool = False
    destructive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BrainAlphaToolbox:
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
            "check_alpha": self._check_alpha,
            "submit_alpha": self._submit_alpha,
            "sync_cloud_alphas": self._sync_cloud_alphas,
            "get_job_status": self._get_job_status,
            "query_research_memory": self._query_research_memory,
            "query_expression_index": self._query_expression_index,
            "query_research_observability": self._query_research_observability,
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
        handler = self._handlers.get(str(name or ""))
        if not handler:
            return _tool_error(ValueError(f"unknown tool: {name}"), "TOOL_NOT_FOUND")
        try:
            return redact_data(handler(dict(arguments or {})))
        except Exception as exc:
            return _tool_error(exc, "TOOL_ERROR", tool=str(name or ""))

    def _list_context(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", "all") or "all")
        limit = _bounded_int(args.get("limit", 20), 1, 200)
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
        count = _bounded_int(args.get("count", 10), 1, MAX_TOOL_CANDIDATES)
        dataset_id = str(args.get("dataset_id", "") or "")
        generator = CandidateGenerator()
        memory_guidance: dict[str, Any] = {}
        use_memory = self.use_research_memory_guidance and _truthy(args.get("use_research_memory", True))
        if use_memory:
            memory_guidance = self._research_memory_guidance(args)
            if memory_guidance:
                if _has_generator_bias(memory_guidance):
                    generator.set_experience_guidance(memory_guidance)

        assistant_guidance: dict[str, Any] | None = None
        assistant_guidance_applied = False
        try:
            assistant_guidance = self._assistant_generation_guidance(args)
        except AssistantResponseParseError as exc:
            return _tool_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR")

        if assistant_guidance:
            assistant_guidance = ensure_assistant_guidance_digest(assistant_guidance)
            assistant_generator_guidance = _assistant_guidance_for_generator(assistant_guidance)
            if _has_generator_bias(assistant_generator_guidance):
                if memory_guidance:
                    assistant_generator_guidance = _merge_generation_guidance(
                        memory_guidance,
                        assistant_generator_guidance,
                    )
                generator.set_experience_guidance(assistant_generator_guidance)
                assistant_guidance_applied = True

        candidates = generator.generate(count, dataset_id=dataset_id)
        if assistant_guidance_applied and assistant_guidance:
            for candidate in candidates:
                _attach_assistant_guidance(candidate, assistant_guidance)
        payload = {
            "ok": True,
            "count": len(candidates),
            "candidates": [candidate.to_dict() for candidate in candidates],
        }
        if assistant_guidance is not None:
            payload["assistant_guidance"] = _assistant_guidance_summary(
                assistant_guidance,
                applied=assistant_guidance_applied,
            )
        return payload

    def _validate_expression(self, args: dict[str, Any]) -> dict[str, Any]:
        expression = _required_text(args, "expression")
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
        expression = _required_text(args, "expression")
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
        return {"ok": True, "candidate": candidate.to_dict(), "scorecard": scorecard}

    def _run_simulation(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = self._live_api_blocked(args, tool="run_simulation")
        if blocked:
            return blocked
        expression = _required_text(args, "expression")
        blocked = self._duplicate_live_expression_block(expression, tool="run_simulation")
        if blocked:
            return blocked
        api = self._api()
        api.authenticate()
        validation = api.validate_expression(
            expression,
            self.run_config.ops.settings.to_platform_dict()["settings"],
        )
        if str(validation.get("status", "")).upper() not in {"PASS", "PASSED", "OK"}:
            return {"ok": False, "error_code": "VALIDATION_FAILED", "validation": validation}
        simulation_id = api.submit_simulation(
            expression,
            self.run_config.ops.settings.to_platform_dict()["settings"],
        )
        max_polls = _bounded_int(args.get("max_polls", 5), 1, 20)
        status = ""
        for _ in range(max_polls):
            status = str(api.poll_simulation(simulation_id))
            if status.upper() in {"COMPLETED", "FAILED", "ERROR"}:
                break
        payload = {"ok": True, "simulation_id": simulation_id, "status": status}
        if status.upper() == "COMPLETED":
            payload["result"] = api.fetch_result(simulation_id)
        return payload

    def _check_alpha(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = self._live_api_blocked(args, tool="check_alpha")
        if blocked:
            return blocked
        alpha_id = _required_text(args, "alpha_id")
        api = self._api()
        api.authenticate()
        return {"ok": True, "alpha_id": alpha_id, "check": api.check_alpha(alpha_id)}

    def _submit_alpha(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_submit or not bool(args.get("confirm_submit")):
            return {
                "ok": False,
                "error_code": "SUBMIT_NOT_ALLOWED",
                "error": "submit_alpha requires allow_submit=True and confirm_submit=True",
            }
        blocked = self._live_api_blocked(args, tool="submit_alpha")
        if blocked:
            return blocked
        alpha_id = _required_text(args, "alpha_id")
        expression = _required_text(args, "expression")
        api = self._api()
        api.authenticate()
        check = api.check_alpha(alpha_id)
        if str(check.get("status", "")).upper() not in {"PASS", "PASSED"}:
            return {"ok": False, "error_code": "PRE_SUBMIT_CHECK_FAILED", "check": check}
        result = api.submit_alpha(
            alpha_id,
            expression,
            self.run_config.ops.settings.to_platform_dict()["settings"],
        )
        return {"ok": True, "alpha_id": alpha_id, "submission": result, "pre_submit_check": check}

    def _sync_cloud_alphas(self, args: dict[str, Any]) -> dict[str, Any]:
        blocked = self._live_api_blocked(args, tool="sync_cloud_alphas")
        if blocked:
            return blocked
        sync_range = str(args.get("sync_range", self.run_config.ops.budget.cloud_sync_range) or "3d")
        if sync_range not in MAX_SYNC_RANGE:
            sync_range = "3d"
        api = self._api()
        api.authenticate()
        rows = api.list_user_alphas(sync_range)
        merge_stats = ResearchRepository(self.run_config.ops.storage_dir).merge_cloud_alphas(
            rows,
            sync_range=sync_range,
        )
        return {
            "ok": True,
            "range": sync_range,
            "count": len(rows),
            "merge": merge_stats,
            "alphas": rows[: _bounded_int(args.get("limit", 20), 1, 200)],
        }

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
        limit = _bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = _bounded_int(args.get("top_n", 10), 1, 50)
        persist = bool(args.get("persist"))
        memory = ResearchMemory(self.run_config.ops.storage_dir)
        summary = memory.summary(limit=limit, top_n=top_n)
        if persist:
            summary["written_to"] = str(memory.write_summary(limit=limit, top_n=top_n))
        return summary

    def _query_expression_index(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = _bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = _bounded_int(args.get("top_n", 10), 1, 50)
        include_cloud = _truthy(args.get("include_cloud", True))
        index = ExpressionHistoryIndex(self.run_config.ops.storage_dir)
        expression = str(args.get("expression") or "").strip()
        if expression:
            return index.lookup(
                expression,
                limit=limit,
                top_n=top_n,
                include_cloud=include_cloud,
                min_similarity=_bounded_float(args.get("min_similarity", 0.75), 0.0, 1.0),
            )
        return index.summary(limit=limit, top_n=top_n, include_cloud=include_cloud)

    def _query_research_observability(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = _bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = _bounded_int(args.get("top_n", 10), 1, 50)
        include_cloud = _truthy(args.get("include_cloud", True))
        return build_research_observability_snapshot(
            self.run_config.ops.storage_dir,
            limit=limit,
            top_n=top_n,
            include_cloud=include_cloud,
            job_rows=self._tool_job_rows(limit=min(limit, 1000)),
        )

    def _build_assistant_context(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = _bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = _bounded_int(args.get("top_n", 10), 1, 50)
        include_prompt = _truthy(args.get("include_prompt", True))
        return build_assistant_context_pack(
            self.run_config,
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
        )

    def _build_assistant_request(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = _bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = _bounded_int(args.get("top_n", 10), 1, 50)
        include_prompt = _truthy(args.get("include_prompt", True))
        include_draft = _truthy(args.get("include_offline_draft", True))
        context = build_assistant_context_pack(
            self.run_config,
            limit=limit,
            top_n=top_n,
            include_prompt=True,
        )
        return build_assistant_request_pack(
            context,
            include_prompt=include_prompt,
            include_offline_draft=include_draft,
        )

    def _tool_job_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for kind, store in self.job_stores.items():
            all_jobs = getattr(store, "all", None)
            if not callable(all_jobs):
                continue
            try:
                for job_id, job in all_jobs(limit=limit):
                    rows.append({"source": f"{kind}_job", "job_id": job_id, **job})
            except Exception:
                continue
        return rows[-limit:]

    def _parse_assistant_response(self, args: dict[str, Any]) -> dict[str, Any]:
        raw_output = str(args.get("raw_output") or args.get("text") or "")
        try:
            return parse_assistant_response(raw_output)
        except AssistantResponseParseError as exc:
            return _tool_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR")

    def _assistant_response_guidance(self, args: dict[str, Any]) -> dict[str, Any]:
        raw_output = str(args.get("raw_output") or args.get("text") or "")
        min_confidence = _bounded_float(args.get("min_confidence", 0.0), 0.0, 1.0)
        try:
            response = parse_assistant_response(raw_output)
            return assistant_response_to_generation_guidance(response, min_confidence=min_confidence)
        except AssistantResponseParseError as exc:
            return _tool_error(exc, "ASSISTANT_RESPONSE_PARSE_ERROR")

    def _run_anti_overfit(self, args: dict[str, Any]) -> dict[str, Any]:
        candidate = _candidate_argument(args)
        return AntiOverfitService().evaluate(candidate)

    def _run_rolling_validation(self, args: dict[str, Any]) -> dict[str, Any]:
        candidate = _candidate_argument(args)
        windows = _bounded_int(args.get("windows", 4), 2, 20)
        return RollingValidationService().evaluate(candidate, windows=windows)

    def _cross_review_assistant_response(self, args: dict[str, Any]) -> dict[str, Any]:
        request_pack = args.get("request_pack")
        if not isinstance(request_pack, dict):
            return _tool_error(ValueError("request_pack must be an object"), "INVALID_REQUEST_PACK")
        primary = args.get("primary_response") or args.get("primary")
        reviewer = args.get("reviewer_response") or args.get("reviewer")
        try:
            return cross_review_assistant_response(
                request_pack,
                primary if primary is not None else "",
                reviewer_response=reviewer,
                min_confidence=_bounded_float(args.get("min_confidence", 0.6), 0.0, 1.0),
            )
        except AssistantResponseParseError as exc:
            return _tool_error(exc, "ASSISTANT_CROSS_REVIEW_PARSE_ERROR")

    def _assistant_generation_guidance(self, args: dict[str, Any]) -> dict[str, Any] | None:
        min_confidence = _bounded_float(args.get("assistant_min_confidence", 0.0), 0.0, 1.0)
        supplied_guidance = args.get("assistant_guidance")
        if isinstance(supplied_guidance, dict):
            guidance = dict(supplied_guidance)
            guidance.setdefault("ok", True)
            guidance.setdefault("source", "assistant_guidance_argument")
            guidance.setdefault("min_confidence", min_confidence)
            guidance.setdefault("sample_size", _guidance_sample_size(guidance))
            guidance = ensure_assistant_guidance_digest(guidance)
            confidence = guidance.get("confidence")
            confidence_ok = True
            if confidence is not None:
                confidence_ok = _bounded_float(confidence, 0.0, 1.0) >= min_confidence
            guidance["usable"] = _truthy(guidance.get("usable", True)) and confidence_ok
            return guidance

        raw_output = args.get("assistant_response") or args.get("assistant_raw_output")
        if raw_output is None or not str(raw_output).strip():
            return None
        response = parse_assistant_response(str(raw_output))
        return assistant_response_to_generation_guidance(response, min_confidence=min_confidence)

    def _research_memory_guidance(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(args or {})
        limit = _bounded_int(args.get("limit", 5000), 1, 50000)
        top_n = _bounded_int(args.get("top_n", 10), 1, 50)
        min_success_rate = float(args.get("min_success_rate", 0.0) or 0.0)
        memory = ResearchMemory(self.run_config.ops.storage_dir)
        try:
            return memory.generation_guidance(limit=limit, top_n=top_n, min_success_rate=min_success_rate)
        except Exception:
            return {}

    def _api(self):
        if self.api is not None:
            return self.api
        if str(self.run_config.environment).lower() == "mock":
            return MockBrainAPI()
        return api_from_run_config(self.run_config)

    def _live_api_blocked(self, args: dict[str, Any], *, tool: str) -> dict[str, Any] | None:
        environment = str(self.run_config.environment).lower()
        if environment == "mock":
            return None
        if not self.allow_live_api or not bool(args.get("confirm_live_api")):
            return {
                "ok": False,
                "error_code": "LIVE_API_NOT_ALLOWED",
                "tool": tool,
                "environment": environment,
                "error": f"{tool} requires allow_live_api=True and confirm_live_api=True outside mock mode",
            }
        return None

    def _duplicate_live_expression_block(self, expression: str, *, tool: str) -> dict[str, Any] | None:
        if str(self.run_config.environment).lower() == "mock":
            return None
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


def tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            "list_context",
            "List local official fields, operators, and datasets available to the research engine.",
            _schema({"query": "string", "limit": "integer"}),
        ),
        ToolDefinition(
            "generate_candidates",
            "Generate candidate FASTEXPR alpha expressions without calling the official API; local research memory guidance is enabled by default and optional assistant guidance can bias the local generator.",
            _schema({
                "count": "integer",
                "dataset_id": "string",
                "use_research_memory": "boolean",
                "top_n": "integer",
                "min_success_rate": "number",
                "assistant_response": "string",
                "assistant_raw_output": "string",
                "assistant_guidance": "object",
                "assistant_min_confidence": "number",
            }),
        ),
        ToolDefinition(
            "validate_expression",
            "Validate a FASTEXPR expression locally, optionally with the configured BRAIN API.",
            _schema({"expression": "string", "use_api": "boolean", "confirm_live_api": "boolean"}),
            live_api=True,
        ),
        ToolDefinition(
            "score_candidate",
            "Compute local scorecard and gate-oriented diagnostics for one expression.",
            _schema({"expression": "string", "family": "string", "hypothesis": "string", "official_metrics": "object"}),
        ),
        ToolDefinition(
            "run_simulation",
            "Submit one expression to the configured simulation API and fetch the result when completed.",
            _schema({"expression": "string", "max_polls": "integer", "confirm_live_api": "boolean"}),
            live_api=True,
        ),
        ToolDefinition(
            "check_alpha",
            "Run the configured alpha check for an official alpha id.",
            _schema({"alpha_id": "string", "confirm_live_api": "boolean"}),
            live_api=True,
        ),
        ToolDefinition(
            "submit_alpha",
            "Submit an official alpha after pre-submit check and explicit confirmation.",
            _schema({"alpha_id": "string", "expression": "string", "confirm_live_api": "boolean", "confirm_submit": "boolean"}),
            live_api=True,
            destructive=True,
        ),
        ToolDefinition(
            "sync_cloud_alphas",
            "Sync user cloud alphas into the local research repository.",
            _schema({"sync_range": "string", "limit": "integer", "confirm_live_api": "boolean"}),
            live_api=True,
        ),
        ToolDefinition(
            "get_job_status",
            "Read status from a configured task store.",
            _schema({"kind": "string", "job_id": "string"}),
        ),
        ToolDefinition(
            "query_research_memory",
            "Summarize local research memory: fields, operators, failures, hypotheses, and lineage.",
            _schema({"limit": "integer", "top_n": "integer", "persist": "boolean"}),
        ),
        ToolDefinition(
            "query_expression_index",
            "Summarize or look up persisted FASTEXPR history by canonical fingerprint and semantic similarity.",
            _schema({"expression": "string", "limit": "integer", "top_n": "integer", "include_cloud": "boolean", "min_similarity": "number"}),
        ),
        ToolDefinition(
            "query_research_observability",
            "Summarize local research health: expression reuse, backtest failures, retryable errors, official-call guard blocks, and JSONL/cache status.",
            _schema({"limit": "integer", "top_n": "integer", "include_cloud": "boolean"}),
        ),
        ToolDefinition(
            "build_assistant_context",
            "Build an LLM-ready context pack from run config, latest local results, cloud cache, and research memory guidance.",
            _schema({"limit": "integer", "top_n": "integer", "include_prompt": "boolean"}),
        ),
        ToolDefinition(
            "build_assistant_request",
            "Build a provider-neutral LLM request envelope with response schema and offline fallback draft.",
            _schema({"limit": "integer", "top_n": "integer", "include_prompt": "boolean", "include_offline_draft": "boolean"}),
        ),
        ToolDefinition(
            "parse_assistant_response",
            "Parse and normalize a JSON response returned by an external assistant model.",
            _schema({"raw_output": "string"}),
        ),
        ToolDefinition(
            "assistant_response_guidance",
            "Convert an assistant model response into generator-ready fields, operators, windows, and operational flags.",
            _schema({"raw_output": "string", "min_confidence": "number"}),
        ),
        ToolDefinition(
            "run_anti_overfit",
            "Run deterministic anti-overfit checks for a candidate payload.",
            _schema({"candidate": "object"}, required=["candidate"]),
        ),
        ToolDefinition(
            "run_rolling_validation",
            "Run rolling validation checks for a candidate payload.",
            _schema({"candidate": "object", "windows": "integer"}, required=["candidate"]),
        ),
        ToolDefinition(
            "cross_review_assistant_response",
            "Cross-review a primary assistant response against an assistant request pack.",
            _schema(
                {"request_pack": "object", "primary_response": "string", "reviewer_response": "string", "min_confidence": "number"},
                required=["request_pack", "primary_response"],
            ),
        ),
    ]


def _schema(properties: dict[str, str], *, required: list[str] | None = None) -> dict[str, Any]:
    required_names = required if required is not None else [name for name in properties if name in {"expression", "alpha_id", "raw_output"}]
    return {
        "type": "object",
        "properties": {name: {"type": kind} for name, kind in properties.items()},
        "required": required_names,
        "additionalProperties": False,
    }


def _tool_error(exc: Exception, error_code: str, **context: Any) -> dict[str, Any]:
    return user_error_payload(exc, error_code=error_code, **context)


def _bounded_int(value: Any, lower: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = lower
    return min(max(parsed, lower), upper)


def _bounded_float(value: Any, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = lower
    return min(max(parsed, lower), upper)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _required_text(args: dict[str, Any], key: str) -> str:
    value = str(args.get(key, "") or "").strip()
    if not value:
        raise ValueError(f"missing required argument: {key}")
    return value


def _candidate_argument(args: dict[str, Any]) -> dict[str, Any]:
    candidate = args.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    expression = _required_text(args, "expression")
    return {
        "alpha_id": str(args.get("alpha_id", "agent_candidate") or "agent_candidate"),
        "expression": expression,
        "family": str(args.get("family", "Agent") or "Agent"),
        "hypothesis": str(args.get("hypothesis", "Agent supplied expression") or "Agent supplied expression"),
        "official_metrics": dict(args.get("official_metrics") or {}),
        "submission": dict(args.get("submission") or {}),
    }


def _has_generator_bias(guidance: dict[str, Any] | None) -> bool:
    if not guidance:
        return False
    return bool(
        guidance.get("top_operators")
        or guidance.get("preferred_windows")
        or guidance.get("field_combinations")
    )


def _assistant_guidance_for_generator(guidance: dict[str, Any]) -> dict[str, Any]:
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


def _merge_generation_guidance(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = {
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
    return merged


def _assistant_guidance_summary(guidance: dict[str, Any], *, applied: bool) -> dict[str, Any]:
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


def _attach_assistant_guidance(candidate: Candidate, guidance: dict[str, Any]) -> None:
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


def _guidance_sample_size(guidance: dict[str, Any]) -> int:
    return max(
        len(_text_items(guidance.get("top_fields"))),
        len(_text_items(guidance.get("top_operators"))),
        len(_number_items(guidance.get("preferred_windows"))),
        len(_field_combinations(guidance.get("field_combinations"))),
    )


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

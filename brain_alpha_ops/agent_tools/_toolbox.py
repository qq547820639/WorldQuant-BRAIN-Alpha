"""``BrainAlphaToolbox`` core: routing, handler registry, live-API gating.

The toolbox is the safe callable surface for LLM/agent integration.  It
resolves tool names, delegates to handler methods (some inherited from
mixins), redacts results, and gates live BRAIN API calls behind a dual
confirm/allow mechanism.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Mapping

from brain_alpha_ops.agent_live_tools import (
    AgentLiveToolsMixin,
)
from brain_alpha_ops.agent_tool_registry import resolve_tool_name, tool_definitions
from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.redaction import redact_data, redact_error_message
from brain_alpha_ops.research.expression_ast import expression_key
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.observability import (
    actionable_duplicate_expression_records,
)
from brain_alpha_ops.runner import api_from_run_config
from brain_alpha_ops.tasks import JobStore

from ._alert_assistant_mixin import _AlertAssistantToolsMixin
from ._context_mixin import _ContextToolsMixin
from ._helpers import _tool_error
from ._research_mixin import _ResearchToolsMixin

logger = logging.getLogger("brain_alpha_ops.agent_tools")


class BrainAlphaToolbox(AgentLiveToolsMixin, _ContextToolsMixin, _ResearchToolsMixin, _AlertAssistantToolsMixin):
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

    def _api(self):
        if self.api is not None:
            return self.api
        return api_from_run_config(self.run_config)

    def _live_api_blocked(self, args: dict[str, Any], *, tool: str) -> dict[str, Any] | None:
        if not self.allow_live_api or not bool(args.get("confirm_live_api")):
            # P3-31 fix: explain the dual-gate mechanism clearly so that
            # agent users understand *which* condition is missing.
            _block_reasons = []
            if not self.allow_live_api:
                _block_reasons.append("server started without --allow-live-api")
            if not bool(args.get("confirm_live_api")):
                _block_reasons.append("caller did not set confirm_live_api=True")
            return {
                "ok": False,
                "error_code": "LIVE_API_NOT_ALLOWED",
                "tool": tool,
                "environment": "production",
                "error": f"{tool} blocked: " + "; ".join(_block_reasons) + ". "
                    "Set allow_live_api=True on the toolbox and confirm_live_api=True in the call arguments.",
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

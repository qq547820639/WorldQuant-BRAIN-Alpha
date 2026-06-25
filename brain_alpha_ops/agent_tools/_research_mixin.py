"""Mixin: research memory, expression index, observability, market data, and
parameter search handlers.

These handlers query local research artifacts (memory, expression index,
observability snapshots, market-data cache) and orchestrate parameter
search / parallel backtest planning.  Like ``_ContextToolsMixin``, this
mixin is stateless and relies on ``BrainAlphaToolbox.__init__`` attributes.
"""
from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.agent_research_tools import (
    build_market_data_cache_tool,
    build_vectorized_market_data_from_args,
    collect_job_rows_with_diagnostics,
    orchestrate_parameter_search_from_args,
    plan_parallel_backtest_from_args,
    query_research_observability_snapshot,
    search_parameters_tool,
)
from brain_alpha_ops.agent_guidance_tools import guidance_sample_size
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.assistant import (
    assistant_response_to_generation_guidance,
    parse_assistant_response,
)
from brain_alpha_ops.research.expression_index import ExpressionHistoryIndex
from brain_alpha_ops.research.guidance import ensure_assistant_guidance_digest
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.shared_bounds import (
    bounded_float,
    bounded_int,
    candidate_argument,
    truthy,
)

logger = logging.getLogger("brain_alpha_ops.agent_tools")


class _ResearchToolsMixin:
    """Handlers for research memory, expression index, and parameter search."""

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
        raw_limit = args.get("limit")
        limit = None if raw_limit in (None, "") else bounded_int(raw_limit, 1, 50000)
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
        except Exception as exc:
            logger.warning("research memory guidance unavailable; using empty guidance", exc_info=True)
            return {}

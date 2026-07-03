"""Mixin: context listing, candidate generation, validation, scoring, job status.

These handlers are split out of ``BrainAlphaToolbox`` to keep the class
focused on routing and live-API gating.  The mixin is stateless: it relies
only on attributes that ``BrainAlphaToolbox.__init__`` sets up
(``run_config``, ``job_stores``, ``use_research_memory_guidance``, etc.).
"""
from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.agent_research_tools import (
    assistant_guidance_for_generator,
    assistant_guidance_summary,
    attach_assistant_guidance,
    guidance_sample_size,
    has_generator_bias,
    merge_generation_guidance,
)
from brain_alpha_ops.models import Candidate
from brain_alpha_ops.research.assistant import AssistantResponseParseError
from brain_alpha_ops.research.generator import (
    CandidateGenerator,
    extract_fields,
    extract_operators,
)
from brain_alpha_ops.research.guidance import ensure_assistant_guidance_digest
from brain_alpha_ops.research.scoring import build_scorecard
from brain_alpha_ops.research.validated_generator import (
    validate_expression as local_validate_expression,
)
from brain_alpha_ops.shared_bounds import (
    bounded_int,
    required_text,
    truthy,
)

from ._helpers import (
    MAX_TOOL_CANDIDATES,
    _dataset_to_dict,
    _field_to_dict,
    _operator_to_dict,
    _tool_error,
)

logger = logging.getLogger("brain_alpha_ops.agent_tools")


class _ContextToolsMixin:
    """Handlers for context listing, candidate generation, and scoring."""

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
        except Exception as exc:
            logger.warning("official context loader unavailable; using default agent context", exc_info=True)
            from brain_alpha_ops.brain_api.context_defaults import (
                DEFAULT_FIELDS,
                DEFAULT_OPERATORS,
            )

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
        knowledge_constraints: dict[str, Any] = {}
        preferred_fields = [str(item).lower() for item in (args.get("preferred_fields") or []) if str(item)]
        preferred_operators = [str(item).lower() for item in (args.get("preferred_operators") or []) if str(item)]
        if preferred_fields:
            knowledge_constraints["preferred_fields"] = preferred_fields
            if truthy(args.get("strict_preferred_fields", False)):
                knowledge_constraints["strict_preferred_fields"] = True
        if preferred_operators:
            knowledge_constraints["preferred_operators"] = preferred_operators
            if truthy(args.get("strict_preferred_operators", False)):
                knowledge_constraints["strict_preferred_operators"] = True
        if knowledge_constraints:
            generator.set_knowledge_constraints(knowledge_constraints)
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

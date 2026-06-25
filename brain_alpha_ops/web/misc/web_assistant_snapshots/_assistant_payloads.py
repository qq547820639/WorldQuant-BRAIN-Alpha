"""Assistant context/request snapshots and response/guidance payloads."""
from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    build_assistant_request_pack,
    parse_assistant_response,
)
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.guidance import ensure_assistant_guidance_digest
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.repository import ResearchRepository

from ._helpers import (
    BoundedFloat,
    LoadConfig,
    PayloadTruthy,
    RunConfigFromPayload,
    Snapshot,
    WebError,
    _bounded_float,
    _default_web_error,
    _payload_truthy,
)


def assistant_context_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_sensitive: bool = False,
    load_config: LoadConfig,
    latest_result_snapshot: Snapshot,
    cloud_alpha_snapshot: Snapshot,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        memory = ResearchMemory(config.ops.storage_dir)
        memory_summary = memory.summary(limit=limit, top_n=top_n)
        memory_guidance = memory.generation_guidance(limit=limit, top_n=top_n, summary=memory_summary)
        latest = latest_result_snapshot()
        cloud = cloud_alpha_snapshot()
        return build_assistant_context_pack(
            config,
            latest_result_snapshot=latest,
            cloud_alpha_snapshot=cloud,
            memory_summary=memory_summary,
            memory_guidance=memory_guidance,
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
        )
    except Exception as exc:
        return web_error(exc, "ASSISTANT_CONTEXT_ERROR")


def assistant_request_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_offline_draft: bool = True,
    include_sensitive: bool = False,
    assistant_context_snapshot: Snapshot,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        context = assistant_context_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=True,
            include_sensitive=include_sensitive,
        )
        if context.get("ok") is False:
            return context
        return build_assistant_request_pack(
            context,
            include_prompt=include_prompt,
            include_offline_draft=include_offline_draft,
        )
    except Exception as exc:
        return web_error(exc, "ASSISTANT_REQUEST_ERROR")


def assistant_response_parse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_output = str((payload or {}).get("raw_output") or (payload or {}).get("text") or "")
    if not raw_output.strip():
        raise AssistantResponseParseError("assistant response is empty")
    return parse_assistant_response(raw_output)


def assistant_response_guidance_payload(
    payload: dict[str, Any],
    *,
    bounded_query_float: BoundedFloat = _bounded_float,
) -> dict[str, Any]:
    raw_output = str((payload or {}).get("raw_output") or (payload or {}).get("text") or "")
    if not raw_output.strip():
        raise AssistantResponseParseError("assistant response is empty")
    min_confidence = bounded_query_float((payload or {}).get("min_confidence", 0.0), 0.0, 1.0)
    return assistant_response_to_generation_guidance(
        parse_assistant_response(raw_output),
        min_confidence=min_confidence,
    )


def save_assistant_guidance_payload(
    payload: dict[str, Any],
    *,
    run_config_from_payload: RunConfigFromPayload,
    bounded_query_float: BoundedFloat = _bounded_float,
    payload_truthy: PayloadTruthy = _payload_truthy,
    assistant_guidance_snapshot: Snapshot,
    repository_factory: Callable[[str], ResearchRepository] = ResearchRepository,
) -> dict[str, Any]:
    payload = dict(payload or {})
    run_config = run_config_from_payload(payload)
    min_confidence = bounded_query_float(
        payload.get(
            "min_confidence",
            payload.get("assistant_min_confidence", run_config.ops.budget.assistant_guidance_min_confidence),
        ),
        0.0,
        1.0,
    )
    supplied_guidance = payload.get("assistant_guidance")
    if isinstance(supplied_guidance, dict):
        guidance = dict(supplied_guidance)
        guidance.setdefault("source", "assistant_guidance_argument")
        guidance.setdefault("min_confidence", min_confidence)
        confidence = bounded_query_float(guidance.get("confidence", 1.0), 0.0, 1.0)
        if confidence < min_confidence:
            guidance["usable"] = False
            guidance["reason"] = "confidence_below_threshold"
        guidance = ensure_assistant_guidance_digest(guidance)
    else:
        raw_output = str(payload.get("assistant_response") or payload.get("raw_output") or payload.get("text") or "")
        if not raw_output.strip():
            raise AssistantResponseParseError("assistant response is empty")
        guidance = assistant_response_to_generation_guidance(
            parse_assistant_response(raw_output),
            min_confidence=min_confidence,
        )
        if not payload_truthy(guidance.get("usable", True)):
            guidance["reason"] = "confidence_below_threshold"

    usable = guidance.get("ok") is not False and payload_truthy(guidance.get("usable", True))
    has_bias = bool(
        guidance.get("top_fields")
        or guidance.get("top_operators")
        or guidance.get("preferred_windows")
        or guidance.get("field_combinations")
    )
    if not usable:
        return {
            "ok": True,
            "saved": False,
            "reason": guidance.get("reason") or "not_usable",
            "assistant_guidance": guidance,
            "snapshot": assistant_guidance_snapshot(min_confidence=min_confidence),
        }
    if not has_bias:
        return {
            "ok": True,
            "saved": False,
            "reason": "no_generator_bias",
            "assistant_guidance": guidance,
            "snapshot": assistant_guidance_snapshot(min_confidence=min_confidence),
        }

    repository_factory(run_config.ops.storage_dir).save_assistant_guidance(
        guidance,
        source=str(payload.get("source") or "web_save_assistant_guidance"),
    )
    return {
        "ok": True,
        "saved": True,
        "assistant_guidance": guidance,
        "snapshot": assistant_guidance_snapshot(min_confidence=min_confidence),
    }

"""Research memory and assistant snapshot services for the local web API."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research.assistant import (
    AssistantResponseParseError,
    assistant_response_to_generation_guidance,
    build_assistant_request_pack,
    parse_assistant_response,
)
from brain_alpha_ops.research.context import build_assistant_context_pack
from brain_alpha_ops.research.guidance import (
    assistant_guidance_outcome_status,
    assistant_guidance_scoring_eligibility,
    assistant_guidance_scoring_policy,
    ensure_assistant_guidance_digest,
)
from brain_alpha_ops.research.knowledge_base import ResearchKnowledgeBase
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository


logger = logging.getLogger(__name__)

LoadConfig = Callable[[], RunConfig]
WebError = Callable[[Exception, str], dict[str, Any]]
BoundedFloat = Callable[[Any, float, float], float]
PayloadTruthy = Callable[[Any], bool]
ReadStorageJsonl = Callable[..., list[dict[str, Any]]]
StoragePath = Callable[[str], Path]
SafeErrorMessage = Callable[[Exception], str]
RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
Snapshot = Callable[..., dict[str, Any]]


def _default_web_error(exc: Exception, error_code: str) -> dict[str, Any]:
    return {"ok": False, "error_code": error_code, "error": str(exc)}


def _bounded_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def _payload_truthy(value: Any) -> bool:
    return value not in (False, "false", "False", "0", 0, None)


def research_memory_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    load_config: LoadConfig = load_run_config,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        return ResearchMemory(config.ops.storage_dir).summary(limit=limit, top_n=top_n)
    except Exception as exc:
        return web_error(exc, "RESEARCH_MEMORY_ERROR")


def research_knowledge_snapshot(
    *,
    limit: int = 100,
    min_confidence: float = 0.0,
    load_config: LoadConfig = load_run_config,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        return ResearchKnowledgeBase(config.ops.storage_dir).summary(
            limit=limit,
            min_confidence=min_confidence,
        )
    except Exception as exc:
        return web_error(exc, "RESEARCH_KNOWLEDGE_ERROR")


def prompt_run_ledger_snapshot(
    *,
    limit: int = 100,
    load_config: LoadConfig = load_run_config,
    read_jsonl_tail_func: Callable[..., list[dict[str, Any]]] = read_jsonl_tail,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        path = Path(config.ops.storage_dir) / "prompt_runs.jsonl"
        rows = read_jsonl_tail_func(path, limit=max(1, int(limit or 1)))
        items = [_prompt_run_public_row(row) for row in reversed(rows) if isinstance(row, dict)]
        return {
            "ok": True,
            "schema_version": "prompt_run_ledger_snapshot.v1",
            "source": "prompt_runs_jsonl",
            "path": str(path),
            "count": len(items),
            "items": items,
        }
    except Exception as exc:
        return web_error(exc, "PROMPT_RUN_LEDGER_ERROR")


def _prompt_run_public_row(row: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "schema_version",
        "timestamp",
        "prompt_digest",
        "context_digest",
        "model",
        "temperature",
        "response_digest",
        "parse_status",
    }
    return {key: row.get(key) for key in allowed_keys if key in row}


def research_observability_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_cloud: bool = True,
    load_config: LoadConfig = load_run_config,
    durable_job_rows: Callable[..., list[dict[str, Any]]] | None = None,
    observability_builder: Callable[..., dict[str, Any]] = build_research_observability_snapshot,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        job_rows = durable_job_rows(limit=min(limit, 1000)) if durable_job_rows else []
        return observability_builder(
            config.ops.storage_dir,
            limit=limit,
            top_n=top_n,
            include_cloud=include_cloud,
            job_rows=job_rows,
        )
    except Exception as exc:
        return web_error(exc, "RESEARCH_OBSERVABILITY_ERROR")


def durable_job_rows(*, stores: list[tuple[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source, store in stores:
        all_jobs = getattr(store, "all", None)
        if not callable(all_jobs):
            continue
        try:
            for job_id, job in all_jobs(limit=limit):
                rows.append({"source": source, "job_id": job_id, **job})
        except Exception:
            continue
    return rows[-limit:]


def assistant_guidance_snapshot(
    *,
    limit: int = 100,
    min_confidence: float | None = None,
    load_config: LoadConfig = load_run_config,
    bounded_query_float: BoundedFloat = _bounded_float,
    payload_truthy: PayloadTruthy = _payload_truthy,
    read_storage_jsonl: ReadStorageJsonl | None = None,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    try:
        config = load_config()
        budget = config.ops.budget
        configured_min_confidence = bounded_query_float(
            getattr(budget, "assistant_guidance_min_confidence", 0.6),
            0.0,
            1.0,
        )
        threshold = configured_min_confidence if min_confidence is None else bounded_query_float(min_confidence, 0.0, 1.0)
        scoring_policy = assistant_guidance_scoring_policy(config.ops.scoring)
        memory = ResearchMemory(config.ops.storage_dir)
        guidance = memory.latest_assistant_guidance(
            limit=limit,
            min_confidence=threshold,
        )
        memory_summary = memory.summary(limit=5000, top_n=10)
        history = read_storage_jsonl("assistant_guidance.jsonl", limit=limit) if read_storage_jsonl else []
        outcomes_by_guidance = {
            str(row.get("guidance_digest") or ""): row
            for row in memory_summary.get("assistant_guidance_outcomes", [])
            if row.get("guidance_digest")
        }
        history_items = assistant_guidance_history(
            history,
            min_confidence=threshold,
            scoring_policy=scoring_policy,
            outcomes_by_guidance=outcomes_by_guidance,
            bounded_query_float=bounded_query_float,
            payload_truthy=payload_truthy,
        )
        return {
            "ok": True,
            "schema_version": "assistant_guidance_snapshot.v1",
            "enabled": bool(getattr(budget, "use_assistant_guidance", True)),
            "configured_min_confidence": configured_min_confidence,
            "min_confidence": threshold,
            "history_count": len(history),
            "history_limit": limit,
            "scoring_policy": scoring_policy,
            "score_adjustment_eligibility": assistant_guidance_scoring_eligibility(
                guidance,
                guidance.get("historical_outcome") if isinstance(guidance, dict) else {},
                scoring_policy,
            ),
            "guidance": guidance,
            "history": history_items,
            "outcomes": memory_summary.get("assistant_guided", {}),
            "outcomes_by_guidance": memory_summary.get("assistant_guidance_outcomes", []),
        }
    except Exception as exc:
        return web_error(exc, "ASSISTANT_GUIDANCE_ERROR")


def assistant_guidance_history(
    rows: list[dict[str, Any]],
    *,
    min_confidence: float,
    scoring_policy: dict[str, Any] | None = None,
    outcomes_by_guidance: dict[str, dict[str, Any]] | None = None,
    bounded_query_float: BoundedFloat = _bounded_float,
    payload_truthy: PayloadTruthy = _payload_truthy,
) -> list[dict[str, Any]]:
    threshold = bounded_query_float(min_confidence, 0.0, 1.0)
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        guidance = row.get("guidance") if isinstance(row.get("guidance"), dict) else row
        if not isinstance(guidance, dict):
            continue
        guidance = ensure_assistant_guidance_digest(guidance)
        digest = row.get("guidance_digest") or guidance.get("guidance_digest")
        confidence = bounded_query_float(guidance.get("confidence", 1.0), 0.0, 1.0)
        usable = guidance.get("ok") is not False and payload_truthy(guidance.get("usable", True))
        has_bias = bool(
            guidance.get("top_fields")
            or guidance.get("top_operators")
            or guidance.get("preferred_windows")
            or guidance.get("field_combinations")
        )
        outcomes = (outcomes_by_guidance or {}).get(str(digest), {})
        outcome_status = assistant_guidance_outcome_status(outcomes)
        scoring_eligibility = assistant_guidance_scoring_eligibility(guidance, outcomes, scoring_policy or {})
        items.append(
            {
                "history_index": index,
                "timestamp": row.get("timestamp") or row.get("persisted_at") or "",
                "source": row.get("source") or guidance.get("persistence_source") or guidance.get("source") or "assistant_guidance_jsonl",
                "guidance_digest": digest,
                "usable": usable,
                "meets_min_confidence": confidence >= threshold,
                "has_generator_bias": has_bias,
                "has_healthy_outcome": outcome_status != "weak",
                "score_adjustment_eligible": scoring_eligibility.get("eligible", False),
                "score_adjustment_reason": scoring_eligibility.get("reason", ""),
                "historical_outcome_status": outcome_status,
                "confidence": confidence,
                "sample_size": guidance.get("sample_size") or 0,
                "summary": guidance.get("summary") or "",
                "reason": guidance.get("reason") or "",
                "top_fields": guidance.get("top_fields") if isinstance(guidance.get("top_fields"), list) else [],
                "top_operators": guidance.get("top_operators") if isinstance(guidance.get("top_operators"), list) else [],
                "preferred_windows": guidance.get("preferred_windows") if isinstance(guidance.get("preferred_windows"), list) else [],
                "field_combinations": guidance.get("field_combinations") if isinstance(guidance.get("field_combinations"), list) else [],
                "risk_flags": guidance.get("risk_flags") if isinstance(guidance.get("risk_flags"), list) else [],
                "outcomes": outcomes,
                "score_adjustment_eligibility": scoring_eligibility,
                "assistant_guidance": guidance,
            }
        )
    return list(reversed(items))


def assistant_context_snapshot(
    *,
    limit: int = 5000,
    top_n: int = 10,
    include_prompt: bool = True,
    include_sensitive: bool = False,
    load_config: LoadConfig = load_run_config,
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


def latest_result_snapshot(
    *,
    job_store: Any,
    latest_run_history_path: Callable[[], Path | None],
    enrich_progress: Callable[[dict[str, Any]], dict[str, Any]],
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    latest = job_store.latest_any()
    if latest:
        job_id, job = latest
        if "progress" in job:
            job["progress"] = enrich_progress(dict(job["progress"]))
        return {"ok": True, "source": "job_store", "job_id": job_id, **job}

    path = latest_run_history_path()
    if not path:
        return {"ok": True, "source": "empty", "job_id": "", "status": "idle", "result": None, "progress": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {**web_error(exc, "RUN_HISTORY_ERROR"), "source": "run_history", "result": None, "progress": {}}

    summary = data.get("summary") or {}
    result = {
        "summary": summary,
        "candidates": summary.get("candidates") or data.get("candidates") or [],
    }
    progress = {
        "phase": data.get("status") or "completed",
        "phase_label": "最近结果",
        "percent": 100,
        "message": f"已恢复最近一次结果：{path.name}",
        "data": summary,
    }
    return {
        "ok": True,
        "source": "run_history",
        "job_id": str(data.get("run_id") or path.stem),
        "status": data.get("status") or "completed",
        "result": result,
        "progress": progress,
    }


def latest_run_history_path(*, load_config: LoadConfig = load_run_config) -> Path | None:
    history_dir = Path(load_config().ops.storage_dir) / "run_history"
    try:
        files = [path for path in history_dir.glob("*.json") if path.is_file()]
    except Exception:
        return None
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def user_profile_snapshot(
    *,
    job_store: Any,
    storage_jsonl_path: StoragePath,
    safe_error_message: SafeErrorMessage = str,
) -> dict[str, Any]:
    active = job_store.latest_active()
    if not active:
        profile_path = storage_jsonl_path("user_profile.json")
        if profile_path.exists():
            try:
                return json.loads(profile_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("failed to read user profile from %s: %s", profile_path, safe_error_message(exc), exc_info=True)
        return {"tier": "offline", "level": None, "points": None, "username": ""}

    _job_id, job = active
    progress = job.get("progress") or {}
    data = progress.get("data") or {}
    result = job.get("result") or {}
    summary = result.get("summary") or {}
    profile = (
        data.get("user_profile")
        or summary.get("user_profile")
        or {"tier": "loading", "level": None, "points": None}
    )
    return profile

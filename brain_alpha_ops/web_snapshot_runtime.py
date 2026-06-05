"""Assistant, snapshot facade, and runtime snapshots."""

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
from brain_alpha_ops.redaction import redact_error_message, redact_text
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
            logger.warning("durable job rows unavailable for source=%s", source, exc_info=True)
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
        logger.warning("failed to list run history files from %s", history_dir, exc_info=True)
        return None
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def user_profile_snapshot(
    *,
    job_store: Any,
    storage_jsonl_path: StoragePath,
    safe_error_message: SafeErrorMessage = redact_error_message,
) -> dict[str, Any]:
    active = job_store.latest_active()
    if not active:
        profile_path = storage_jsonl_path("user_profile.json")
        if profile_path.exists():
            try:
                return json.loads(profile_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(
                    "failed to read user profile from %s: %s",
                    redact_text(profile_path, max_length=180),
                    safe_error_message(exc),
                )
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

"""Public snapshot function facade for the local web module."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class WebSnapshotFacade:
    runtime_factory: Callable[[], Any]
    latest_result_snapshot_func: Callable[[], dict] | None = None
    latest_run_history_path_func: Callable[[], Path | None] | None = None
    assistant_context_snapshot_func: Callable[..., dict] | None = None
    assistant_guidance_snapshot_func: Callable[..., dict] | None = None

    def _runtime(self) -> Any:
        return self.runtime_factory()

    def durable_job_rows(self, *, limit: int) -> list[dict]:
        return self._runtime().durable_job_rows(limit=limit)

    def research_memory_snapshot(self, *, limit: int = 5000, top_n: int = 10) -> dict:
        return self._runtime().research_memory_snapshot(limit=limit, top_n=top_n)

    def research_knowledge_snapshot(self, *, limit: int = 100, min_confidence: float = 0.0) -> dict:
        return self._runtime().research_knowledge_snapshot(limit=limit, min_confidence=min_confidence)

    def research_observability_snapshot(self, *, limit: int = 5000, top_n: int = 10, include_cloud: bool = True) -> dict:
        return self._runtime().research_observability_snapshot(limit=limit, top_n=top_n, include_cloud=include_cloud)

    def prompt_run_ledger_snapshot(self, *, limit: int = 100) -> dict:
        return self._runtime().prompt_run_ledger_snapshot(limit=limit)

    def assistant_guidance_snapshot(self, *, limit: int = 100, min_confidence: float | None = None) -> dict:
        return self._runtime().assistant_guidance_snapshot(limit=limit, min_confidence=min_confidence)

    def assistant_guidance_history(
        self,
        rows: list[dict],
        *,
        min_confidence: float,
        scoring_policy: dict | None = None,
        outcomes_by_guidance: dict[str, dict] | None = None,
    ) -> list[dict]:
        return self._runtime().assistant_guidance_history(
            rows,
            min_confidence=min_confidence,
            scoring_policy=scoring_policy,
            outcomes_by_guidance=outcomes_by_guidance,
        )

    def assistant_context_snapshot(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_prompt: bool = True,
        include_sensitive: bool = False,
    ) -> dict:
        return self._runtime().assistant_context_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
            latest_result_snapshot=self._latest_result_snapshot,
        )

    def assistant_request_snapshot(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_prompt: bool = True,
        include_offline_draft: bool = True,
        include_sensitive: bool = False,
    ) -> dict:
        return self._runtime().assistant_request_snapshot(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_offline_draft=include_offline_draft,
            include_sensitive=include_sensitive,
            assistant_context_snapshot=self._assistant_context_snapshot,
        )

    def assistant_response_parse_payload(self, payload: dict) -> dict:
        return self._runtime().assistant_response_parse_payload(payload)

    def assistant_response_guidance_payload(self, payload: dict) -> dict:
        return self._runtime().assistant_response_guidance_payload(payload)

    def anti_overfit_snapshot(self, candidate_id: str = "") -> dict:
        return self._runtime().anti_overfit_snapshot(candidate_id, self._latest_result_snapshot)

    def rolling_validation_snapshot(self, candidate_id: str = "", windows: int = 4) -> dict:
        return self._runtime().rolling_validation_snapshot(candidate_id, windows, self._latest_result_snapshot)

    def assistant_cross_review_payload(self, payload: dict) -> dict:
        return self._runtime().assistant_cross_review_payload(payload)

    def save_assistant_guidance_payload(self, payload: dict) -> dict:
        return self._runtime().save_assistant_guidance_payload(payload, self._assistant_guidance_snapshot)

    def latest_result_snapshot(self) -> dict:
        return self._runtime().latest_result_snapshot(self._latest_run_history_path)

    def latest_run_history_path(self) -> Path | None:
        return self._runtime().latest_run_history_path()

    def user_profile_snapshot(self) -> dict:
        return self._runtime().user_profile_snapshot()

    def _latest_result_snapshot(self) -> dict:
        if self.latest_result_snapshot_func is not None:
            return self.latest_result_snapshot_func()
        return self.latest_result_snapshot()

    def _latest_run_history_path(self) -> Path | None:
        if self.latest_run_history_path_func is not None:
            return self.latest_run_history_path_func()
        return self.latest_run_history_path()

    def _assistant_context_snapshot(self, **kwargs) -> dict:
        if self.assistant_context_snapshot_func is not None:
            return self.assistant_context_snapshot_func(**kwargs)
        return self.assistant_context_snapshot(**kwargs)

    def _assistant_guidance_snapshot(self, **kwargs) -> dict:
        if self.assistant_guidance_snapshot_func is not None:
            return self.assistant_guidance_snapshot_func(**kwargs)
        return self.assistant_guidance_snapshot(**kwargs)

"""Runtime dependency facade for Web snapshot services."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.web_snapshots import (
    assistant_context_snapshot as assistant_context_snapshot_service,
    assistant_guidance_history as assistant_guidance_history_service,
    assistant_guidance_snapshot as assistant_guidance_snapshot_service,
    assistant_request_snapshot as assistant_request_snapshot_service,
    assistant_response_guidance_payload as assistant_response_guidance_payload_service,
    assistant_response_parse_payload as assistant_response_parse_payload_service,
    durable_job_rows as durable_job_rows_service,
    latest_result_snapshot as latest_result_snapshot_service,
    latest_run_history_path as latest_run_history_path_service,
    prompt_run_ledger_snapshot as prompt_run_ledger_snapshot_service,
    research_knowledge_snapshot as research_knowledge_snapshot_service,
    research_memory_snapshot as research_memory_snapshot_service,
    research_observability_snapshot as research_observability_snapshot_service,
    save_assistant_guidance_payload as save_assistant_guidance_payload_service,
    user_profile_snapshot as user_profile_snapshot_service,
)
from brain_alpha_ops.web_review import (
    anti_overfit_snapshot as anti_overfit_snapshot_service,
    assistant_cross_review_payload as assistant_cross_review_payload_service,
    rolling_validation_snapshot as rolling_validation_snapshot_service,
)


@dataclass
class WebSnapshotRuntime:
    load_config: Callable[[], Any]
    web_error: Callable[[Exception, str], dict]
    bounded_query_float: Callable[..., float]
    payload_truthy: Callable[[Any], bool]
    read_storage_jsonl: Callable[..., list[dict]]
    run_config_from_payload: Callable[[dict], Any]
    cloud_alpha_snapshot: Callable[..., dict]
    storage_jsonl_path: Callable[[str], Path]
    safe_error_message: Callable[[Exception], str]
    job_store: Any
    sync_job_store: Any
    check_job_store: Any
    enrich_progress: Callable[[dict], dict]
    repository_factory: Callable[..., Any] = ResearchRepository
    observability_builder: Callable[..., dict] = build_research_observability_snapshot

    def durable_job_rows(self, *, limit: int) -> list[dict]:
        return durable_job_rows_service(
            stores=[
                ("production_job", self.job_store),
                ("sync_job", self.sync_job_store),
                ("check_job", self.check_job_store),
            ],
            limit=limit,
        )

    def research_memory_snapshot(self, *, limit: int = 5000, top_n: int = 10) -> dict:
        return research_memory_snapshot_service(
            limit=limit,
            top_n=top_n,
            load_config=self.load_config,
            web_error=self.web_error,
        )

    def research_knowledge_snapshot(self, *, limit: int = 100, min_confidence: float = 0.0) -> dict:
        return research_knowledge_snapshot_service(
            limit=limit,
            min_confidence=min_confidence,
            load_config=self.load_config,
            web_error=self.web_error,
        )

    def research_observability_snapshot(self, *, limit: int = 5000, top_n: int = 10, include_cloud: bool = True) -> dict:
        return research_observability_snapshot_service(
            limit=limit,
            top_n=top_n,
            include_cloud=include_cloud,
            load_config=self.load_config,
            durable_job_rows=self.durable_job_rows,
            observability_builder=self.observability_builder,
            web_error=self.web_error,
        )

    def prompt_run_ledger_snapshot(self, *, limit: int = 100) -> dict:
        return prompt_run_ledger_snapshot_service(
            limit=limit,
            load_config=self.load_config,
            web_error=self.web_error,
        )

    def assistant_guidance_snapshot(self, *, limit: int = 100, min_confidence: float | None = None) -> dict:
        return assistant_guidance_snapshot_service(
            limit=limit,
            min_confidence=min_confidence,
            load_config=self.load_config,
            bounded_query_float=self.bounded_query_float,
            payload_truthy=self.payload_truthy,
            read_storage_jsonl=self.read_storage_jsonl,
            web_error=self.web_error,
        )

    def assistant_guidance_history(
        self,
        rows: list[dict],
        *,
        min_confidence: float,
        scoring_policy: dict | None = None,
        outcomes_by_guidance: dict[str, dict] | None = None,
    ) -> list[dict]:
        return assistant_guidance_history_service(
            rows,
            min_confidence=min_confidence,
            scoring_policy=scoring_policy,
            outcomes_by_guidance=outcomes_by_guidance,
            bounded_query_float=self.bounded_query_float,
            payload_truthy=self.payload_truthy,
        )

    def assistant_context_snapshot(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_prompt: bool = True,
        include_sensitive: bool = False,
        latest_result_snapshot: Callable[[], dict],
    ) -> dict:
        return assistant_context_snapshot_service(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_sensitive=include_sensitive,
            load_config=self.load_config,
            latest_result_snapshot=latest_result_snapshot,
            cloud_alpha_snapshot=self.cloud_alpha_snapshot,
            web_error=self.web_error,
        )

    def assistant_request_snapshot(
        self,
        *,
        limit: int = 5000,
        top_n: int = 10,
        include_prompt: bool = True,
        include_offline_draft: bool = True,
        include_sensitive: bool = False,
        assistant_context_snapshot: Callable[..., dict],
    ) -> dict:
        return assistant_request_snapshot_service(
            limit=limit,
            top_n=top_n,
            include_prompt=include_prompt,
            include_offline_draft=include_offline_draft,
            include_sensitive=include_sensitive,
            assistant_context_snapshot=assistant_context_snapshot,
            web_error=self.web_error,
        )

    def assistant_response_parse_payload(self, payload: dict) -> dict:
        return assistant_response_parse_payload_service(payload)

    def assistant_response_guidance_payload(self, payload: dict) -> dict:
        return assistant_response_guidance_payload_service(payload, bounded_query_float=self.bounded_query_float)

    def anti_overfit_snapshot(self, candidate_id: str, latest_result_snapshot: Callable[[], dict]) -> dict:
        return anti_overfit_snapshot_service(
            candidate_id=candidate_id,
            latest_result_snapshot=latest_result_snapshot,
        )

    def rolling_validation_snapshot(self, candidate_id: str, windows: int, latest_result_snapshot: Callable[[], dict]) -> dict:
        return rolling_validation_snapshot_service(
            candidate_id=candidate_id,
            windows=windows,
            latest_result_snapshot=latest_result_snapshot,
        )

    def assistant_cross_review_payload(self, payload: dict) -> dict:
        return assistant_cross_review_payload_service(
            payload,
            bounded_query_float=self.bounded_query_float,
        )

    def save_assistant_guidance_payload(self, payload: dict, assistant_guidance_snapshot: Callable[..., dict]) -> dict:
        return save_assistant_guidance_payload_service(
            payload,
            run_config_from_payload=self.run_config_from_payload,
            bounded_query_float=self.bounded_query_float,
            payload_truthy=self.payload_truthy,
            assistant_guidance_snapshot=assistant_guidance_snapshot,
            repository_factory=self.repository_factory,
        )

    def latest_result_snapshot(self, latest_run_history_path: Callable[[], Path | None]) -> dict:
        return latest_result_snapshot_service(
            job_store=self.job_store,
            latest_run_history_path=latest_run_history_path,
            enrich_progress=self.enrich_progress,
            web_error=self.web_error,
        )

    def latest_run_history_path(self) -> Path | None:
        return latest_run_history_path_service(load_config=self.load_config)

    def user_profile_snapshot(self) -> dict:
        return user_profile_snapshot_service(
            job_store=self.job_store,
            storage_jsonl_path=self.storage_jsonl_path,
            safe_error_message=self.safe_error_message,
        )
"""Research snapshots, run-history recovery, and profile helpers.

Consolidated from the former ``web_assistant_snapshots/`` subpackage
(``_helpers`` + ``_research_snapshots`` + ``_run_history`` + ``_profile``
modules). Provides shared logger/type aliases, research memory/knowledge/
observability snapshots, prompt-run ledger, run-history replay audit, and
user-profile snapshot helpers.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import RunConfig, load_run_config
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.redaction import redact_error_message, redact_text
from brain_alpha_ops.research.knowledge_base import ResearchKnowledgeBase
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.observability import build_research_observability_snapshot
from brain_alpha_ops.web_candidates.payloads import (
    DEFAULT_MAIN_POOL_SIZE,
    candidate_payload,
    candidate_result_total,
    has_candidate_like_rows,
)

logger = logging.getLogger("brain_alpha_ops.web.misc.web_assistant_snapshots")

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
    from brain_alpha_ops.redaction import redact_error_message
    return {"ok": False, "error_code": error_code, "error": redact_error_message(exc)}


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


def latest_result_snapshot(
    *,
    job_store: Any,
    latest_run_history_path: Callable[[], Path | None],
    enrich_progress: Callable[[dict[str, Any]], dict[str, Any]],
    read_storage_jsonl: ReadStorageJsonl | None = None,
    target_pool_size: int | None = None,
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

    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    result = _run_history_result_payload(
        data,
        summary,
        path=path,
        read_storage_jsonl=read_storage_jsonl,
        target_pool_size=target_pool_size,
    )
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


def _run_history_result_payload(
    data: dict[str, Any],
    summary: dict[str, Any],
    *,
    path: Path,
    read_storage_jsonl: ReadStorageJsonl | None,
    target_pool_size: int | None,
) -> dict[str, Any]:
    candidates = _run_history_candidate_rows(data, summary)
    total = _run_history_candidate_total(data, summary, fallback=len(candidates))
    if not has_candidate_like_rows(candidates):
        return {
            "summary": summary,
            "candidates": candidates,
            "replay_audit": _run_history_replay_audit(
                payload={"candidates": []},
                payload_rows=[],
                lifecycle_rows=[],
                raw_candidate_count=len(candidates),
                total_candidate_count=total,
                path=path,
            ),
        }

    payload_rows = _run_history_candidate_payload_rows(candidates)
    lifecycle_rows = _run_history_lifecycle_rows(read_storage_jsonl)
    payload = candidate_payload(
        payload_rows,
        source="run_history",
        total=total,
        path=str(path),
        lifecycle_rows=lifecycle_rows,
        target_pool_size=target_pool_size or DEFAULT_MAIN_POOL_SIZE,
    )
    return {
        "summary": summary,
        **payload,
        "replay_audit": _run_history_replay_audit(
            payload=payload,
            payload_rows=payload_rows,
            lifecycle_rows=lifecycle_rows,
            raw_candidate_count=len(candidates),
            total_candidate_count=total,
            path=path,
        ),
    }


def _run_history_candidate_rows(data: dict[str, Any], summary: dict[str, Any]) -> list[Any]:
    for container in (
        summary,
        data.get("result") if isinstance(data.get("result"), dict) else {},
        data.get("data") if isinstance(data.get("data"), dict) else {},
        data,
    ):
        rows = container.get("candidates") if isinstance(container, dict) else None
        if isinstance(rows, list) and rows:
            return rows
    return []


def _run_history_candidate_payload_rows(rows: list[Any]) -> list[dict[str, Any]]:
    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else row
        payload_rows.append(dict(candidate))
    return payload_rows


def _run_history_candidate_total(data: dict[str, Any], summary: dict[str, Any], *, fallback: int) -> int:
    for container in (summary, data):
        for key in ("total_candidates", "produced_count"):
            try:
                number = int(container.get(key))
            except (TypeError, ValueError):
                continue
            if number >= 0:
                return max(number, fallback)
    return candidate_result_total({**data, **summary}, fallback)


def _run_history_lifecycle_rows(read_storage_jsonl: ReadStorageJsonl | None) -> list[dict[str, Any]]:
    if read_storage_jsonl is None:
        return []
    try:
        rows = read_storage_jsonl("lifecycle.jsonl", limit=None)
    except Exception:
        logger.warning("run history lifecycle rows unavailable; continuing without historical risk", exc_info=True)
        return []
    return [row for row in rows if isinstance(row, dict)]


def _run_history_replay_audit(
    *,
    payload: dict[str, Any],
    payload_rows: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
    raw_candidate_count: int,
    total_candidate_count: int,
    path: Path,
) -> dict[str, Any]:
    candidates = [row for row in payload.get("candidates") or [] if isinstance(row, dict)]
    pool_summary = payload.get("pool_summary") if isinstance(payload.get("pool_summary"), dict) else {}
    scientific = payload.get("scientific_audit") if isinstance(payload.get("scientific_audit"), dict) else {}
    workflow = payload.get("workflow_plan") if isinstance(payload.get("workflow_plan"), dict) else {}
    readiness = workflow.get("readiness_evidence") if isinstance(workflow.get("readiness_evidence"), dict) else {}
    production_counts = pool_summary.get("decision_action_counts")
    if not isinstance(production_counts, dict):
        production_counts = _run_history_decision_action_counts(candidates)
    blocker_counts = readiness.get("blocker_counts")
    if not isinstance(blocker_counts, dict):
        blocker_counts = _run_history_reason_counts(candidates)
    return {
        "schema_version": "run-history-replay-audit-v1",
        "source": "run_history",
        "path": str(path),
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "real_submit_performed": False,
        "raw_candidate_row_count": int(raw_candidate_count),
        "payload_candidate_row_count": len(payload_rows),
        "recovered_candidate_count": len(candidates),
        "total_candidate_count": int(total_candidate_count),
        "lifecycle_row_count": len(lifecycle_rows),
        "lifecycle_rows_used_count": _run_history_matching_lifecycle_count(candidates, lifecycle_rows),
        "candidates_with_production_decision": sum(
            1 for row in candidates if isinstance(row.get("production_decision"), dict)
        ),
        "production_decision_counts": dict(sorted(production_counts.items())),
        "scientific_audit_summary_available": bool(scientific),
        "candidates_with_scientific_audit": int(scientific.get("audited_count") or 0),
        "candidates_missing_scientific_audit": int(scientific.get("missing_audit_count") or 0),
        "scientific_submit_boundary_intact": (
            int(scientific.get("submit_allowed_count") or 0) == 0
            and int(scientific.get("real_submit_performed_count") or 0) == 0
        ),
        "workflow_plan_available": bool(workflow),
        "workflow_queue_counts": _run_history_workflow_queue_counts(workflow),
        "readiness_blocker_counts": dict(sorted(blocker_counts.items())),
        "execution_gap_counts": dict(sorted((readiness.get("execution_gap_counts") or {}).items()))
        if isinstance(readiness.get("execution_gap_counts"), dict)
        else {},
        "stop_rule": readiness.get("authoritative_stop_rule") or "scripts/check_live_submit_readiness.py",
        "submit_boundary_intact": (
            workflow.get("submit_allowed") is not True
            and int(scientific.get("submit_allowed_count") or 0) == 0
            and int(scientific.get("real_submit_performed_count") or 0) == 0
        ),
    }


def _run_history_workflow_queue_counts(workflow: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in ("producer", "validator", "rework", "review", "archive"):
        queue = workflow.get(name) if isinstance(workflow.get(name), dict) else {}
        value = queue.get("candidate_count")
        if value is None and name == "producer":
            value = queue.get("deficit")
        try:
            counts[name] = max(0, int(value or 0))
        except (TypeError, ValueError):
            counts[name] = 0
    return counts


def _run_history_reason_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in candidates:
        decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
        for reason in decision.get("reason_codes") or []:
            text = str(reason or "").strip()
            if text:
                counts[text] += 1
    return dict(sorted(counts.items()))


def _run_history_decision_action_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in candidates:
        decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
        action = str(decision.get("action") or "").strip()
        if action:
            counts[action] += 1
    return dict(sorted(counts.items()))


def _run_history_matching_lifecycle_count(
    candidates: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
) -> int:
    keys: set[str] = set()
    for row in candidates:
        keys.update(_run_history_candidate_keys(row))
    if not keys:
        return 0
    matched = 0
    for row in lifecycle_rows:
        if any(key in keys for key in _run_history_candidate_keys(row)):
            matched += 1
    return matched


def _run_history_candidate_keys(row: dict[str, Any]) -> set[str]:
    keys = {
        str(row.get(field) or "").strip()
        for field in ("alpha_id", "candidate_id", "official_alpha_id", "simulation_id")
        if str(row.get(field) or "").strip()
    }
    expression = _run_history_expression_key(row.get("expression"))
    if expression:
        keys.add(f"expression:{expression}")
        keys.add(_run_history_expression_digest(expression))
    digest = str(row.get("expression_digest") or "").strip()
    if digest:
        keys.add(digest)
    return keys


def _run_history_expression_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _run_history_expression_digest(expression: str) -> str:
    return "expr_" + sha256(expression.encode("utf-8")).hexdigest()[:12] if expression else ""


__all__ = [
    "BoundedFloat",
    "LoadConfig",
    "PayloadTruthy",
    "ReadStorageJsonl",
    "RunConfigFromPayload",
    "SafeErrorMessage",
    "Snapshot",
    "StoragePath",
    "WebError",
    "durable_job_rows",
    "latest_result_snapshot",
    "latest_run_history_path",
    "logger",
    "prompt_run_ledger_snapshot",
    "research_knowledge_snapshot",
    "research_memory_snapshot",
    "research_observability_snapshot",
    "user_profile_snapshot",
    "_bounded_float",
    "_default_web_error",
    "_payload_truthy",
    "_prompt_run_public_row",
    "_run_history_candidate_keys",
    "_run_history_candidate_payload_rows",
    "_run_history_candidate_rows",
    "_run_history_candidate_total",
    "_run_history_decision_action_counts",
    "_run_history_expression_digest",
    "_run_history_expression_key",
    "_run_history_lifecycle_rows",
    "_run_history_matching_lifecycle_count",
    "_run_history_reason_counts",
    "_run_history_replay_audit",
    "_run_history_result_payload",
    "_run_history_workflow_queue_counts",
]

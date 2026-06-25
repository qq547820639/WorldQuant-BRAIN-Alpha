"""Research memory, knowledge, prompt-run, and observability snapshots."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.jsonl import read_jsonl_tail
from brain_alpha_ops.research.knowledge_base import ResearchKnowledgeBase
from brain_alpha_ops.research.memory import ResearchMemory
from brain_alpha_ops.research.observability import build_research_observability_snapshot

from ._helpers import (
    LoadConfig,
    ReadStorageJsonl,
    WebError,
    _default_web_error,
    logger,
)


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

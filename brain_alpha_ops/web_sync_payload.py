"""Synchronous cloud sync payload service for the local web API."""

from __future__ import annotations

from typing import Any, Callable

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.repository import ResearchRepository


RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ApiFromRunConfig = Callable[[RunConfig], Any]
RepositoryFactory = Callable[[str], ResearchRepository]
DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
PersistOfficialContext = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]


def sync_cloud_alphas_payload(
    payload: dict[str, Any],
    *,
    run_config_from_payload: RunConfigFromPayload,
    api_from_run_config: ApiFromRunConfig,
    repository_factory: RepositoryFactory,
    datasets_from_fields: DatasetsFromFields,
    persist_official_context: PersistOfficialContext,
    default_fields: list[dict[str, Any]],
    default_operators: list[dict[str, Any]],
) -> dict[str, Any]:
    run_config = run_config_from_payload(payload)
    sync_range = str(payload.get("syncRange", run_config.ops.budget.cloud_sync_range))
    api = api_from_run_config(run_config)
    api.authenticate()
    rows = api.list_user_alphas(sync_range)
    repo = repository_factory(run_config.ops.storage_dir)
    merge_stats = repo.merge_cloud_alphas(rows, sync_range=sync_range)
    try:
        fields = api.list_fields("all", run_config.ops.settings.region)
        operators = api.list_operators("all")
        datasets = datasets_from_fields(fields)
        persist_official_context(fields, operators, datasets)
    except Exception:
        fields = list(default_fields)
        operators = list(default_operators)
        datasets = []
    return {
        "ok": True,
        "range": sync_range,
        "count": len(rows),
        "scanned": len(rows),
        "added": merge_stats["added"],
        "updated": merge_stats["updated"],
        "skipped": merge_stats["skipped"],
        "failed": merge_stats["failed"],
        "alphas": rows,
        "fields_count": len(fields),
        "operators_count": len(operators),
        "datasets_count": len(datasets),
    }

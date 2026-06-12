"""Synchronous cloud sync payload service for the local web API."""

from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.brain_api.user_alpha_sync import list_user_alphas_for_sync, sync_range_from_payload
from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.repository import ResearchRepository
from brain_alpha_ops.web_cloud_snapshot import (
    cached_user_alpha_paths,
    latest_cached_user_alpha_path,
    latest_cached_user_alphas,
    official_context_file_counts,
    read_official_context_json,
    read_official_context_metadata,
    save_official_context_json,
)
from brain_alpha_ops.web_post_handlers import connection_test_post_payload


logger = logging.getLogger(__name__)


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
    sync_range = sync_range_from_payload(payload)
    api = api_from_run_config(run_config)
    api.authenticate()
    rows = list_user_alphas_for_sync(api, sync_range)
    repo = repository_factory(run_config.ops.storage_dir)
    merge_stats = repo.merge_cloud_alphas(rows, sync_range=sync_range)
    context_error = ""
    context_warnings: list[str] = []

    def on_dataset_fallback(message: str, exc: Exception) -> None:
        context_warnings.append(f"{message}: {redact_error_message(exc)}")

    try:
        fields = api.list_fields("all", run_config.ops.settings.region)
        operators = api.list_operators("all")
        datasets = list_official_datasets_or_derive(
            api,
            fields,
            region=run_config.ops.settings.region,
            datasets_from_fields=datasets_from_fields,
            fallback_warning=on_dataset_fallback,
        )
        persist_official_context(fields, operators, datasets)
    except Exception as exc:
        context_error = redact_error_message(exc)
        logger.warning("official context sync failed; falling back to default fields/operators", exc_info=True)
        fields = list(default_fields)
        operators = list(default_operators)
        datasets = []
    context_status = "fallback" if context_error else ("refreshed_with_warnings" if context_warnings else "refreshed")
    final_status = "completed_with_warnings" if context_error or context_warnings else "completed"
    return {
        "ok": True,
        "status": final_status,
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
        "context_status": context_status,
        "context_error": context_error,
        "context_warnings": context_warnings,
    }


__all__ = [
    "cached_user_alpha_paths",
    "connection_test_post_payload",
    "latest_cached_user_alpha_path",
    "latest_cached_user_alphas",
    "official_context_file_counts",
    "read_official_context_json",
    "read_official_context_metadata",
    "save_official_context_json",
    "sync_cloud_alphas_payload",
]

"""Cloud alpha snapshot and context refresh.

Subpackage of ``brain_alpha_ops.web_cloud``. Splits the original
``snapshot.py`` monolith into focused modules while preserving the public
API surface via re-exports.
"""

from __future__ import annotations

# Constants, storage, cached alphas, cloud alpha snapshot/dedup/summary/cache probe
from .snapshot import (
    CLOUD_SYNC_STALE_SECONDS,
    CONTEXT_CACHE_MANIFEST_SCHEMA,
    OFFICIAL_CONTEXT_FILES,
    LoadConfig,
    RuntimeRoot,
    SafeErrorMessage,
    _bounded_rows,
    _safe_error_message,
    cached_user_alpha_paths,
    cloud_alpha_cache_probe,
    cloud_alpha_id,
    cloud_alpha_snapshot,
    cloud_alpha_summary,
    cloud_row_sort_key,
    dedupe_cloud_alpha_rows,
    extract_alpha_rows,
    is_production_cloud_alpha_row,
    latest_cached_user_alpha_path,
    latest_cached_user_alphas,
    path_modified_at,
    read_storage_jsonl,
    read_storage_jsonl_stats,
    storage_jsonl_path,
)

# Official context read/write helpers + refresh service
from .snapshot_context import (
    DatasetsFromFields,
    JobStoreLike,
    OfficialContextCounts,
    PersistOfficialContext,
    _cloud_refresh_progress_message,
    _metadata_int,
    context_cache_manifest,
    context_items_hash,
    datasets_from_fields,
    enrich_context_cache_metadata,
    official_context_file_counts,
    parse_cache_timestamp,
    persist_official_context,
    read_official_context_json,
    read_official_context_metadata,
    refresh_cloud_context_for_check_service,
    save_official_context_json,
)

__all__ = [
    # Constants
    "CLOUD_SYNC_STALE_SECONDS",
    "CONTEXT_CACHE_MANIFEST_SCHEMA",
    "OFFICIAL_CONTEXT_FILES",
    "LoadConfig",
    "RuntimeRoot",
    "SafeErrorMessage",
    # Storage
    "storage_jsonl_path",
    "read_storage_jsonl",
    "read_storage_jsonl_stats",
    "path_modified_at",
    "extract_alpha_rows",
    # Cloud alpha
    "cloud_alpha_snapshot",
    "cloud_alpha_cache_probe",
    "cloud_alpha_summary",
    "cloud_alpha_id",
    "cloud_row_sort_key",
    "dedupe_cloud_alpha_rows",
    "is_production_cloud_alpha_row",
    # Cached alphas
    "latest_cached_user_alphas",
    "latest_cached_user_alpha_path",
    "cached_user_alpha_paths",
    # Official context read
    "official_context_file_counts",
    "enrich_context_cache_metadata",
    "context_items_hash",
    "context_cache_manifest",
    "parse_cache_timestamp",
    "read_official_context_metadata",
    "read_official_context_json",
    "datasets_from_fields",
    # Official context write
    "persist_official_context",
    "save_official_context_json",
    # Refresh service
    "refresh_cloud_context_for_check_service",
    "JobStoreLike",
    "OfficialContextCounts",
    "DatasetsFromFields",
    "PersistOfficialContext",
]

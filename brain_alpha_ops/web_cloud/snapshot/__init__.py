"""Cloud alpha snapshot and context refresh.

Subpackage of ``brain_alpha_ops.web_cloud``. Splits the original
``snapshot.py`` monolith into focused modules while preserving the public
API surface via re-exports.
"""

from __future__ import annotations

# Constants and type aliases
from ._constants import (
    CLOUD_SYNC_STALE_SECONDS,
    CONTEXT_CACHE_MANIFEST_SCHEMA,
    OFFICIAL_CONTEXT_FILES,
    LoadConfig,
    RuntimeRoot,
    SafeErrorMessage,
    _safe_error_message,
)

# Storage helpers
from ._storage import (
    extract_alpha_rows,
    path_modified_at,
    read_storage_jsonl,
    read_storage_jsonl_stats,
    storage_jsonl_path,
)

# Cloud alpha snapshot, dedup, summary, cache probe
from ._cloud_alpha import (
    _bounded_rows,
    cloud_alpha_cache_probe,
    cloud_alpha_id,
    cloud_alpha_snapshot,
    cloud_alpha_summary,
    cloud_row_sort_key,
    dedupe_cloud_alpha_rows,
    is_production_cloud_alpha_row,
)

# Cached user-alpha helpers
from ._cached_alphas import (
    cached_user_alpha_paths,
    latest_cached_user_alpha_path,
    latest_cached_user_alphas,
)

# Official context read helpers
from ._official_context_read import (
    _metadata_int,
    context_cache_manifest,
    context_items_hash,
    datasets_from_fields,
    enrich_context_cache_metadata,
    official_context_file_counts,
    parse_cache_timestamp,
    read_official_context_json,
    read_official_context_metadata,
)

# Official context write helpers
from ._official_context_write import (
    persist_official_context,
    save_official_context_json,
)

# Refresh service
from ._refresh_service import (
    DatasetsFromFields,
    JobStoreLike,
    OfficialContextCounts,
    PersistOfficialContext,
    _cloud_refresh_progress_message,
    refresh_cloud_context_for_check_service,
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

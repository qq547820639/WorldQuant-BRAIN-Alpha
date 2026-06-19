"""Cloud sync package for BRAIN Alpha Ops web layer.

Consolidates web_cloud_snapshot.py, web_cloud_context_refresh.py,
web_sync_job.py, and web_sync_payload.py into a single package.
"""

import brain_alpha_ops.web  # noqa: F401 — install sys.meta_path bridge

from .snapshot import (
    cloud_alpha_snapshot,
    cloud_alpha_cache_probe,
    dedupe_cloud_alpha_rows,
    is_production_cloud_alpha_row,
    latest_cached_user_alphas,
    latest_cached_user_alpha_path,
    cached_user_alpha_paths,
    path_modified_at,
    extract_alpha_rows,
    official_context_file_counts,
    read_storage_jsonl,
    read_storage_jsonl_stats,
    storage_jsonl_path,
)
from .sync_job import (
    run_sync_job_service,
    SyncJobCancelled,
)
from .sync_payload import sync_cloud_alphas_payload

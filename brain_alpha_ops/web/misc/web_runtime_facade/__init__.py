"""Runtime-bound helpers for the public ``brain_alpha_ops.web`` facade.

Subpackage that splits the original ``web_runtime_facade.py`` monolith into
focused modules while preserving the public API surface via re-exports.
"""
from __future__ import annotations

from ._logging import logger
from ._dispatch_context import (
    _profile_status_code,
    cloud_similarity_risk,
    cloud_status_for,
    handler_dispatch_context,
    test_connection,
)
from ._job_services import (
    alpha_lifecycle_history,
    cloud_alpha_cache_probe,
    cloud_alpha_snapshot,
    generate_candidates_payload,
    lifecycle_from_job,
    lookup_sse_job,
    run_generate_candidates_job,
    run_job,
    run_scoring_evaluate_job,
)
from ._snapshots import (
    candidate_from_payload,
    latest_result_snapshot,
    latest_run_history_path,
    load_presets,
    match_preset_id,
    maybe_archive_lifecycle,
    run_check_batch_job,
    run_sync_job,
    snapshot_facade,
    snapshot_runtime,
    sync_cloud_alphas,
    user_profile_snapshot,
)
from ._submission import (
    check_candidate,
    check_candidate_availability,
    datasets_from_fields,
    find_free_port,
    load_check_results,
    observability_submission_preflight,
    passed_candidates_from_payload,
    persist_official_context,
    public_run_config,
    read_storage_jsonl,
    read_storage_jsonl_stats,
    record_submit_blocked,
    refresh_cloud_context_for_check,
    run_submit_batch_job,
    save_official_context_json,
    storage_jsonl_path,
    submit_batch,
    submit_candidate,
    submission_preflight_advisory,
    submission_preflight_error,
)
from ._server import (
    _server_lock,
    compute_run_stats,
    main,
    serve,
    shutdown_server,
    smoke_test_server,
    status_category,
)

__all__ = [
    # Module-level
    "logger",
    # Dispatch context
    "handler_dispatch_context",
    "cloud_status_for",
    "cloud_similarity_risk",
    "test_connection",
    # Job services
    "run_job",
    "generate_candidates_payload",
    "lookup_sse_job",
    "run_generate_candidates_job",
    "run_scoring_evaluate_job",
    "lifecycle_from_job",
    "alpha_lifecycle_history",
    "cloud_alpha_snapshot",
    "cloud_alpha_cache_probe",
    # Snapshots
    "snapshot_runtime",
    "snapshot_facade",
    "latest_result_snapshot",
    "latest_run_history_path",
    "user_profile_snapshot",
    "load_presets",
    "match_preset_id",
    "candidate_from_payload",
    "sync_cloud_alphas",
    "run_sync_job",
    "run_check_batch_job",
    "maybe_archive_lifecycle",
    # Submission
    "refresh_cloud_context_for_check",
    "datasets_from_fields",
    "persist_official_context",
    "save_official_context_json",
    "passed_candidates_from_payload",
    "check_candidate_availability",
    "check_candidate",
    "submission_preflight_error",
    "submission_preflight_advisory",
    "observability_submission_preflight",
    "record_submit_blocked",
    "submit_candidate",
    "load_check_results",
    "submit_batch",
    "run_submit_batch_job",
    "storage_jsonl_path",
    "read_storage_jsonl",
    "read_storage_jsonl_stats",
    "public_run_config",
    "find_free_port",
    # Server
    "shutdown_server",
    "serve",
    "smoke_test_server",
    "main",
    # Stubs
    "compute_run_stats",
    "status_category",
]

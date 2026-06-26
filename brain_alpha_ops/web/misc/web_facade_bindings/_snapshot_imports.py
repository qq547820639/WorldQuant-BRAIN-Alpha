"""Snapshot binding imports for the web facade.

Re-export shim that pulls snapshot helpers from the consolidated
``web_snapshot_bindings`` module so ``build_web_facade_bindings`` can wire
them into the namespace. Extracted from the former ``web_facade_bindings.py``
monolith (deep-optimization-phase12, Task B8).
"""

from __future__ import annotations

from brain_alpha_ops.web_snapshot_bindings import (
    anti_overfit_snapshot as _anti_overfit_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    assistant_context_snapshot as _assistant_context_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    assistant_cross_review_payload as _assistant_cross_review_payload,
)
from brain_alpha_ops.web_snapshot_bindings import (
    assistant_guidance_history as _assistant_guidance_history,
)
from brain_alpha_ops.web_snapshot_bindings import (
    assistant_guidance_snapshot as _assistant_guidance_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    assistant_request_snapshot as _assistant_request_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    assistant_response_guidance_payload as _assistant_response_guidance_payload,
)
from brain_alpha_ops.web_snapshot_bindings import (
    assistant_response_parse_payload as _assistant_response_parse_payload,
)
from brain_alpha_ops.web_snapshot_bindings import (
    cached_user_alpha_paths as _cached_user_alpha_paths,
)
from brain_alpha_ops.web_snapshot_bindings import (
    cloud_alpha_cache_probe as _cloud_alpha_cache_probe,
)
from brain_alpha_ops.web_snapshot_bindings import (
    cloud_alpha_snapshot as _cloud_alpha_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    cloud_alpha_summary as _cloud_alpha_summary,
)
from brain_alpha_ops.web_snapshot_bindings import (
    durable_job_rows as _durable_job_rows,
)
from brain_alpha_ops.web_snapshot_bindings import (
    latest_cached_user_alpha_path as _latest_cached_user_alpha_path,
)
from brain_alpha_ops.web_snapshot_bindings import (
    latest_cached_user_alphas as _latest_cached_user_alphas,
)
from brain_alpha_ops.web_snapshot_bindings import (
    latest_result_snapshot as _latest_result_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    latest_run_history_path as _latest_run_history_path,
)
from brain_alpha_ops.web_snapshot_bindings import (
    load_presets as _load_presets,
)
from brain_alpha_ops.web_snapshot_bindings import (
    match_preset_id as _match_preset_id,
)
from brain_alpha_ops.web_snapshot_bindings import (
    official_context_file_counts as _official_context_file_counts,
)
from brain_alpha_ops.web_snapshot_bindings import (
    prompt_run_ledger_snapshot as _prompt_run_ledger_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    public_run_config as _public_run_config,
)
from brain_alpha_ops.web_snapshot_bindings import (
    read_official_context_json as _read_official_context_json,
)
from brain_alpha_ops.web_snapshot_bindings import (
    read_official_context_metadata as _read_official_context_metadata,
)
from brain_alpha_ops.web_snapshot_bindings import (
    read_storage_jsonl as _read_storage_jsonl,
)
from brain_alpha_ops.web_snapshot_bindings import (
    read_storage_jsonl_stats as _read_storage_jsonl_stats,
)
from brain_alpha_ops.web_snapshot_bindings import (
    research_knowledge_snapshot as _research_knowledge_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    research_memory_snapshot as _research_memory_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    research_observability_snapshot as _research_observability_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    rolling_validation_snapshot as _rolling_validation_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    save_assistant_guidance_payload as _save_assistant_guidance_payload,
)
from brain_alpha_ops.web_snapshot_bindings import (
    snapshot_facade as _snapshot_facade,
)
from brain_alpha_ops.web_snapshot_bindings import (
    snapshot_runtime as _snapshot_runtime,
)
from brain_alpha_ops.web_snapshot_bindings import (
    sqlite_expression_lookup_payload as _sqlite_expression_lookup_payload,
)
from brain_alpha_ops.web_snapshot_bindings import (
    sqlite_index_snapshot as _sqlite_index_snapshot,
)
from brain_alpha_ops.web_snapshot_bindings import (
    sqlite_record_lookup_payload as _sqlite_record_lookup_payload,
)
from brain_alpha_ops.web_snapshot_bindings import (
    storage_jsonl_path as _storage_jsonl_path,
)
from brain_alpha_ops.web_snapshot_bindings import (
    user_profile_snapshot as _user_profile_snapshot,
)

__all__ = [
    "_anti_overfit_snapshot",
    "_assistant_context_snapshot",
    "_assistant_cross_review_payload",
    "_assistant_guidance_history",
    "_assistant_guidance_snapshot",
    "_assistant_request_snapshot",
    "_assistant_response_guidance_payload",
    "_assistant_response_parse_payload",
    "_cached_user_alpha_paths",
    "_cloud_alpha_cache_probe",
    "_cloud_alpha_snapshot",
    "_cloud_alpha_summary",
    "_durable_job_rows",
    "_latest_cached_user_alpha_path",
    "_latest_cached_user_alphas",
    "_latest_result_snapshot",
    "_latest_run_history_path",
    "_load_presets",
    "_match_preset_id",
    "_official_context_file_counts",
    "_prompt_run_ledger_snapshot",
    "_public_run_config",
    "_read_official_context_json",
    "_read_official_context_metadata",
    "_read_storage_jsonl",
    "_read_storage_jsonl_stats",
    "_research_knowledge_snapshot",
    "_research_memory_snapshot",
    "_research_observability_snapshot",
    "_rolling_validation_snapshot",
    "_save_assistant_guidance_payload",
    "_snapshot_facade",
    "_snapshot_runtime",
    "_sqlite_expression_lookup_payload",
    "_sqlite_index_snapshot",
    "_sqlite_record_lookup_payload",
    "_storage_jsonl_path",
    "_user_profile_snapshot",
]

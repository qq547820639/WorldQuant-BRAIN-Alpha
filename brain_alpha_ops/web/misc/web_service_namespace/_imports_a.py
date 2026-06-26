"""Import group A for the web service namespace."""
from __future__ import annotations

import brain_alpha_ops.web_html as _web_html
import brain_alpha_ops.web_session as _web_session
from brain_alpha_ops.brain_api.context_defaults import DEFAULT_FIELDS as _DEFAULT_FIELDS
from brain_alpha_ops.brain_api.context_defaults import (
    DEFAULT_OPERATORS as _DEFAULT_OPERATORS,
)
from brain_alpha_ops.config import (
    RunConfig as _RunConfig,
)
from brain_alpha_ops.config import (
    load_run_config as _load_run_config,
)
from brain_alpha_ops.config import (
    runtime_project_root as _runtime_project_root,
)
from brain_alpha_ops.jsonl import tail_text_lines as _tail_text_lines_service
from brain_alpha_ops.observability import error_payload as _error_payload
from brain_alpha_ops.research.observability import (
    build_research_observability_snapshot as _build_research_observability_snapshot,
)
from brain_alpha_ops.research.repository import (
    ResearchRepository as _ResearchRepository,
)
from brain_alpha_ops.research.safety import SubmissionLedger as _SubmissionLedger
from brain_alpha_ops.runner import api_from_run_config as _api_from_run_config
from brain_alpha_ops.runner import run_pipeline_from_config as _run_pipeline_from_config
from brain_alpha_ops.runtime_constants import CloudDefaults as _CloudDefaults
from brain_alpha_ops.runtime_constants import SnapshotDefaults as _SnapshotDefaults
from brain_alpha_ops.runtime_constants import WebDefaults as _WebDefaults
from brain_alpha_ops.submission_readiness import (
    live_submit_readiness_hard_gate as _live_submit_readiness_hard_gate,
)
from brain_alpha_ops.task_executor import ThreadTaskExecutor as _ThreadTaskExecutor
from brain_alpha_ops.tasks import JobStore as _DurableJobStore
from brain_alpha_ops.web.handlers.sync import (
    active_job_payload as _active_job_payload,
)
from brain_alpha_ops.web.handlers.sync import (
    cloud_alpha_id as _cloud_alpha_id_service,
)
from brain_alpha_ops.web.handlers.sync import (
    cloud_row_sort_key as _cloud_row_sort_key_service,
)
from brain_alpha_ops.web.handlers.sync import (
    health_payload as _health_payload,
)
from brain_alpha_ops.web.handlers.sync import (
    job_status_payload as _job_status_payload,
)
from brain_alpha_ops.web.handlers.sync import (
    lifecycle_payload as _lifecycle_payload,
)
from brain_alpha_ops.web.handlers.sync import (
    presets_payload as _presets_payload,
)
from brain_alpha_ops.web.handlers.sync import (
    profile_payload as _profile_payload,
)
from brain_alpha_ops.web.handlers.sync import (
    run_sync_job_service as _run_sync_job_service,
)
from brain_alpha_ops.web.handlers.sync import (
    sync_cloud_alphas_payload as _sync_cloud_alphas_payload,
)
from brain_alpha_ops.web_async_jobs import (
    start_background_job_payload as _background_job_start_payload,
)
from brain_alpha_ops.web_async_jobs import progress_update as _progress_update
from brain_alpha_ops.web_async_jobs import (
    run_simple_async_job_service as _run_simple_async_job_service,
)
from brain_alpha_ops.web_candidates.check import (
    check_candidate_payload as _check_candidate_payload,
)
from brain_alpha_ops.web_candidates.generation import (
    generate_candidates_payload as _generate_candidates_payload,
)
from brain_alpha_ops.web_candidates.selection import (
    is_passed_candidate_for_check as _is_passed_candidate_for_check,
)
from brain_alpha_ops.web_candidates.selection import (
    official_alpha_id as _official_alpha_id,
)
from brain_alpha_ops.web_check_availability import (
    check_candidate_availability as _check_candidate_availability,
)
from brain_alpha_ops.web_check_availability import (
    cloud_row_expression as _cloud_row_expression,
)
from brain_alpha_ops.web_check_availability import (
    cloud_similarity_risk as _cloud_similarity_risk,
)
from brain_alpha_ops.web_check_availability import (
    cloud_status_for as _cloud_status_for,
    run_check_batch_job_service as _run_check_batch_job_service,
)
from brain_alpha_ops.web_cloud_context_refresh import (
    refresh_cloud_context_for_check_service as _refresh_cloud_context_for_check_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    cloud_alpha_cache_probe as _cloud_alpha_cache_probe_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    cloud_alpha_snapshot as _cloud_alpha_snapshot_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    cloud_alpha_summary as _cloud_alpha_summary_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    persist_official_context as _persist_official_context_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    read_official_context_json as _read_official_context_json_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    read_official_context_metadata as _read_official_context_metadata_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    read_storage_jsonl as _read_storage_jsonl_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    read_storage_jsonl_stats as _read_storage_jsonl_stats_service,
)
from brain_alpha_ops.web_cloud.snapshot import (
    storage_jsonl_path as _storage_jsonl_path_service,
)

__all__ = [name for name in dir() if not name.startswith("__")]

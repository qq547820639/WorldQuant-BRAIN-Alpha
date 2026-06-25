"""Assistant, snapshot facade, and runtime snapshots.

Subpackage that splits the original ``web_assistant_snapshots.py`` monolith
into focused modules while preserving the public API surface via re-exports.
"""
from __future__ import annotations

from ._helpers import (
    BoundedFloat,
    LoadConfig,
    PayloadTruthy,
    ReadStorageJsonl,
    RunConfigFromPayload,
    SafeErrorMessage,
    Snapshot,
    StoragePath,
    WebError,
    _bounded_float,
    _default_web_error,
    _payload_truthy,
    logger,
)
from ._research_snapshots import (
    durable_job_rows,
    prompt_run_ledger_snapshot,
    research_knowledge_snapshot,
    research_memory_snapshot,
    research_observability_snapshot,
    _prompt_run_public_row,
)
from ._assistant_guidance import (
    assistant_guidance_history,
    assistant_guidance_snapshot,
)
from ._assistant_payloads import (
    assistant_context_snapshot,
    assistant_request_snapshot,
    assistant_response_guidance_payload,
    assistant_response_parse_payload,
    save_assistant_guidance_payload,
)
from ._run_history import (
    latest_result_snapshot,
    _run_history_candidate_keys,
    _run_history_candidate_payload_rows,
    _run_history_candidate_rows,
    _run_history_candidate_total,
    _run_history_decision_action_counts,
    _run_history_expression_digest,
    _run_history_expression_key,
    _run_history_lifecycle_rows,
    _run_history_matching_lifecycle_count,
    _run_history_reason_counts,
    _run_history_replay_audit,
    _run_history_result_payload,
    _run_history_workflow_queue_counts,
)
from ._profile import (
    latest_run_history_path,
    user_profile_snapshot,
)

__all__ = [
    # Module-level
    "logger",
    # Type aliases
    "LoadConfig",
    "WebError",
    "BoundedFloat",
    "PayloadTruthy",
    "ReadStorageJsonl",
    "StoragePath",
    "SafeErrorMessage",
    "RunConfigFromPayload",
    "Snapshot",
    # Research snapshots
    "research_memory_snapshot",
    "research_knowledge_snapshot",
    "prompt_run_ledger_snapshot",
    "research_observability_snapshot",
    "durable_job_rows",
    # Assistant guidance
    "assistant_guidance_snapshot",
    "assistant_guidance_history",
    # Assistant payloads
    "assistant_context_snapshot",
    "assistant_request_snapshot",
    "assistant_response_parse_payload",
    "assistant_response_guidance_payload",
    "save_assistant_guidance_payload",
    # Run history & profile
    "latest_result_snapshot",
    "latest_run_history_path",
    "user_profile_snapshot",
]

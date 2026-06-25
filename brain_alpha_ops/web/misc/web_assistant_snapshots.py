"""Re-export from the ``web_assistant_snapshots`` subpackage for backward compatibility.

The implementation now lives in ``web_assistant_snapshots/`` submodules. This
shim keeps the original import path
(``brain_alpha_ops.web.misc.web_assistant_snapshots``) working for existing
callers and tests.
"""
from __future__ import annotations

from brain_alpha_ops.web.misc.web_assistant_snapshots import *  # noqa: F401,F403
from brain_alpha_ops.web.misc.web_assistant_snapshots import (  # noqa: F401
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
    _prompt_run_public_row,
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
    logger,
)

"""Re-export from get_routes subpackage for backward compatibility.

The original monolithic ``web_routes.py`` has been split into focused
modules under the ``get_routes`` subpackage. This shim preserves the
public API surface so that legacy imports such as::

    from brain_alpha_ops.web_routes import GET_ROUTES
    from brain_alpha_ops.web.dispatch.web_routes import _status_payload

continue to work unchanged.
"""

from __future__ import annotations

# Module-level names that the original web_routes.py imported and that tests
# patch via @patch("brain_alpha_ops.web_routes.load_run_config"). Re-importing
# them here keeps those patch targets resolvable.
from brain_alpha_ops.config import load_run_config, runtime_project_root  # noqa: F401
from brain_alpha_ops.redaction import redact_error_message  # noqa: F401

# Public API (symbols listed in get_routes.__all__).
from brain_alpha_ops.web.dispatch.get_routes import *  # noqa: F401,F403

# Explicit re-export of private symbols (underscore-prefixed) that tests
# and legacy code import via brain_alpha_ops.web_routes. These are already
# imported into the get_routes namespace by its __init__, so we re-bind
# them here to preserve the historical import paths.
from brain_alpha_ops.web.dispatch.get_routes import (  # noqa: F401
    _backtest_queue_next_action,
    _backtest_slot_limit,
    _backtest_slots_payload,
    _build_route_map,
    _candidate_high_cloud_similarity_blocked,
    _candidate_lifecycle_rows,
    _candidate_local_backtest_failed,
    _candidate_local_valid,
    _candidate_official_review_blockers,
    _candidate_score,
    _candidate_submit_evidence_blockers,
    _candidate_target_pool_size,
    _cloud_snapshot_payload,
    _durable_production_job_store,
    _get_routes,
    _handle_candidate_check,
    _handle_candidate_simulate,
    _handle_candidate_submit,
    _handle_config_update,
    _handle_pipeline_start,
    _handle_pipeline_stop,
    _is_submit_only_quality_reason,
    _iter_jsonl_records,
    _jsonl_payload,
    _jsonl_summary_payload,
    _latest_result_payload,
    _make_get_routes_proxy,
    _official_simulation_score_threshold,
    _public_config,
    _query_limit,
    _query_positive_int,
    _query_text,
    _query_truthy,
    _read_jsonl_records,
    _read_jsonl_tail,
    _slot_active,
    _slot_has_official_work_record,
    _slot_payload,
    _status_payload,
    _storage_file,
    _submit_readiness_payload,
)

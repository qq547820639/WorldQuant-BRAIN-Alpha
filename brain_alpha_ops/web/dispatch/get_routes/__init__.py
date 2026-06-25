"""GET routes subpackage for the web console.

Splits the original ``web_routes.py`` monolith into focused modules while
preserving the public API surface via re-exports.
"""

from __future__ import annotations

# Types
from ._types import Route, RouteHandler

# Dispatch functions
from ._dispatch import dispatch_get, dispatch_post

# POST route handlers
from ._post_handlers import (
    _handle_candidate_check,
    _handle_candidate_simulate,
    _handle_candidate_submit,
    _handle_config_update,
    _handle_pipeline_start,
    _handle_pipeline_stop,
)

# Data helpers
from ._helpers import (
    _backtest_slot_limit,
    _backtest_slots_payload,
    _candidate_lifecycle_rows,
    _candidate_target_pool_size,
    _cloud_snapshot_payload,
    _durable_production_job_store,
    _iter_jsonl_records,
    _jsonl_payload,
    _jsonl_summary_payload,
    _latest_result_payload,
    _official_simulation_score_threshold,
    _public_config,
    _query_limit,
    _query_positive_int,
    _query_text,
    _query_truthy,
    _read_jsonl_records,
    _read_jsonl_tail,
    _status_payload,
    _storage_file,
    _submit_readiness_payload,
)

# Route map
from ._route_map import (
    GET_ROUTES,
    POST_ROUTES,
    _build_route_map,
    _get_routes,
    _make_get_routes_proxy,
    route_for,
)

# ═══════════════════════ Backward-Compatible Test Exports ═══════════════════
# Re-export symbols from web_backtest_slots that tests import via web_routes.
from brain_alpha_ops.web.misc.web_backtest_slots import slot_payload as _slot_payload  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import slot_active as _slot_active  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import slot_has_official_work_record as _slot_has_official_work_record  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import candidate_score as _candidate_score  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import candidate_local_valid as _candidate_local_valid  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import candidate_official_review_blockers as _candidate_official_review_blockers  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import candidate_submit_evidence_blockers as _candidate_submit_evidence_blockers  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import is_submit_only_quality_reason as _is_submit_only_quality_reason  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import candidate_high_cloud_similarity_blocked as _candidate_high_cloud_similarity_blocked  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import candidate_local_backtest_failed as _candidate_local_backtest_failed  # noqa: F401
from brain_alpha_ops.web.misc.web_backtest_slots import backtest_queue_next_action as _backtest_queue_next_action  # noqa: F401

__all__ = [
    "Route",
    "RouteHandler",
    "dispatch_get",
    "dispatch_post",
    "GET_ROUTES",
    "POST_ROUTES",
    "route_for",
]

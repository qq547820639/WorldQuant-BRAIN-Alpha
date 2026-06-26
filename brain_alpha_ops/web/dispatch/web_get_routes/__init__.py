"""GET route handlers for the web console.

Contains all ``_get_*`` handler functions (37 routes) plus supporting helpers.
These handlers are imported by ``web_handler_dispatch.py`` and registered in
``_GET_DISPATCH_HANDLERS``.

This package re-exports the public API previously provided by the flat
``web_get_routes.py`` module so existing imports continue to work.
"""
from __future__ import annotations

from ._helpers import (
    _positive_query_int,
    _active_job_from_any_store,
    _job_status_from_any_store,
)
from ._routes_alpha import (
    _get_alpha_lifecycle,
    _get_cloud_alphas,
    _get_lifecycle,
    _get_latest_result,
    _get_anti_overfit,
    _get_rolling_validation,
    _get_backtest_slots,
    _get_submit_readiness,
)
from ._routes_simulation import (
    _get_status,
    _get_active_job,
    _get_stream,
    _get_sync_status,
    _get_check_status,
    _get_check_results,
    _get_candidates_simulate_eligible,
    _get_phase_state,
    _get_trends,
)
from ._routes_misc import (
    _get_root,
    _get_config,
    _get_config_schema,
    _get_capabilities,
    _get_health,
    _get_research_memory,
    _get_research_knowledge,
    _get_research_observability,
    _get_prompt_runs,
    _get_sqlite_indexes,
    _get_sqlite_expression_lookup,
    _get_sqlite_record_lookup,
    _get_assistant_context,
    _get_assistant_guidance,
    _get_assistant_request,
    _get_profile,
    _get_presets,
    _get_redline_report,
    _get_scoring_health,
    _get_checkpoint_status,
)
from ._routes_audit import _get_audit_export

__all__: list[str] = []  # handlers are private (_-prefixed)

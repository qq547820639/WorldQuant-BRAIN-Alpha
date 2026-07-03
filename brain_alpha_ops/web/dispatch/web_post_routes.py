"""POST route handlers for the web console.

Contains all ``_post_*`` handler functions (25 routes) plus supporting helpers
(``_start_sync_job``, ``_start_optimize_candidates_job``, ``_submit_with_lock``,
``_non_submit_run_payload``, ``_create_non_submit_run_job``).

These handlers are imported by ``web_handler_dispatch.py`` and registered in
``_POST_DISPATCH_HANDLERS``.
"""

from __future__ import annotations

from .post_routes import (
    _create_non_submit_run_job,
    _non_submit_run_payload,
    _post_assistant_cross_review,
    _post_assistant_guidance,
    _post_assistant_response_guidance,
    _post_assistant_response_parse,
    _post_candidates_simulate,
    _post_cancel,
    _post_check,
    _post_check_batch,
    _post_config_save,
    _post_generate_candidates,
    _post_logout,
    _post_optimize_candidates,
    _post_run,
    _post_scoring_attribution,
    _post_scoring_evaluate,
    _post_scoring_gate_decision,
    _post_scoring_multi_attribution,
    _post_session,
    _post_shutdown,
    _post_stop,
    _post_submit,
    _post_submit_batch,
    _post_sync_alphas,
    _post_sync_cancel,
    _post_sync_context_only,
    _post_test_connection,
    _post_trends,
    _start_optimize_candidates_job,
    _start_sync_job,
    _stop_or_cancel_job,
    _submit_with_lock,
)

__all__: list[str] = []

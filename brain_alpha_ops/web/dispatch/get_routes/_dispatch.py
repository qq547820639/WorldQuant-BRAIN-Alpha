"""GET and POST request dispatch functions."""

from __future__ import annotations

import json
import logging
from typing import Any

from brain_alpha_ops.config import load_run_config
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.web_backtest_slots import (
    backtest_slots_payload as _shared_backtest_slots_payload,
)
from brain_alpha_ops.web_candidates.payloads import (
    annotate_candidate_rows as _annotate_candidate_rows,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_main_pool as _candidate_main_pool,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_pool_summary as _candidate_pool_summary,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_summary as _candidate_rows_summary,
)
from brain_alpha_ops.web_candidates.payloads import (
    candidate_summary_from_iter as _candidate_rows_summary_from_iter,
)
from brain_alpha_ops.web_candidates.workflow import (
    candidate_workflow_plan as _candidate_workflow_plan,
)
from brain_alpha_ops.web_session import session_status as _web_session_status
from brain_alpha_ops.web_submit_readiness import (
    submit_readiness_payload as _build_submit_readiness_payload,
)

from ._helpers import (
    _backtest_slots_payload,
    _candidate_lifecycle_rows,
    _candidate_target_pool_size,
    _cloud_snapshot_payload,
    _iter_jsonl_records,
    _jsonl_payload,
    _latest_result_payload,
    _public_config,
    _query_limit,
    _query_text,
    _read_jsonl_records,
    _read_jsonl_tail,
    _status_payload,
    _submit_readiness_payload,
)
from ._post_handlers import (
    _handle_candidate_check,
    _handle_candidate_simulate,
    _handle_candidate_submit,
    _handle_config_update,
    _handle_pipeline_start,
    _handle_pipeline_stop,
)
from ..web_get_handlers import health_payload as _health_payload

logger = logging.getLogger(__name__)


# ═══════════════════════ GET Routes ═══════════════════════════════════
def dispatch_get(handler: Any, path: str, query: dict) -> None:
    """Dispatch GET requests to appropriate handlers."""
    # Health endpoint — no auth required
    if path == "/api/health":
        handler._send_json(_health_payload())
        return

    # Authentication gate for all other endpoints
    if not handler._has_valid_session():
        handler._send_json({"ok": False, "error_code": "AUTH_REQUIRED", "error": "session required"}, status=401)
        return

    # Session refresh (authenticated)
    if path == "/api/refresh_session":
        handler._send_json(_health_payload())
        return

    # Backtest slots
    if path == "/api/backtest_slots":
        handler._send_json(_backtest_slots_payload())
        return

    # Submit readiness
    if path == "/api/submit_readiness":
        handler._send_json(_submit_readiness_payload())
        return

    # Simulation eligibility preview
    if path == "/api/candidates/simulate/eligible":
        from brain_alpha_ops.web_candidates.simulation import (
            simulation_candidates_payload,
        )
        try:
            handler._send_json(simulation_candidates_payload(dict(query)))
        except Exception as exc:
            from brain_alpha_ops.redaction import redact_error_message
            handler._send_json({"ok": False, "error": redact_error_message(exc)}, status=500)
        return

    # Latest result (P1-2: uses dedicated _latest_result_payload so this
    # endpoint and /api/backtest_slots can evolve independently.)
    if path == "/api/latest_result":
        handler._send_json(_latest_result_payload())
        return

    # Status
    if path == "/api/status":
        handler._send_json(_status_payload(query))
        return

    # Phase state (v4.0)
    if path == "/api/phase_state":
        from brain_alpha_ops.web.handlers.phase import phase_state_payload
        from brain_alpha_ops.web_cloud.snapshot import (
            cloud_alpha_cache_probe,
            cloud_alpha_snapshot,
            official_context_file_counts,
        )
        from brain_alpha_ops.web_handler_candidate_routes import (
            candidate_ledger_summary,
        )
        try:
            handler._send_json(phase_state_payload(
                sync_jobs=getattr(handler, "SYNC_JOBS", None),
                candidate_repo=getattr(handler, "_candidate_repo", None),
                connection_tracker=getattr(handler, "_connection_tracker", None),
                readiness_service=getattr(handler, "_readiness_service", None),
                session_status=_web_session_status(getattr(handler, '_session_id_from_cookie', lambda: '')()),
                cloud_alpha_snapshot=cloud_alpha_snapshot,
                cloud_alpha_cache_probe=cloud_alpha_cache_probe,
                official_context_file_counts=official_context_file_counts,
                candidate_summary_probe=candidate_ledger_summary,
            ))
        except Exception:
            handler._send_json({"ok": True, "current_phase": "connect", "connected": False, "context_fresh": False, "candidates_count": 0, "scored_count": 0, "readiness_passed": False})
        return

    # Config
    if path == "/api/config":
        config = load_run_config()
        d = _public_config(config.to_dict() if hasattr(config, 'to_dict') else {"environment": "production"})
        handler._send_json({"ok": True, "config": d})
        return

    # Config schema
    if path == "/api/config_schema":
        handler._send_json({"ok": True, "schema": {"type": "object"}})
        return

    # Capability registry
    if path == "/api/capabilities":
        from brain_alpha_ops.web_capability_registry import build_capability_registry
        from brain_alpha_ops.web_cloud.snapshot import official_context_file_counts
        from brain_alpha_ops.web_config_schema import public_config_schema

        handler._send_json(
            build_capability_registry(
                public_config_schema=public_config_schema,
                official_context_file_counts=official_context_file_counts,
            )
        )
        return

    # Candidates
    if path == "/api/candidates":
        handler._send_json(_jsonl_payload("candidates", "candidates.jsonl", query, items_key="candidates", full_scan=True))
        return

    # Check results
    if path == "/api/check_results":
        handler._send_json(_jsonl_payload("check_results", "checks.jsonl", query, items_key="items", full_scan=True))
        return

    # Local Alpha lifecycle replay
    if path in ("/api/alpha_lifecycle", "/api/lifecycle/history"):
        from brain_alpha_ops.web_alpha_lifecycle import alpha_lifecycle_history_payload
        from brain_alpha_ops.web_cloud.snapshot import read_storage_jsonl

        def _read_lifecycle_jsonl(filename: str, *, limit: int | None = None):
            return read_storage_jsonl(filename, limit=limit, load_config=load_run_config)

        handler._send_json(alpha_lifecycle_history_payload(
            read_storage_jsonl=_read_lifecycle_jsonl,
            alpha_id=_query_text(query, "alpha_id"),
            query=_query_text(query, "query"),
            stage=_query_text(query, "stage"),
            status=_query_text(query, "status"),
            status_category_filter=_query_text(query, "status_category"),
            limit=_query_limit(query, default=250, maximum=2000),
        ))
        return

    # Cloud snapshot
    if path == "/api/snapshot/cloud":
        handler._send_json(_cloud_snapshot_payload(query))
        return

    # Generic snapshot
    if path.startswith("/api/snapshot/"):
        handler._send_json({"ok": True, "snapshot": {}})
        return

    # Serve static / HTML
    handler._serve_static(path)


# ═══════════════════════ POST Routes ══════════════════════════════════
def dispatch_post(handler: Any, path: str, body: str) -> None:
    """Dispatch POST requests to appropriate handlers."""
    # Authentication gate for all POST endpoints
    if not handler._has_valid_session():
        handler._send_json({"ok": False, "error_code": "AUTH_REQUIRED", "error": "session required"}, status=401)
        return

    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        handler._send_json({"ok": False, "error": "invalid JSON"}, status=400)
        return

    # Pipeline start
    if path == "/api/pipeline/start":
        _handle_pipeline_start(handler, payload)
        return

    # Pipeline stop
    if path == "/api/pipeline/stop":
        _handle_pipeline_stop(handler, payload)
        return

    # Config update
    if path == "/api/config":
        _handle_config_update(handler, payload)
        return

    # Candidate submission
    if path.startswith("/api/candidates/") and path.endswith("/submit"):
        _handle_candidate_submit(handler, path, payload)
        return

    # Candidate check
    if path.startswith("/api/candidates/") and path.endswith("/check"):
        _handle_candidate_check(handler, path, payload)
        return

    # BRAIN simulation - submit candidates for official BRAIN API simulation
    if path == "/api/candidates/simulate":
        _handle_candidate_simulate(handler, payload)
        return

    # Default: not found
    handler._send_json({"ok": False, "error": "not found"}, status=404)

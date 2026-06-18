"""Route definitions for the BRAIN Alpha Ops web console.

Extracted from web.py to separate HTTP routing logic from server infrastructure.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.types import (
    BacktestSlotResponse,
    CandidateListResponse,
    ConfigResponse,
    SubmissionReadinessResponse,
    WebRouteResponse,
)
from brain_alpha_ops.web_backtest_slots import (
    backtest_queue_next_action as _backtest_queue_next_action,
)
from brain_alpha_ops.web_backtest_slots import (
    backtest_slot_limit as _shared_backtest_slot_limit,
)
from brain_alpha_ops.web_backtest_slots import (
    backtest_slots_payload as _shared_backtest_slots_payload,
)
from brain_alpha_ops.web_backtest_slots import (
    candidate_high_cloud_similarity_blocked as _candidate_high_cloud_similarity_blocked,
)
from brain_alpha_ops.web_backtest_slots import (
    candidate_local_backtest_failed as _candidate_local_backtest_failed,
)
from brain_alpha_ops.web_backtest_slots import (
    candidate_local_valid as _candidate_local_valid,
)
from brain_alpha_ops.web_backtest_slots import (
    candidate_official_review_blockers as _candidate_official_review_blockers,
)
from brain_alpha_ops.web_backtest_slots import (
    candidate_score as _candidate_score,
)
from brain_alpha_ops.web_backtest_slots import (
    candidate_submit_evidence_blockers as _candidate_submit_evidence_blockers,
)
from brain_alpha_ops.web_backtest_slots import (
    is_submit_only_quality_reason as _is_submit_only_quality_reason,
)
from brain_alpha_ops.web_backtest_slots import (
    official_simulation_score_threshold as _shared_official_simulation_score_threshold,
)
from brain_alpha_ops.web_backtest_slots import (
    slot_active as _slot_active,
)
from brain_alpha_ops.web_backtest_slots import (
    slot_has_official_work_record as _slot_has_official_work_record,
)
from brain_alpha_ops.web_backtest_slots import (
    slot_payload as _slot_payload,
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

logger = logging.getLogger(__name__)


# ═══════════════════════ Route Handler Type ═══════════════════════════
RouteHandler = Callable[[Any, str, dict], None]


@dataclass(frozen=True)
class Route:
    handler: str
    requires_session: bool = True
    category: str = "api"


# ═══════════════════════ GET Routes ═══════════════════════════════════
def dispatch_get(handler: Any, path: str, query: dict) -> None:
    """Dispatch GET requests to appropriate handlers."""
    # Health and session endpoints
    if path in ("/api/health", "/api/refresh_session"):
        handler._send_json(health_payload())
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

    # Latest result
    if path == "/api/latest_result":
        slots = _backtest_slots_payload()
        handler._send_json({
            "ok": True,
            "source": "local_readonly_snapshot",
            "status": "completed",
            "result": {"summary": {"backtest_slots": slots["slots"]}},
            "progress": {"data": {"backtests": slots["slots"]}},
        })
        return

    # Status
    if path == "/api/status":
        handler._send_json(_status_payload(query))
        return

    # Phase state (v4.0)
    if path == "/api/phase_state":
        from brain_alpha_ops.web.handlers.phase import phase_state_payload
        from brain_alpha_ops.web_cloud_snapshot import (
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
        from brain_alpha_ops.web_cloud_snapshot import official_context_file_counts
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
        from brain_alpha_ops.web_cloud_snapshot import read_storage_jsonl

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


# ═══════════════════════ Route Handlers ═══════════════════════════════
def _handle_pipeline_start(handler: Any, payload: dict) -> None:
    """Handle pipeline start request."""
    import os
    import threading

    from brain_alpha_ops.redaction import redact_error_message
    from brain_alpha_ops.web_jobs import job_update, new_job_id

    job_id = new_job_id("pipeline")
    job_update(job_id, status="starting", progress={"phase": "init", "percent_complete": 0})

    # Start pipeline in background thread
    def run_pipeline():
        try:
            from brain_alpha_ops.brain_api.official import OfficialBrainAPI
            from brain_alpha_ops.config import load_run_config
            from brain_alpha_ops.research.pipeline import AlphaResearchPipeline

            config = load_run_config(payload.get("config_path"))
            ops = config.ops
            cred = config.credentials
            from brain_alpha_ops.secure_credentials import resolve_credentials
            bundle = resolve_credentials(username=cred.username, password=cred.password, token=cred.token,
                                         username_env=cred.username_env, password_env=cred.password_env, token_env=cred.token_env)
            username = bundle.username
            password = bundle.password
            token = bundle.token
            api = OfficialBrainAPI(
                config=ops.official_api,
                username=username,
                password=password,
                token=token,
                disable_proxy=True,
            )
            pipeline = AlphaResearchPipeline(config=ops, api=api)
            job_update(job_id, status="running", progress={"phase": "running", "percent_complete": 10})
            pipeline.run()
            job_update(job_id, status="completed", progress={"phase": "done", "percent_complete": 100})
        except Exception as e:
            logger.exception("Pipeline failed")
            job_update(job_id, status="failed", error=redact_error_message(e))

    threading.Thread(target=run_pipeline, daemon=True).start()
    handler._send_json({"ok": True, "job_id": job_id})


def _handle_pipeline_stop(handler: Any, payload: dict) -> None:
    """Reject direct stop request — production stop must go through the job monitor.

    The pipeline runs in a background thread managed by web_jobs. Stopping
    it requires coordinated cancellation via the job registry, not a simple
    thread termination. This endpoint returns a clear message guiding users
    to the correct stop mechanism.
    """
    handler._send_json({
        "ok": False,
        "error_code": "STOP_VIA_JOB_MONITOR",
        "error": "请通过页面上的任务监控面板停止流水线。直接停止请求已被拒绝以保护数据一致性。",
        "message": "Pipeline stop must use job monitor — direct stop rejected to protect data consistency.",
    }, status=409)


def _handle_config_update(handler: Any, payload: dict) -> None:
    """Handle config update request with validation.

    Only a whitelisted set of fields can be updated through the web UI.
    Nested dataclass fields (credentials, ops) are validated in depth by
    validate_run_config() after the update.
    """
    # Whitelist: only these top-level RunConfig fields are user-configurable.
    _CONFIG_UPDATE_WHITELIST = frozenset({"auto_submit", "credentials", "ops"})
    try:
        from brain_alpha_ops.config import (
            ConfigValidationError,
            validate_run_config,
            write_run_config,
        )
        config = load_run_config()
        # Update config with payload — only whitelisted fields
        rejected: list[str] = []
        for key, value in payload.items():
            if key not in _CONFIG_UPDATE_WHITELIST:
                rejected.append(key)
                continue
            if hasattr(config, key):
                setattr(config, key, value)
        # Validate before writing — rejects unsafe/out-of-range values
        validated = validate_run_config(config)
        write_run_config(validated)
        public = _public_config(validated.to_dict() if hasattr(validated, 'to_dict') else {"environment": "production"})
        response = {"ok": True, "message": "Config validated and saved", "config": public}
        if rejected:
            response["warnings"] = [f"字段 '{field}' 不支持通过 Web 修改，已忽略" for field in rejected]
        handler._send_json(response)
    except ConfigValidationError as e:
        message = redact_error_message(e)
        logger.warning("Config update validation failed: %s", message)
        handler._send_json({"ok": False, "error": message, "error_code": "CONFIG_VALIDATION_ERROR"}, status=400)
    except Exception as e:
        logger.exception("Config update failed")
        handler._send_json({"ok": False, "error": redact_error_message(e), "error_code": "CONFIG_UPDATE_ERROR"}, status=500)


def _handle_candidate_submit(handler: Any, path: str, payload: dict) -> None:
    """Reject legacy dynamic candidate-submit requests.

    The only supported submit surface is the Web staged readiness and
    confirmation flow; this compatibility route must not imply success.
    """
    # Extract candidate_id from path
    parts = path.split("/")
    if len(parts) >= 4:
        candidate_id = parts[3]
        handler._send_json(
            {
                "ok": False,
                "candidate_id": candidate_id,
                "error_code": "WEB_ONLY_SUBMIT_REQUIRED",
                "error": "Candidate submission must use the Web staged readiness and confirmation flow.",
            },
            status=410,
        )
    else:
        handler._send_json({"ok": False, "error": "invalid path"}, status=400)


def _handle_candidate_check(handler: Any, path: str, payload: dict) -> None:
    """Reject legacy single-candidate check in favor of batch check.

    Individual candidate checks are only meaningful with full context
    (API connection, cloud alphas, submission ledger).  Use the batch
    check endpoint (/api/check_batch) which orchestrates the complete
    check pipeline.
    """
    parts = path.split("/")
    if len(parts) >= 4:
        candidate_id = parts[3]
        handler._send_json(
            {
                "ok": False,
                "candidate_id": candidate_id,
                "error_code": "USE_BATCH_CHECK",
                "error": "请使用批量检查端点 /api/check_batch 进行候选检查。",
                "suggestion": "POST /api/check_batch with {\"expressions\": [\"<expression>\"]}",
            },
            status=410,
        )
    else:
        handler._send_json({"ok": False, "error": "candidate_id is required in path", "error_code": "VALIDATION_ERROR"}, status=400)


def _handle_candidate_simulate(handler: Any, payload: dict) -> None:
    """Start BRAIN simulation for eligible candidates."""
    from brain_alpha_ops.web_candidates.simulation import (
        simulate_candidates_job,
        simulation_candidates_payload,
    )
    from brain_alpha_ops.web_jobs import is_cancelled, job_update, new_job_id

    # Preview mode: just show eligible candidates without starting simulation
    if payload.get("preview"):
        try:
            result = simulation_candidates_payload(payload)
            handler._send_json(result)
        except Exception as exc:
            from brain_alpha_ops.redaction import redact_error_message
            handler._send_json({"ok": False, "error": redact_error_message(exc)}, status=500)
        return

    # Check for already running simulation job
    from brain_alpha_ops.web_jobs import ASYNC_JOBS, ASYNC_JOBS_LOCK
    with ASYNC_JOBS_LOCK:
        for jid, job in ASYNC_JOBS.items():
            if str(job.get("status") or "").lower() in {"queued", "pending", "running", "starting", "stopping"}:
                phase = (job.get("progress") or {}).get("phase", "")
                if "simulat" in str(phase).lower():
                    handler._send_json({
                        "ok": False,
                        "error": "已有模拟任务在运行",
                        "error_code": "CONFLICT_RUNNING",
                        "job_id": jid,
                    }, status=409)
                    return

    # Start simulation as background job. The durable JobStore-backed route uses
    # the same active initial state; keep this legacy path consistent for SSE UI.
    job_id = new_job_id("simulate")
    start_message = "正在启动官方 BRAIN 模拟任务。"
    job_update(job_id, status="running", progress={
        "phase": "simulation_starting",
        "message": start_message,
        "status_message": start_message,
        "percent": 0,
        "percent_complete": 0,
    })

    import threading
    def run_sim():
        try:
            from brain_alpha_ops.web_simulation_job import create_sim_job_store
            simulate_candidates_job(job_id, payload, job_store=create_sim_job_store(), log=logger)
        except Exception as e:
            from brain_alpha_ops.redaction import redact_error_message
            logger.exception("Simulation job %s failed", job_id)
            job_update(job_id, status="failed", error=redact_error_message(e))

    threading.Thread(target=run_sim, daemon=False).start()
    handler._send_json({
        "ok": True,
        "job_id": job_id,
        "task_id": job_id,
        "sse_url": f"/sse?job_id={job_id}",
        "status_url": f"/api/status?job_id={job_id}",
    })


# ═══════════════════════ Data Helpers ═════════════════════════════════
def _public_config(config: dict) -> dict:
    """Sanitize config for public consumption."""
    data = dict(config or {})
    credentials = data.get("credentials") if isinstance(data.get("credentials"), dict) else {}
    data["credentials"] = {
        "username": "",
        "password": "",
        "token": "",
        "username_env": credentials.get("username_env", "BRAIN_USERNAME"),
        "password_env": credentials.get("password_env", "BRAIN_PASSWORD"),
        "token_env": credentials.get("token_env", "BRAIN_TOKEN"),
    }
    return data


def _status_payload(query: dict) -> dict:
    """Get status payload for job status query."""
    from brain_alpha_ops.web_jobs import ASYNC_JOBS, ASYNC_JOBS_LOCK, job_get

    job_id = ""
    if isinstance(query, dict):
        values = query.get("job_id") or []
        job_id = str(values[0] if values else "")
    if job_id:
        row = job_get(job_id)
        if not row:
            durable_store = _durable_production_job_store()
            row = durable_store.get(job_id) if durable_store is not None else None
        if not row:
            return {"ok": False, "error": "job not found", "job_id": job_id, "status": "missing"}
        return {"ok": True, "job_id": job_id, "task_id": job_id, **row}
    with ASYNC_JOBS_LOCK:
        latest = max(ASYNC_JOBS.values(), key=lambda item: str(item.get("updated_at") or ""), default=None)
    durable_store = _durable_production_job_store()
    durable_latest = durable_store.latest_any() if durable_store is not None else None
    if durable_latest:
        durable_job_id, durable_row = durable_latest
        latest = {"job_id": durable_job_id, "task_id": durable_job_id, **durable_row}
    return {"ok": True, "status": "idle" if not latest else latest.get("status", "idle"), "latest_job": latest or {}}


def _durable_production_job_store():
    try:
        from brain_alpha_ops.web_job_bindings import job_registry_view

        return job_registry_view().jobs
    except (ImportError, AttributeError) as exc:
        logger.warning(
            "Durable production job store unavailable for status fallback: %s",
            redact_error_message(exc),
        )
        return None
    except Exception as exc:
        logger.exception(
            "Durable production job store failed unexpectedly: %s",
            redact_error_message(exc),
        )
        return None


def _query_limit(query: dict, *, default: int = 1000, maximum: int = 5000) -> int:
    """Extract limit from query parameters."""
    raw = ""
    if isinstance(query, dict):
        values = query.get("limit") or []
        raw = values[0] if values else ""
    try:
        value = int(raw or default)
    except (TypeError, ValueError):
        value = default
    return max(1, min(maximum, value))


def _query_text(query: dict, key: str) -> str:
    values = query.get(key) if isinstance(query, dict) else []
    return str(values[0] if values else "")


def _storage_file(name: str) -> Path:
    """Get storage file path."""
    try:
        return Path(load_run_config().ops.storage_dir) / name
    except Exception:
        return runtime_project_root() / "data" / name


def _read_jsonl_tail(name: str, *, limit: int) -> tuple[list[dict], int, str]:
    """Read tail of JSONL file."""
    from collections import deque

    path = _storage_file(name)
    rows: deque[dict] = deque(maxlen=max(1, int(limit)))
    total = 0
    if not path.is_file():
        return [], 0, str(path)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            total += 1
            rows.append(row)
    return list(rows), total, str(path)


def _read_jsonl_records(name: str) -> tuple[list[dict], int, str]:
    """Read all JSONL records for aggregate derivation from existing events."""
    from brain_alpha_ops.jsonl import iter_jsonl_records

    path = _storage_file(name)
    rows = list(iter_jsonl_records(path))
    return rows, len(rows), str(path)


def _jsonl_payload(source: str, filename: str, query: dict, *, items_key: str, full_scan: bool = False) -> dict:
    """Create JSONL payload response."""
    if _query_truthy(query, "summary"):
        return _jsonl_summary_payload(source, filename, items_key=items_key)
    rows, total, path = _read_jsonl_records(filename) if full_scan else _read_jsonl_tail(filename, limit=_query_limit(query))
    if filename == "candidates.jsonl":
        rows = _annotate_candidate_rows(rows, lifecycle_rows=_candidate_lifecycle_rows())
    summary = _candidate_rows_summary(rows, total=total) if filename == "candidates.jsonl" else {}
    pool_payload = (
        {
            "main_pool_candidates": _candidate_main_pool(rows, target_size=_candidate_target_pool_size()),
            "pool_summary": _candidate_pool_summary(rows, target_size=_candidate_target_pool_size()),
        }
        if filename == "candidates.jsonl"
        else {}
    )
    if filename == "candidates.jsonl":
        workflow_plan = _candidate_workflow_plan(
            rows,
            target_size=_candidate_target_pool_size(),
            main_pool=pool_payload["main_pool_candidates"],
        )
        pool_payload["workflow_plan"] = workflow_plan
        pool_payload["candidate_workflow"] = workflow_plan
    return {
        "ok": True,
        "source": source,
        "path": path,
        "summary_only": False,
        items_key: rows,
        "items": rows,
        "count": len(rows),
        "returned_count": len(rows),
        "total_count": total,
        "total": total,
        **pool_payload,
        **summary,
    }


def _jsonl_summary_payload(source: str, filename: str, *, items_key: str) -> dict:
    if filename == "candidates.jsonl":
        path = _storage_file(filename)
        rows = _annotate_candidate_rows(list(_iter_jsonl_records(filename)), lifecycle_rows=_candidate_lifecycle_rows())
        summary = _candidate_rows_summary_from_iter(rows)
        pool_payload = {
            "main_pool_candidates": [],
            "pool_summary": _candidate_pool_summary(rows, target_size=_candidate_target_pool_size()),
        }
        workflow_plan = _candidate_workflow_plan(
            rows,
            target_size=_candidate_target_pool_size(),
            main_pool=[],
        )
        pool_payload["workflow_plan"] = workflow_plan
        pool_payload["candidate_workflow"] = workflow_plan
        total = int(summary.get("candidate_count", 0) or 0)
    else:
        rows, total, path = _read_jsonl_records(filename)
        summary = {}
        pool_payload = {}
    return {
        "ok": True,
        "source": source,
        "path": str(path),
        "summary_only": True,
        items_key: [],
        "items": [],
        "count": 0,
        "returned_count": 0,
        "total_count": total,
        "total": total,
        **pool_payload,
        **summary,
    }


def _candidate_target_pool_size() -> int:
    try:
        return max(1, int(load_run_config().ops.budget.retained_alpha_pool_size or 10))
    except Exception:
        return 10


def _candidate_lifecycle_rows() -> list[dict[str, Any]]:
    try:
        rows, _total, _path = _read_jsonl_records("lifecycle.jsonl")
        return rows
    except Exception:
        logger.warning("candidate lifecycle history read failed; continuing without historical risk", exc_info=True)
        return []


def _query_truthy(query: dict, key: str) -> bool:
    values = query.get(key) if isinstance(query, dict) else []
    value = values[0] if values else ""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _iter_jsonl_records(name: str):
    from brain_alpha_ops.jsonl import iter_jsonl_records

    return iter_jsonl_records(_storage_file(name))


def _cloud_snapshot_payload(query: dict) -> dict:
    """Create cloud snapshot payload."""
    from brain_alpha_ops.web_cloud_snapshot import cloud_alpha_snapshot

    limit = _query_positive_int(query, "limit")
    snapshot = cloud_alpha_snapshot(limit=limit)
    rows = list(snapshot.get("alphas") or [])
    summary = dict(snapshot.get("summary") or {})
    return {
        "ok": True,
        "source": summary.get("source", "cloud_alphas_jsonl"),
        "summary": summary,
        "count": summary.get("count", summary.get("total")),
        "total": summary.get("total", summary.get("count")),
        "submitted_count": summary.get("submitted_count", 0),
        "passed_unsubmitted_count": summary.get("passed_unsubmitted_count", 0),
        "failed_unsubmitted_count": summary.get("failed_unsubmitted_count", 0),
        "is_stale": bool(summary.get("is_stale")),
        "alphas": rows,
        "sample_alphas": rows,
    }


def _query_positive_int(query: dict, key: str) -> int | None:
    values = query.get(key) if isinstance(query, dict) else []
    if not values:
        return None
    try:
        return max(1, int(values[0]))
    except (TypeError, ValueError):
        return None


def _backtest_slot_limit() -> int:
    return _shared_backtest_slot_limit(load_run_config)


def _backtest_slots_payload() -> dict:
    return _shared_backtest_slots_payload(_read_jsonl_records, load_config=load_run_config)


def _official_simulation_score_threshold() -> float:
    return _shared_official_simulation_score_threshold(load_run_config)


def _submit_readiness_payload() -> dict:
    """Create submit readiness payload."""
    return _build_submit_readiness_payload()

# ═══════════════════════ Backward-Compatible Test Exports ═══════════════════
# Tests written against the old monolithic web_routes.py expect GET_ROUTES,
# POST_ROUTES, and route_for symbols.  These are now provided as backward-
# compatible shims that reconstruct the route tables from the dispatch
# functions in web.py.

def _build_route_map() -> dict[str, list[tuple[str, str]]]:
    """Reconstruct GET/POST route tables for dispatch compatibility."""
    get_routes = {
        "/": Route("root", requires_session=False, category="html"),
        "/api/health": Route("health", requires_session=False),
        "/api/status": Route("status"),
        "/api/production-validation/status": Route("status"),
        "/api/config": Route("config"),
        "/api/config_schema": Route("config_schema"),
        "/api/capabilities": Route("capabilities"),
        "/api/active_job": Route("active_job"),
        "/api/latest_result": Route("latest_result"),
        "/api/stream": Route("stream"),
        "/sse": Route("stream"),
        "/api/lifecycle": Route("lifecycle"),
        "/api/alpha_lifecycle": Route("alpha_lifecycle"),
        "/api/lifecycle/history": Route("alpha_lifecycle"),
        "/api/candidates": Route("candidates"),
        "/api/candidate/list": Route("candidates"),
        "/api/cloud_alphas": Route("cloud_alphas"),
        "/api/snapshot/cloud": Route("cloud_alphas"),
        "/api/snapshot/cloud_alphas": Route("cloud_alphas"),
        "/api/research_memory": Route("research_memory"),
        "/api/snapshot/memory": Route("research_memory"),
        "/api/snapshot/research_memory": Route("research_memory"),
        "/api/research_knowledge": Route("research_knowledge"),
        "/api/research_observability": Route("research_observability"),
        "/api/snapshot/observability": Route("research_observability"),
        "/api/prompt_runs": Route("prompt_runs"),
        "/api/sqlite_indexes": Route("sqlite_indexes"),
        "/api/snapshot/sqlite_indexes": Route("sqlite_indexes"),
        "/api/sqlite_expression_lookup": Route("sqlite_expression_lookup"),
        "/api/sqlite_record_lookup": Route("sqlite_record_lookup"),
        "/api/assistant_context": Route("assistant_context"),
        "/api/snapshot/assistant_context": Route("assistant_context"),
        "/api/assistant_guidance": Route("assistant_guidance"),
        "/api/snapshot/assistant_guidance": Route("assistant_guidance"),
        "/api/assistant_request": Route("assistant_request"),
        "/api/snapshot/assistant_requests": Route("assistant_request"),
        "/api/anti_overfit": Route("anti_overfit"),
        "/api/snapshot/anti_overfit": Route("anti_overfit"),
        "/api/rolling_validation": Route("rolling_validation"),
        "/api/snapshot/rolling_validation": Route("rolling_validation"),
        "/api/sync_status": Route("sync_status"),
        "/api/check_status": Route("check_status"),
        "/api/check_results": Route("check_results"),
        "/api/profile": Route("profile"),
        "/api/presets": Route("presets"),
        "/api/redline_report": Route("redline_report"),
        "/api/scoring/health": Route("scoring_health"),
        "/api/checkpoint_status": Route("checkpoint_status"),
        "/api/backtest_slots": Route("backtest_slots"),
        "/api/submit_readiness": Route("submit_readiness"),
        "/api/candidates/simulate/eligible": Route("candidates_simulate_eligible"),
        "/api/phase_state": Route("phase_state"),
    }
    post_routes = {
        "/api/run": Route("run"),
        "/api/production-validation/start": Route("run"),
        "/api/config": Route("config"),
        "/api/config/update": Route("config"),
        "/api/test_connection": Route("test_connection"),
        "/api/connection_test": Route("test_connection"),
        "/api/stop": Route("stop"),
        "/api/production-validation/stop": Route("stop"),
        "/api/cancel": Route("cancel"),
        "/api/sync_alphas": Route("sync_alphas"),
        "/api/sync-cloud-alphas": Route("sync_alphas"),          # R-02: legacy alias
        "/api/sync/sync_alphas": Route("sync_alphas"),
        "/api/sync_context_only": Route("sync_context_only"),
        "/api/sync_cancel": Route("sync_cancel"),
        "/api/check": Route("check"),
        "/api/candidate/check": Route("check"),
        "/api/generate_candidates": Route("generate_candidates"),
        "/api/generate": Route("generate_candidates"),
        "/api/candidates/optimize": Route("optimize_candidates"),
        "/api/candidate/optimize": Route("optimize_candidates"),
        "/api/check_batch": Route("check_batch"),
        "/api/submit": Route("submit"),
        "/api/candidate/submit": Route("submit"),
        "/api/submit_batch": Route("submit_batch"),
        "/api/assistant/parse": Route("assistant_response_parse"),
        "/api/assistant_response/parse": Route("assistant_response_parse"),
        "/api/assistant_response_parse": Route("assistant_response_parse"),
        "/api/assistant/guidance": Route("assistant_response_guidance"),
        "/api/assistant_response_guidance": Route("assistant_response_guidance"),
        "/api/assistant/cross_review": Route("assistant_cross_review"),
        "/api/assistant_cross_review": Route("assistant_cross_review"),
        "/api/assistant_guidance": Route("assistant_guidance"),
        "/api/logout": Route("logout"),
        "/api/shutdown": Route("shutdown"),
        "/api/scoring/evaluate": Route("scoring_evaluate"),
        "/api/scoring/attribution": Route("scoring_attribution"),
        "/api/candidates/simulate": Route("candidates_simulate"),
        "/api/session": Route("session", requires_session=False),    # R-02: creates new session
    }
    return {"GET": get_routes, "POST": post_routes}

_route_map = None
_get_routes_cache = None

def _get_routes():
    """Lazy load route tables to avoid circular imports."""
    global _get_routes_cache
    if _get_routes_cache is not None:
        return _get_routes_cache
    m = _build_route_map()
    _get_routes_cache = (dict(m["GET"]), dict(m["POST"]))
    return _get_routes_cache

def _make_get_routes_proxy(kind: str):
    """Create a dict-like proxy that lazily loads the route table."""
    class _RouteProxy(dict):
        def __init__(self):
            pass  # Don't call super().__init__() — load lazily
        def _load(self):
            if not dict.__len__(self):
                g, p = _get_routes()
                d = g if kind == "GET" else p
                dict.update(self, d)
        def __getitem__(self, key):
            self._load()
            return dict.__getitem__(self, key)
        def __contains__(self, key):
            self._load()
            return dict.__contains__(self, key)
        def get(self, key, default=None):
            self._load()
            return dict.get(self, key, default)
        def keys(self):
            self._load()
            return dict.keys(self)
        def items(self):
            self._load()
            return dict.items(self)
        def values(self):
            self._load()
            return dict.values(self)
        def __len__(self):
            self._load()
            return dict.__len__(self)
        def __iter__(self):
            self._load()
            return dict.__iter__(self)
    return _RouteProxy()

GET_ROUTES = _make_get_routes_proxy("GET")
POST_ROUTES = _make_get_routes_proxy("POST")

def route_for(method: str, path: str) -> Route | None:
    """Backward-compatible route lookup."""
    g, p = _get_routes()
    _map = {"GET": g, "POST": p}.get(method.upper(), {})
    return _map.get(path)

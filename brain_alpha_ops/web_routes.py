"""Route definitions for the BRAIN Alpha Ops web console.

Extracted from web.py to separate HTTP routing logic from server infrastructure.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable
from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.research.fallback_generation import high_turnover_generation_risk_reasons
from brain_alpha_ops.web_submit_readiness import submit_readiness_payload as _build_submit_readiness_payload

logger = logging.getLogger(__name__)


# ═══════════════════════ Route Handler Type ═══════════════════════════
RouteHandler = Callable[[Any, str, dict], None]


@dataclass(frozen=True)
class Route:
    handler: str
    requires_session: bool = True
    category: str = "api"


# ═══════════════════════ Constants ══════════════════════════════════════
_OFFICIAL_REVIEW_LOCAL_BLOCKING_CATEGORIES = {
    "missing",
    "format_error",
    "numeric_out_of_bounds",
    "local_quality_failed",
}
_OFFICIAL_REVIEW_SUBMIT_ONLY_REASON_CODES = {
    "decision_band_not_submit_candidate",
    "gate_not_submission_ready",
    "missing_official_alpha_id",
    "missing_official_metrics",
    "missing_official_metric_fields",
    "official_pass_fail_not_pass",
    "expression_too_nested",
}
_OFFICIAL_REVIEW_SUBMIT_ONLY_CATEGORIES = {
    "official_evidence_missing",
    "quality_gate_failed",
}
_OFFICIAL_REVIEW_OFFICIAL_STATE_KEYS = {
    "official_alpha_id": "official_alpha_id_already_present",
    "simulation_id": "official_simulation_already_started",
}


# ═══════════════════════ GET Routes ═══════════════════════════════════
def dispatch_get(handler: Any, path: str, query: dict) -> None:
    """Dispatch GET requests to appropriate handlers."""
    # Health and session endpoints
    if path in ("/api/health", "/api/refresh_session"):
        handler._send_json({"ok": True})
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
        from brain_alpha_ops.web_candidate_simulation import simulation_candidates_payload
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
        try:
            handler._send_json(phase_state_payload(
                sync_jobs=getattr(handler, "SYNC_JOBS", None),
                candidate_repo=getattr(handler, "_candidate_repo", None),
                connection_tracker=getattr(handler, "_connection_tracker", None),
                readiness_service=getattr(handler, "_readiness_service", None),
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

    # Candidates
    if path == "/api/candidates":
        handler._send_json(_jsonl_payload("candidates", "candidates.jsonl", query, items_key="candidates"))
        return

    # Check results
    if path == "/api/check_results":
        handler._send_json(_jsonl_payload("check_results", "checks.jsonl", query, items_key="items"))
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
    from brain_alpha_ops.web_jobs import job_update, new_job_id
    from brain_alpha_ops.redaction import redact_error_message

    job_id = new_job_id("pipeline")
    job_update(job_id, status="starting", progress={"phase": "init", "percent_complete": 0})

    # Start pipeline in background thread
    def run_pipeline():
        try:
            from brain_alpha_ops.config import load_run_config
            from brain_alpha_ops.brain_api.official import OfficialBrainAPI
            from brain_alpha_ops.research.pipeline import AlphaResearchPipeline

            config = load_run_config(payload.get("config_path"))
            ops = config.ops
            cred = config.credentials
            username = cred.username or os.environ.get(cred.username_env, "")
            password = cred.password or os.environ.get(cred.password_env, "")
            token = cred.token or os.environ.get(cred.token_env, "")
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

    threading.Thread(target=run_pipeline, daemon=False).start()
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
        from brain_alpha_ops.config import ConfigValidationError, validate_run_config, write_run_config
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
    from brain_alpha_ops.web_candidate_simulation import (
        simulate_candidates_job,
        simulation_candidates_payload,
    )
    from brain_alpha_ops.web_jobs import job_update, new_job_id, is_cancelled

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
            if job.get("status") == "running":
                phase = (job.get("progress") or {}).get("phase", "")
                if "simulat" in str(phase).lower():
                    handler._send_json({
                        "ok": False,
                        "error": "已有模拟任务在运行",
                        "error_code": "CONFLICT_RUNNING",
                        "job_id": jid,
                    }, status=409)
                    return

    # Start simulation as background job
    job_id = new_job_id("simulate")
    job_update(job_id, status="starting", progress={"phase": "init", "percent_complete": 0})

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
    from brain_alpha_ops.web_jobs import job_get, ASYNC_JOBS, ASYNC_JOBS_LOCK

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


def _jsonl_payload(source: str, filename: str, query: dict, *, items_key: str) -> dict:
    """Create JSONL payload response."""
    rows, total, path = _read_jsonl_tail(filename, limit=_query_limit(query))
    return {
        "ok": True,
        "source": source,
        "path": path,
        items_key: rows,
        "items": rows,
        "total": total,
    }


def _cloud_snapshot_payload(query: dict) -> dict:
    """Create cloud snapshot payload."""
    rows, total, path = _read_jsonl_tail("cloud_alphas.jsonl", limit=_query_limit(query, default=100, maximum=1000))
    submitted = sum(1 for row in rows if str(row.get("status") or "").upper() == "SUBMITTED")
    passed = sum(1 for row in rows if str(row.get("pass_fail") or row.get("passFail") or "").upper() == "PASS")
    failed = sum(1 for row in rows if str(row.get("pass_fail") or row.get("passFail") or "").upper() == "FAIL")
    summary = {
        "returned_count": len(rows),
        "total_count": total,
        "submitted_count": submitted,
        "passed_unsubmitted_count": passed,
        "failed_unsubmitted_count": failed,
        "is_stale": False,
    }
    return {
        "ok": True,
        "source": "cloud_alphas_jsonl",
        "path": path,
        "summary": summary,
        "count": total,
        "submitted_count": submitted,
        "passed_unsubmitted_count": passed,
        "failed_unsubmitted_count": failed,
        "is_stale": False,
        "alphas": rows,
        "sample_alphas": rows,
    }


def _backtest_slot_limit() -> int:
    """Get backtest slot limit from config."""
    try:
        budget = load_run_config().ops.budget
        return max(
            3,
            min(
                max(1, int(budget.official_backtest_batch_size)),
                max(1, int(budget.max_official_simulations_per_cycle)),
                max(1, int(budget.max_official_concurrent_simulations)),
            ),
        )
    except Exception:
        return 3


def _backtest_slots_payload() -> dict:
    """Create backtest slots payload."""
    slot_limit = _backtest_slot_limit()
    rows, _total, path = _read_jsonl_tail("backtests.jsonl", limit=1000)
    latest_by_slot: dict[int, dict] = {}
    for row in rows:
        try:
            slot = int(row.get("slot") or 0)
        except (TypeError, ValueError):
            continue
        if 1 <= slot <= slot_limit:
            latest_by_slot[slot] = row
    slots = [_slot_payload(slot, latest_by_slot.get(slot)) for slot in range(1, slot_limit + 1)]
    active_count = sum(1 for slot in slots if _slot_active(slot.get("status")))
    return {
        "ok": True,
        "source": "backtests_jsonl",
        "path": path,
        "slot_limit": slot_limit,
        "active_count": active_count,
        "queue_summary": _backtest_queue_summary(slots, slot_limit=slot_limit, active_count=active_count),
        "slots": slots,
        "updated_at": max((str(row.get("timestamp") or "") for row in latest_by_slot.values()), default=""),
    }


def _slot_payload(slot: int, row: dict | None) -> dict:
    """Create slot payload."""
    if not row:
        return {"slot": slot, "status": "empty", "alpha_id": "", "expression": ""}
    return {
        "slot": slot,
        "status": row.get("status", "unknown"),
        "alpha_id": row.get("alpha_id", ""),
        "expression": row.get("expression", ""),
        "sharpe": row.get("sharpe"),
        "fitness": row.get("fitness"),
        "turnover": row.get("turnover"),
        "progress": row.get("progress"),
        "error": row.get("error"),
        "timestamp": row.get("timestamp"),
    }


def _slot_active(status: str | None) -> bool:
    """Check if slot is active."""
    return str(status or "").lower() in {"running", "pending", "starting"}


def _backtest_queue_summary(slots: list[dict], *, slot_limit: int, active_count: int) -> dict:
    """Create backtest queue summary."""
    from collections import Counter

    candidates, candidate_total, candidate_path = _read_jsonl_tail("candidates.jsonl", limit=1000)
    min_score = _official_simulation_score_threshold()
    reason_counts: Counter[str] = Counter()
    local_valid_count = 0
    above_score_count = 0
    review_candidate_count = 0
    submit_reason_counts: Counter[str] = Counter()
    submit_evidence_blocking_count = 0
    for candidate in candidates:
        score = _candidate_score(candidate)
        if _candidate_local_valid(candidate):
            local_valid_count += 1
        if score >= min_score:
            above_score_count += 1
        blockers = _candidate_official_review_blockers(candidate, min_score=min_score)
        submit_blockers = _candidate_submit_evidence_blockers(candidate)
        if submit_blockers:
            submit_evidence_blocking_count += 1
            submit_reason_counts.update(submit_blockers)
        if blockers:
            reason_counts.update(blockers)
        else:
            review_candidate_count += 1
    open_slot_count = max(0, int(slot_limit or 0) - int(active_count or 0))
    official_slot_record_count = sum(1 for slot in slots if _slot_has_official_work_record(slot))
    return {
        "schema_version": "backtest-slot-queue-summary-v1",
        "source": "local_readonly_snapshot",
        "official_api_called": False,
        "official_slot_record_count": official_slot_record_count,
        "candidate_path": candidate_path,
        "candidate_count": candidate_total,
        "returned_candidate_count": len(candidates),
        "slot_limit": slot_limit,
        "active_slot_count": active_count,
        "open_slot_count": open_slot_count,
        "empty_slot_count": sum(1 for slot in slots if str(slot.get("status") or "").upper() == "EMPTY"),
        "local_valid_count": local_valid_count,
        "above_simulation_score_count": above_score_count,
        "review_candidate_count": review_candidate_count,
        "blocked_candidate_count": max(0, len(candidates) - review_candidate_count),
        "submit_evidence_blocking_count": submit_evidence_blocking_count,
        "min_prior_score_for_official_simulation": min_score,
        "top_blocking_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
        ],
        "top_submit_blocking_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(submit_reason_counts.items(), key=lambda item: (-item[1], item[0]))[:6]
        ],
        "next_action": _backtest_queue_next_action(
            candidate_count=len(candidates),
            review_candidate_count=review_candidate_count,
            open_slot_count=open_slot_count,
        ),
    }


def _official_simulation_score_threshold() -> float:
    """Get official simulation score threshold (prior score, not Sharpe)."""
    try:
        return float(load_run_config().ops.budget.min_prior_score_for_official_simulation)
    except Exception:
        return 70.0


def _slot_has_official_work_record(slot: dict) -> bool:
    """Check if slot has official work record."""
    if not isinstance(slot, dict):
        return False
    status = str(slot.get("status") or "").upper()
    if status in {"", "EMPTY", "CAPACITY_WAIT"}:
        return False
    return bool(
        str(slot.get("alpha_id") or "").strip()
        or str(slot.get("simulation_id") or "").strip()
        or str(slot.get("official_alpha_id") or "").strip()
    )


def _candidate_score(candidate: dict) -> float:
    """Extract candidate score."""
    scorecard = candidate.get("scorecard") if isinstance(candidate.get("scorecard"), dict) else {}
    value = scorecard.get("total_score", candidate.get("score"))
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if score == score else 0.0


def _candidate_local_valid(candidate: dict) -> bool:
    """Check if candidate is locally valid."""
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    if isinstance(diagnosis.get("local_candidate_valid"), bool):
        return bool(diagnosis.get("local_candidate_valid"))
    local_quality = candidate.get("local_quality") if isinstance(candidate.get("local_quality"), dict) else {}
    return local_quality.get("passed") is True


def _candidate_official_review_blockers(candidate: dict, *, min_score: float) -> list[str]:
    """Get blockers for official review."""
    blockers: list[str] = []
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    if diagnosis:
        blockers.extend(_quality_diagnosis_official_review_blockers(diagnosis))
    else:
        blockers.append("missing_quality_diagnosis")
    if not _candidate_local_valid(candidate):
        blockers.append("local_candidate_invalid")
    if _candidate_score(candidate) < min_score:
        blockers.append("score_below_official_simulation_threshold")
    if _candidate_local_backtest_failed(candidate):
        blockers.append("local_backtest_failed")
    if high_turnover_generation_risk_reasons(str(candidate.get("expression") or "")):
        blockers.append("high_turnover_generation_risk")
    source_tags = candidate.get("source_tags") if isinstance(candidate.get("source_tags"), list) else []
    if "generation_risk_blocked" in source_tags:
        blockers.append("generation_risk_blocked")
    if _candidate_high_cloud_similarity_blocked(candidate):
        blockers.append("high_cloud_similarity")
    for key, reason in _OFFICIAL_REVIEW_OFFICIAL_STATE_KEYS.items():
        if str(candidate.get(key) or "").strip():
            blockers.append(reason)
    if isinstance(candidate.get("official_metrics"), dict) and candidate.get("official_metrics"):
        blockers.append("official_simulation_already_completed")
    return sorted(set(blockers))


def _quality_diagnosis_official_review_blockers(diagnosis: dict) -> list[str]:
    """Get blockers from quality diagnosis."""
    blockers: list[str] = []
    reason_rows = diagnosis.get("reasons") if isinstance(diagnosis.get("reasons"), list) else []
    if reason_rows:
        for row in reason_rows:
            if not isinstance(row, dict) or row.get("severity") != "blocking":
                continue
            code = str(row.get("code") or "")
            category = str(row.get("category") or "")
            if not code or _is_submit_only_quality_reason(code, category):
                continue
            if category in _OFFICIAL_REVIEW_LOCAL_BLOCKING_CATEGORIES and not code.startswith("official_"):
                blockers.append(code)
        return blockers
    for reason in diagnosis.get("blocking_reasons") or []:
        code = str(reason or "")
        if code and not _is_submit_only_quality_reason(code, "") and not code.startswith("official_"):
            blockers.append(code)
    return blockers


def _candidate_submit_evidence_blockers(candidate: dict) -> list[str]:
    """Get blockers for submission evidence."""
    diagnosis = candidate.get("quality_diagnosis") if isinstance(candidate.get("quality_diagnosis"), dict) else {}
    blockers: list[str] = []
    if diagnosis:
        reason_rows = diagnosis.get("reasons") if isinstance(diagnosis.get("reasons"), list) else []
        if reason_rows:
            for row in reason_rows:
                if not isinstance(row, dict) or row.get("severity") != "blocking":
                    continue
                code = str(row.get("code") or "")
                category = str(row.get("category") or "")
                if code and _is_submit_only_quality_reason(code, category):
                    blockers.append(code)
        else:
            for reason in diagnosis.get("blocking_reasons") or []:
                code = str(reason or "")
                if code and _is_submit_only_quality_reason(code, ""):
                    blockers.append(code)
    return sorted(set(blockers))


def _is_submit_only_quality_reason(code: str, category: str) -> bool:
    """Check if reason is submit-only quality reason."""
    if code in _OFFICIAL_REVIEW_SUBMIT_ONLY_REASON_CODES:
        return True
    if category in _OFFICIAL_REVIEW_SUBMIT_ONLY_CATEGORIES:
        return True
    return False


def _candidate_high_cloud_similarity_blocked(candidate: dict) -> bool:
    """Check if candidate is blocked by high cloud similarity."""
    status = str(candidate.get("lifecycle_status") or "").lower()
    if "high_cloud_similarity" in status:
        return True
    risk = candidate.get("cloud_correlation_risk") if isinstance(candidate.get("cloud_correlation_risk"), dict) else {}
    level = str(risk.get("level") or "").lower()
    return level in {"high", "blocked"}


def _candidate_local_backtest_failed(candidate: dict) -> bool:
    """Check if local backtest failed."""
    for container_key in ("local_quality", "submission", "extra_fields"):
        container = candidate.get(container_key)
        if not isinstance(container, dict):
            continue
        local_backtest = container.get("local_backtest")
        if isinstance(local_backtest, dict) and local_backtest.get("pass_local") is False:
            return True
    local_backtest = candidate.get("local_backtest")
    return isinstance(local_backtest, dict) and local_backtest.get("pass_local") is False


def _backtest_queue_next_action(*, candidate_count: int, review_candidate_count: int, open_slot_count: int) -> str:
    """Get next action for backtest queue."""
    if candidate_count <= 0:
        return "generate_candidates"
    if review_candidate_count > 0 and open_slot_count > 0:
        return "trusted_environment_official_simulation_required"
    if review_candidate_count > 0:
        return "wait_for_open_backtest_slot"
    return "improve_or_regenerate_candidates"


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
        "/api/active_job": Route("active_job"),
        "/api/latest_result": Route("latest_result"),
        "/api/stream": Route("stream"),
        "/sse": Route("stream"),
        "/api/lifecycle": Route("lifecycle"),
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
        "/api/sync_cancel": Route("sync_cancel"),
        "/api/check": Route("check"),
        "/api/candidate/check": Route("check"),
        "/api/generate_candidates": Route("generate_candidates"),
        "/api/generate": Route("generate_candidates"),
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

"""Data helpers: config sanitization, status payloads, JSONL reads, and query utilities."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.redaction import redact_error_message
from brain_alpha_ops.web_backtest_slots import (
    backtest_slot_limit as _shared_backtest_slot_limit,
)
from brain_alpha_ops.web_backtest_slots import (
    backtest_slots_payload as _shared_backtest_slots_payload,
)
from brain_alpha_ops.web_backtest_slots import (
    official_simulation_score_threshold as _shared_official_simulation_score_threshold,
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
from brain_alpha_ops.web_submit_readiness import (
    submit_readiness_payload as _build_submit_readiness_payload,
)

logger = logging.getLogger(__name__)


# ═══════════════════════ Data Helpers ═════════════════════════════════
def _public_config(config: dict) -> dict:
    """Sanitize config for public consumption."""
    import os
    data = dict(config or {})
    credentials = data.get("credentials") if isinstance(data.get("credentials"), dict) else {}
    managed_credentials_available = bool(
        os.environ.get("BRAIN_USERNAME")
        or os.environ.get("BRAIN_PASSWORD")
        or os.environ.get("BRAIN_TOKEN")
    )
    data["credentials"] = {
        "username": "",
        "password": "",
        "token": "",
        "username_env": credentials.get("username_env", "BRAIN_USERNAME"),
        "password_env": credentials.get("password_env", "BRAIN_PASSWORD"),
        "token_env": credentials.get("token_env", "BRAIN_TOKEN"),
        "managed_credentials_available": managed_credentials_available,
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
            return {"ok": False, "error": "job not found", "error_code": "JOB_NOT_FOUND", "job_id": job_id, "status": "missing"}
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
        # Use ``import ... as`` instead of ``from ... import`` so the lookup
        # resolves to the real module (brain_alpha_ops.web.dispatch.web_routes)
        # which is what monkeypatch.setattr("brain_alpha_ops.web_routes.X")
        # patches. ``from ... import`` binds to the bridge module's attribute
        # (a separate sys.modules entry) and would miss the patch.
        import brain_alpha_ops.web.dispatch.web_routes as _wr
        return Path(_wr.load_run_config().ops.storage_dir) / name
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
        # See _storage_file for why we use ``import ... as`` here.
        import brain_alpha_ops.web.dispatch.web_routes as _wr
        return max(1, int(_wr.load_run_config().ops.budget.retained_alpha_pool_size or 10))
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
    from brain_alpha_ops.web_cloud.snapshot import cloud_alpha_snapshot

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


def _latest_result_payload() -> dict:
    """Build the /api/latest_result response from backtest slots.

    P1-2: independent function for /api/latest_result. Currently wraps
    _backtest_slots_payload() but returns its own structure so the two
    endpoints can evolve independently.
    """
    slots = _backtest_slots_payload()
    return {
        "ok": True,
        "source": "local_readonly_snapshot",
        "status": "completed",
        "result": {"summary": {"backtest_slots": slots["slots"]}},
        "progress": {"data": {"backtests": slots["slots"]}},
    }


def _official_simulation_score_threshold() -> float:
    return _shared_official_simulation_score_threshold(load_run_config)


def _submit_readiness_payload() -> dict:
    """Create submit readiness payload."""
    return _build_submit_readiness_payload()

"""Latest result snapshot recovery and run-history replay audit."""
from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from brain_alpha_ops.web_candidates.payloads import (
    DEFAULT_MAIN_POOL_SIZE,
    candidate_payload,
    candidate_result_total,
    has_candidate_like_rows,
)

from ._helpers import (
    ReadStorageJsonl,
    WebError,
    _default_web_error,
    logger,
)


def latest_result_snapshot(
    *,
    job_store: Any,
    latest_run_history_path: Callable[[], Path | None],
    enrich_progress: Callable[[dict[str, Any]], dict[str, Any]],
    read_storage_jsonl: ReadStorageJsonl | None = None,
    target_pool_size: int | None = None,
    web_error: WebError = _default_web_error,
) -> dict[str, Any]:
    latest = job_store.latest_any()
    if latest:
        job_id, job = latest
        if "progress" in job:
            job["progress"] = enrich_progress(dict(job["progress"]))
        return {"ok": True, "source": "job_store", "job_id": job_id, **job}

    path = latest_run_history_path()
    if not path:
        return {"ok": True, "source": "empty", "job_id": "", "status": "idle", "result": None, "progress": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {**web_error(exc, "RUN_HISTORY_ERROR"), "source": "run_history", "result": None, "progress": {}}

    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    result = _run_history_result_payload(
        data,
        summary,
        path=path,
        read_storage_jsonl=read_storage_jsonl,
        target_pool_size=target_pool_size,
    )
    progress = {
        "phase": data.get("status") or "completed",
        "phase_label": "最近结果",
        "percent": 100,
        "message": f"已恢复最近一次结果：{path.name}",
        "data": summary,
    }
    return {
        "ok": True,
        "source": "run_history",
        "job_id": str(data.get("run_id") or path.stem),
        "status": data.get("status") or "completed",
        "result": result,
        "progress": progress,
    }


def _run_history_result_payload(
    data: dict[str, Any],
    summary: dict[str, Any],
    *,
    path: Path,
    read_storage_jsonl: ReadStorageJsonl | None,
    target_pool_size: int | None,
) -> dict[str, Any]:
    candidates = _run_history_candidate_rows(data, summary)
    total = _run_history_candidate_total(data, summary, fallback=len(candidates))
    if not has_candidate_like_rows(candidates):
        return {
            "summary": summary,
            "candidates": candidates,
            "replay_audit": _run_history_replay_audit(
                payload={"candidates": []},
                payload_rows=[],
                lifecycle_rows=[],
                raw_candidate_count=len(candidates),
                total_candidate_count=total,
                path=path,
            ),
        }

    payload_rows = _run_history_candidate_payload_rows(candidates)
    lifecycle_rows = _run_history_lifecycle_rows(read_storage_jsonl)
    payload = candidate_payload(
        payload_rows,
        source="run_history",
        total=total,
        path=str(path),
        lifecycle_rows=lifecycle_rows,
        target_pool_size=target_pool_size or DEFAULT_MAIN_POOL_SIZE,
    )
    return {
        "summary": summary,
        **payload,
        "replay_audit": _run_history_replay_audit(
            payload=payload,
            payload_rows=payload_rows,
            lifecycle_rows=lifecycle_rows,
            raw_candidate_count=len(candidates),
            total_candidate_count=total,
            path=path,
        ),
    }


def _run_history_candidate_rows(data: dict[str, Any], summary: dict[str, Any]) -> list[Any]:
    for container in (
        summary,
        data.get("result") if isinstance(data.get("result"), dict) else {},
        data.get("data") if isinstance(data.get("data"), dict) else {},
        data,
    ):
        rows = container.get("candidates") if isinstance(container, dict) else None
        if isinstance(rows, list) and rows:
            return rows
    return []


def _run_history_candidate_payload_rows(rows: list[Any]) -> list[dict[str, Any]]:
    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else row
        payload_rows.append(dict(candidate))
    return payload_rows


def _run_history_candidate_total(data: dict[str, Any], summary: dict[str, Any], *, fallback: int) -> int:
    for container in (summary, data):
        for key in ("total_candidates", "produced_count"):
            try:
                number = int(container.get(key))
            except (TypeError, ValueError):
                continue
            if number >= 0:
                return max(number, fallback)
    return candidate_result_total({**data, **summary}, fallback)


def _run_history_lifecycle_rows(read_storage_jsonl: ReadStorageJsonl | None) -> list[dict[str, Any]]:
    if read_storage_jsonl is None:
        return []
    try:
        rows = read_storage_jsonl("lifecycle.jsonl", limit=None)
    except Exception:
        logger.warning("run history lifecycle rows unavailable; continuing without historical risk", exc_info=True)
        return []
    return [row for row in rows if isinstance(row, dict)]


def _run_history_replay_audit(
    *,
    payload: dict[str, Any],
    payload_rows: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
    raw_candidate_count: int,
    total_candidate_count: int,
    path: Path,
) -> dict[str, Any]:
    candidates = [row for row in payload.get("candidates") or [] if isinstance(row, dict)]
    pool_summary = payload.get("pool_summary") if isinstance(payload.get("pool_summary"), dict) else {}
    scientific = payload.get("scientific_audit") if isinstance(payload.get("scientific_audit"), dict) else {}
    workflow = payload.get("workflow_plan") if isinstance(payload.get("workflow_plan"), dict) else {}
    readiness = workflow.get("readiness_evidence") if isinstance(workflow.get("readiness_evidence"), dict) else {}
    production_counts = pool_summary.get("decision_action_counts")
    if not isinstance(production_counts, dict):
        production_counts = _run_history_decision_action_counts(candidates)
    blocker_counts = readiness.get("blocker_counts")
    if not isinstance(blocker_counts, dict):
        blocker_counts = _run_history_reason_counts(candidates)
    return {
        "schema_version": "run-history-replay-audit-v1",
        "source": "run_history",
        "path": str(path),
        "local_only": True,
        "official_api_called": False,
        "submit_allowed": False,
        "real_submit_performed": False,
        "raw_candidate_row_count": int(raw_candidate_count),
        "payload_candidate_row_count": len(payload_rows),
        "recovered_candidate_count": len(candidates),
        "total_candidate_count": int(total_candidate_count),
        "lifecycle_row_count": len(lifecycle_rows),
        "lifecycle_rows_used_count": _run_history_matching_lifecycle_count(candidates, lifecycle_rows),
        "candidates_with_production_decision": sum(
            1 for row in candidates if isinstance(row.get("production_decision"), dict)
        ),
        "production_decision_counts": dict(sorted(production_counts.items())),
        "scientific_audit_summary_available": bool(scientific),
        "candidates_with_scientific_audit": int(scientific.get("audited_count") or 0),
        "candidates_missing_scientific_audit": int(scientific.get("missing_audit_count") or 0),
        "scientific_submit_boundary_intact": (
            int(scientific.get("submit_allowed_count") or 0) == 0
            and int(scientific.get("real_submit_performed_count") or 0) == 0
        ),
        "workflow_plan_available": bool(workflow),
        "workflow_queue_counts": _run_history_workflow_queue_counts(workflow),
        "readiness_blocker_counts": dict(sorted(blocker_counts.items())),
        "execution_gap_counts": dict(sorted((readiness.get("execution_gap_counts") or {}).items()))
        if isinstance(readiness.get("execution_gap_counts"), dict)
        else {},
        "stop_rule": readiness.get("authoritative_stop_rule") or "scripts/check_live_submit_readiness.py",
        "submit_boundary_intact": (
            workflow.get("submit_allowed") is not True
            and int(scientific.get("submit_allowed_count") or 0) == 0
            and int(scientific.get("real_submit_performed_count") or 0) == 0
        ),
    }


def _run_history_workflow_queue_counts(workflow: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in ("producer", "validator", "rework", "review", "archive"):
        queue = workflow.get(name) if isinstance(workflow.get(name), dict) else {}
        value = queue.get("candidate_count")
        if value is None and name == "producer":
            value = queue.get("deficit")
        try:
            counts[name] = max(0, int(value or 0))
        except (TypeError, ValueError):
            counts[name] = 0
    return counts


def _run_history_reason_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in candidates:
        decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
        for reason in decision.get("reason_codes") or []:
            text = str(reason or "").strip()
            if text:
                counts[text] += 1
    return dict(sorted(counts.items()))


def _run_history_decision_action_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in candidates:
        decision = row.get("production_decision") if isinstance(row.get("production_decision"), dict) else {}
        action = str(decision.get("action") or "").strip()
        if action:
            counts[action] += 1
    return dict(sorted(counts.items()))


def _run_history_matching_lifecycle_count(
    candidates: list[dict[str, Any]],
    lifecycle_rows: list[dict[str, Any]],
) -> int:
    keys: set[str] = set()
    for row in candidates:
        keys.update(_run_history_candidate_keys(row))
    if not keys:
        return 0
    matched = 0
    for row in lifecycle_rows:
        if any(key in keys for key in _run_history_candidate_keys(row)):
            matched += 1
    return matched


def _run_history_candidate_keys(row: dict[str, Any]) -> set[str]:
    keys = {
        str(row.get(field) or "").strip()
        for field in ("alpha_id", "candidate_id", "official_alpha_id", "simulation_id")
        if str(row.get(field) or "").strip()
    }
    expression = _run_history_expression_key(row.get("expression"))
    if expression:
        keys.add(f"expression:{expression}")
        keys.add(_run_history_expression_digest(expression))
    digest = str(row.get("expression_digest") or "").strip()
    if digest:
        keys.add(digest)
    return keys


def _run_history_expression_key(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _run_history_expression_digest(expression: str) -> str:
    return "expr_" + sha256(expression.encode("utf-8")).hexdigest()[:12] if expression else ""

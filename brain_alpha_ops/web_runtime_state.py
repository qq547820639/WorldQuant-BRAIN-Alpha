"""Runtime state helpers for the local web console."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Callable

from brain_alpha_ops.config import load_run_config, runtime_project_root
from brain_alpha_ops.research.repository import ResearchRepository


logger = logging.getLogger(__name__)

LoadConfig = Callable[[], Any]
ReadStorageJsonl = Callable[..., list[dict[str, Any]]]
SafeErrorMessage = Callable[[Exception], str]
RepositoryFactory = Callable[[str], ResearchRepository]


def active_auxiliary_operation(
    *,
    production_store: Any,
    sync_store: Any,
    check_store: Any,
    submit_lock: Any,
    exclude: str = "",
    allow_production: bool = False,
) -> tuple[str, str] | None:
    if not allow_production and exclude != "production" and production_store.latest_active():
        return "production", "连续生产任务正在运行，请先停止生产后再执行同步、检查或提交。"
    if exclude != "sync" and sync_store.latest_active():
        return "sync", "已有云端同步任务正在运行，请完成后再操作。"
    if exclude != "check" and check_store.latest_active():
        return "check", "已有批量检查任务正在运行，请完成后再操作。"
    if exclude != "submit" and submit_lock.locked():
        return "submit", "已有提交任务正在运行，请完成后再操作。"
    return None


def compute_run_stats(data: dict[str, Any], run_config: Any) -> dict[str, Any]:
    candidates = data.get("candidates", [])
    backtests = data.get("backtests", [])
    summary = data.get("summary", {})

    active_statuses = {"ACTIVE", "RUNNING", "SUBMITTED", "POLLING", "SIMULATION_RUNNING", "SIMULATION_SUBMITTED"}
    active_backtests = sum(1 for row in backtests if str(row.get("status", "")).upper() in active_statuses)

    passed_candidates = [
        row
        for row in candidates
        if row.get("lifecycle_status") == "submission_ready"
        or (row.get("gate") or {}).get("submission_ready")
    ]

    return {
        "produced_count": int(summary.get("produced_count", len(candidates))),
        "passed_count": len(passed_candidates),
        "active_backtests": active_backtests,
        "ready_results_count": int(summary.get("ready_results_count", 0)),
        "validation_tile": f"{summary.get('official_validation_passed', 0)}/{summary.get('official_validation_attempted', 0)}",
    }


def lifecycle_from_job(
    job: dict[str, Any],
    *,
    read_storage_jsonl: ReadStorageJsonl,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    result = job.get("result") or {}
    summary = result.get("summary") or {}
    progress = job.get("progress") or {}
    data = progress.get("data") or {}
    live = list(summary.get("lifecycle_records") or data.get("lifecycle_records") or [])
    rows = read_storage_jsonl("lifecycle.jsonl", limit=limit)
    seen = set()
    merged: list[dict[str, Any]] = []
    for row in rows + live:
        key = (
            row.get("run_id", ""),
            row.get("alpha_id", ""),
            row.get("official_alpha_id", ""),
            row.get("stage", ""),
            row.get("status", ""),
            row.get("simulation_id", ""),
            row.get("note", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        row["status_category"] = status_category(row)
        merged.append(row)
    return merged[-limit:]


def maybe_archive_lifecycle(
    *,
    last_archive_check: float,
    interval_seconds: float,
    load_config: LoadConfig = load_run_config,
    repository_factory: RepositoryFactory = ResearchRepository,
    safe_error_message: SafeErrorMessage = str,
    log: logging.Logger = logger,
    now: float | None = None,
) -> float:
    current = time.time() if now is None else now
    if current - last_archive_check < interval_seconds:
        return last_archive_check
    try:
        repo = repository_factory(load_config().ops.storage_dir)
        repo.maybe_archive("lifecycle.jsonl", max_size_mb=50)
    except Exception as exc:
        log.warning("lifecycle archive check failed: %s", safe_error_message(exc), exc_info=True)
    return current


def status_category(row: dict[str, Any]) -> str:
    stage = str(row.get("stage", "")).lower()
    status = str(row.get("status", "")).upper()
    status_text = f"{stage} {status}"
    if "blocked" in status_text or stage == "submission_blocked":
        return "blocked"
    if status in {"SUBMITTED", "ACTIVE", "PRODUCTION", "CONDUCTED"}:
        return "submitted"
    if any(word in status for word in ("FAILED", "REJECTED")):
        return "failed"
    if any(word in status for word in ("PASSED", "READY")):
        return "passed"
    return "other"


def load_presets(
    *,
    preset_path: Path | None = None,
    runtime_root: Callable[[], Path] = runtime_project_root,
    log: logging.Logger = logger,
) -> dict[str, Any]:
    target = preset_path or (runtime_root() / "config" / "presets.json")
    try:
        if target.is_file():
            return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.warning("failed to load presets from %s", target, exc_info=True)
    return {}


def match_preset_id(settings: dict[str, Any], presets: dict[str, Any]) -> str:
    for preset_id, preset in presets.items():
        expected = preset.get("settings", {})
        if all(str(settings.get(key, "")) == str(expected.get(key, "")) for key in expected):
            return str(preset_id)
    return ""


def load_check_results(
    *,
    read_storage_jsonl: ReadStorageJsonl,
    safe_error_message: SafeErrorMessage = str,
    log: logging.Logger = logger,
    limit: int = 5000,
    stale_after: timedelta = timedelta(hours=24),
    now: datetime | None = None,
) -> dict[str, Any]:
    try:
        items: list[dict[str, Any]] = []
        current = datetime.now(timezone.utc) if now is None else now
        for record in read_storage_jsonl("checks.jsonl", limit=limit):
            if not record.get("alpha_id"):
                continue
            checked_at = record.get("checked_at", "")
            if checked_at:
                try:
                    dt = datetime.fromisoformat(checked_at)
                    record["is_stale"] = (current - dt) > stale_after
                except (ValueError, TypeError):
                    record["is_stale"] = True
            else:
                record["is_stale"] = True
            items.append(record)
        return {"items": items, "count": len(items)}
    except Exception as exc:
        message = safe_error_message(exc)
        log.warning("failed to load check results: %s", message, exc_info=True)
        return {"items": [], "count": 0, "warning": message}

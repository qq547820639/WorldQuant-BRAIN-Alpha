"""Cloud sync job service entry point."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from brain_alpha_ops.brain_api.user_alpha_sync import (
    list_user_alphas_for_sync,
    sync_range_from_payload,
)
from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive

from ._helpers import (
    _SCAN_OBSERVABILITY_KEYS,
    _cloud_scan_status_message,
    _final_sync_status_message,
    _scan_observability,
    _sync_range_label,
    _timing_payload,
)
from ._types import (
    ApiFromRunConfig,
    DatasetsFromFields,
    ErrorPayload,
    JobStoreLike,
    PersistOfficialContext,
    RepositoryFactory,
    RunConfigFromPayload,
    SafeErrorMessage,
    SyncJobCancelled,
)

logger = logging.getLogger(__name__)


def run_sync_job_service(
    job_id: str,
    payload: dict[str, Any],
    *,
    store: JobStoreLike,
    run_config_from_payload: RunConfigFromPayload,
    api_from_run_config: ApiFromRunConfig,
    repository_factory: RepositoryFactory,
    datasets_from_fields: DatasetsFromFields,
    persist_official_context: PersistOfficialContext,
    default_fields: list[dict[str, Any]],
    default_operators: list[dict[str, Any]],
    safe_error_message: SafeErrorMessage,
    error_payload: ErrorPayload,
) -> None:
    sync_range = sync_range_from_payload(payload)
    context_only = bool(payload.get("contextOnly") or payload.get("context_only"))
    started_at = time.time()
    stats: dict[str, Any] = {
        "range": sync_range,
        "context_only": context_only,
        "scanned": 0,
        "total": 0,
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
    }
    context_error = ""
    context_warnings: list[str] = []
    stop_state = {
        "requested": False,
        "message": "云端同步已停止。",
        "status_message": "云端同步已停止，可调整范围后重试。",
    }

    # ---- watchdog heartbeat daemon ----
    heartbeat_stop = threading.Event()
    heartbeat_count = [0]
    _HB_INTERVAL = 120.0  # 2 minutes, well under 5-min watchdog

    def _heartbeat_loop() -> None:
        while not heartbeat_stop.wait(_HB_INTERVAL):
            heartbeat_count[0] += 1
            try:
                store.update(
                    job_id,
                    status="running",
                    progress={
                        "task_id": job_id,
                        "job_id": job_id,
                        "operation": "sync_alphas",
                        "phase": "heartbeat",
                        "status_code": "HEARTBEAT",
                        "status_message": f"Sync still active ({heartbeat_count[0]} heartbeats).",
                        "message": f"Sync still active ({heartbeat_count[0]} heartbeats).",
                        "heartbeat": {
                            "count": heartbeat_count[0],
                            "source": "watchdog_keepalive",
                            "elapsed": round(time.time() - started_at, 1),
                        },
                        **stats,
                        **_timing_payload(started_at, done=int(stats.get("scanned", 0) or 0)),
                    },
                )
            except (OSError, ValueError, TypeError):
                pass

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True, name=f"sync-hb-{job_id}")
    heartbeat_thread.start()
    # ---- end watchdog heartbeat daemon ----

    def cancel_requested() -> bool:
        checker = getattr(store, "is_cancelled", None)
        return bool(callable(checker) and checker(job_id))

    def request_stop(message: str, status_message: str | None = None) -> None:
        stop_state["requested"] = True
        stop_state["message"] = message
        stop_state["status_message"] = status_message or message

    def ensure_not_cancelled() -> None:
        if cancel_requested():
            request_stop("云端同步已停止。", "云端同步已停止，可调整范围后重试。")
            raise SyncJobCancelled(stop_state["message"])
        if stop_state["requested"]:
            raise SyncJobCancelled(stop_state["message"])

    def on_dataset_fallback(message: str, exc: Exception) -> None:
        context_warnings.append(f"{message}: {safe_error_message(exc)}")

    def mark_cancelled() -> None:
        store.update(
            job_id,
            status="cancelled",  # P0-2 unified (was "stopped"),
            result={
                "ok": False,
                "status": "cancelled",
                "range": sync_range,
                **stats,
                **_timing_payload(started_at, done=int(stats.get("scanned", 0) or 0)),
                "message": stop_state["message"],
            },
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "sync_alphas",
                "phase": "stopped",
                "status_code": "STOPPED",
                "status_message": stop_state["status_message"],
                "message": stop_state["status_message"],
                "percent": 100,
                "percent_complete": 100,
                **stats,
                **_timing_payload(started_at, done=int(stats.get("scanned", 0) or 0)),
            },
        )

    try:
        store.update(
            job_id,
            status="running",
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "sync_alphas",
                "phase": "auth",
                "status_code": "AUTH",
                "status_message": "准备仅刷新官方上下文。" if context_only else f"准备{_sync_range_label(sync_range)}云端同步。",
                "message": "准备仅刷新官方上下文。" if context_only else f"准备{_sync_range_label(sync_range)}云端同步。",
                **stats,
                **_timing_payload(started_at),
            },
        )
        ensure_not_cancelled()
        run_config = run_config_from_payload(payload)
        api = api_from_run_config(run_config)
        api.authenticate()
        ensure_not_cancelled()
        saved: list[dict[str, Any]] = []
        if not context_only:
            repo = repository_factory(run_config.ops.storage_dir)

            def on_page(progress: dict[str, Any]) -> bool:
                ensure_not_cancelled()
                if (
                    "total" in progress
                    and "api_reported_total" not in progress
                    and "filter_window_count" not in progress
                ):
                    # Legacy scan payloads used "total" for the API filter-window
                    # count. Preserve it as a reference only, never as completion.
                    progress = {
                        **progress,
                        "api_reported_total": progress.get("total"),
                        "filter_window_count": progress.get("total"),
                    }
                elif "api_reported_total" in progress and "filter_window_count" not in progress:
                    progress = {**progress, "filter_window_count": progress.get("api_reported_total")}
                elif "filter_window_count" in progress and "api_reported_total" not in progress:
                    progress = {**progress, "api_reported_total": progress.get("filter_window_count")}
                stats["scanned"] = int(progress.get("scanned", stats["scanned"]) or 0)
                stats["page_size"] = int(progress.get("page_size", stats.get("page_size", 0)) or 0)
                stats["offset"] = int(progress.get("offset", stats.get("offset", 0)) or 0)
                for key in _SCAN_OBSERVABILITY_KEYS:
                    stats.pop(key, None)
                stats.update(_scan_observability(progress))
                status_message = _cloud_scan_status_message(stats)
                scan_stats = dict(stats)
                scan_stats.pop("total", None)
                store.update(
                    job_id,
                    status="running",
                    progress={
                        "task_id": job_id,
                        "job_id": job_id,
                        "operation": "sync_alphas",
                        "phase": "scan",
                        "status_code": "SCAN",
                        "status_message": status_message,
                        "message": status_message,
                        **scan_stats,
                        **_timing_payload(started_at, done=stats["scanned"]),
                    },
                )
                if cancel_requested():
                    request_stop("云端同步已停止。", "云端同步已停止，可调整范围后重试。")
                    return False
                return True

            rows = list_user_alphas_for_sync(api, sync_range, progress_callback=on_page)
            ensure_not_cancelled()
            merge_stats = repo.merge_cloud_alphas(rows, sync_range=sync_range)
            stats.update({
                "scanned": len(rows),
                "total": len(rows),
                "added": merge_stats["added"],
                "updated": merge_stats["updated"],
                "skipped": merge_stats["skipped"],
                "failed": merge_stats["failed"],
            })
            saved = list(rows)
            merge_message = (
                f"云端记录合并完成：新增 {stats['added']:,} 条，更新 {stats['updated']:,} 条，"
                f"跳过 {stats['skipped']:,} 条。"
            )
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "sync_alphas",
                    "phase": "merge",
                    "status_code": "MERGE",
                    "status_message": merge_message,
                    "message": merge_message,
                    **stats,
                    **_timing_payload(started_at),
                },
            )
            ensure_not_cancelled()

        store.update(
            job_id,
            status="running",
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "sync_alphas",
                "phase": "context",
                "status_code": "CONTEXT_FIELDS",
                "status_message": "正在刷新官方字段缓存。",
                "message": "正在刷新官方字段缓存。",
                "current": 1,
                "total_steps": 3,
                **stats,
                **_timing_payload(started_at),
            },
        )
        try:
            def on_fields_progress(progress: dict[str, Any]) -> bool:
                ensure_not_cancelled()
                store.update(
                    job_id,
                    status="running",
                    progress={
                        "task_id": job_id,
                        "job_id": job_id,
                        "operation": "sync_alphas",
                        "phase": "context",
                        "status_code": "CONTEXT_FIELDS",
                        "status_message": f"正在刷新官方字段缓存: {progress.get('scanned', 0)} / {progress.get('total') or '未知'}",
                        "message": f"正在刷新官方字段缓存: {progress.get('scanned', 0)} / {progress.get('total') or '未知'}",
                        "current": 1,
                        "total_steps": 3,
                        "fields_count": int(progress.get("scanned", 0) or 0),
                        "fields_total": int(progress.get("total", 0) or 0),
                        **stats,
                        **_timing_payload(
                            started_at,
                            done=int(progress.get("scanned", 0) or 0),
                            total=int(progress.get("total", 0) or 0),
                        ),
                    },
                )
                if cancel_requested():
                    request_stop("云端同步已停止。", "云端同步已停止，可调整范围后重试。")
                    return False
                return True

            fields = api.list_fields(
                "all",
                run_config.ops.settings.region,
                progress_callback=on_fields_progress,
            )
            ensure_not_cancelled()
            datasets = list_official_datasets_or_derive(
                api,
                fields,
                region=run_config.ops.settings.region,
                datasets_from_fields=datasets_from_fields,
                fallback_warning=on_dataset_fallback,
            )
            stats["datasets_count"] = len(datasets)
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "sync_alphas",
                    "phase": "context",
                    "status_code": "CONTEXT_OPERATORS",
                    "status_message": "正在刷新官方算子缓存。",
                    "message": "正在刷新官方算子缓存。",
                    "current": 2,
                    "total_steps": 3,
                    "fields_count": len(fields),
                    **stats,
                    **_timing_payload(started_at),
                },
            )

            def on_operators_progress(progress: dict[str, Any]) -> bool:
                ensure_not_cancelled()
                store.update(
                    job_id,
                    status="running",
                    progress={
                        "task_id": job_id,
                        "job_id": job_id,
                        "operation": "sync_alphas",
                        "phase": "context",
                        "status_code": "CONTEXT_OPERATORS",
                        "status_message": f"正在刷新官方算子缓存: {progress.get('scanned', 0)} / {progress.get('total') or '未知'}",
                        "message": f"正在刷新官方算子缓存: {progress.get('scanned', 0)} / {progress.get('total') or '未知'}",
                        "current": 2,
                        "total_steps": 3,
                        "fields_count": len(fields),
                        "operators_count": int(progress.get("scanned", 0) or 0),
                        "operators_total": int(progress.get("total", 0) or 0),
                        **stats,
                        **_timing_payload(
                            started_at,
                            done=int(progress.get("scanned", 0) or 0),
                            total=int(progress.get("total", 0) or 0),
                        ),
                    },
                )
                if cancel_requested():
                    request_stop("云端同步已停止。", "云端同步已停止，可调整范围后重试。")
                    return False
                return True

            operators = api.list_operators(
                "all",
                progress_callback=on_operators_progress,
            )
            ensure_not_cancelled()
            persist_official_context(fields, operators, datasets)
        except SyncJobCancelled:
            raise
        except Exception as exc:
            context_error = safe_error_message(exc)
            stats["failed"] += 1
            fields = list(default_fields)
            operators = list(default_operators)
            datasets = []
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "sync_alphas",
                    "phase": "context",
                    "status_code": "CONTEXT_FAILED",
                    "status_message": f"官方上下文刷新失败，已改用本地兜底上下文：{context_error}",
                    "message": f"官方上下文刷新失败，已改用本地兜底上下文：{context_error}",
                    "context_error": context_error,
                    "current": 3,
                    "total_steps": 3,
                    **stats,
                    **_timing_payload(started_at, done=stats["scanned"]),
                },
            )
        ensure_not_cancelled()
        filter_window_count = int(stats.get("api_reported_total") or stats.get("filter_window_count") or 0)
        result = {
            "ok": True,
            **stats,
            "api_reported_total": filter_window_count,
            "filter_window_count": filter_window_count,
            "count": len(saved),
            "total": len(saved),
            "alphas": saved,
            "fields_count": len(fields),
            "operators_count": len(operators),
            "datasets_count": len(datasets),
            "context_status": (
                "failed"
                if context_error
                else "refreshed_with_warnings"
                if context_warnings
                else "refreshed"
            ),
            "context_error": context_error,
            "context_warnings": context_warnings,
            **_timing_payload(started_at, done=stats["scanned"]),
        }
        final_status = "completed_with_warnings" if context_error or context_warnings else "completed"
        completion_message = _final_sync_status_message(
            stats,
            context_error=context_error,
            context_warnings=context_warnings,
        )
        store.update(
            job_id,
            status=final_status,
            result=result,
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "sync_alphas",
                "phase": final_status,
                "status_code": "COMPLETED_WITH_WARNINGS" if context_error else "COMPLETED",
                "percent": 100,
                "percent_complete": 100,
                "status_message": completion_message,
                "message": completion_message,
                **stats,
                **_timing_payload(started_at, done=stats["scanned"]),
                "fields_count": len(fields),
                "operators_count": len(operators),
                "datasets_count": len(datasets),
                "context_status": (
                    "failed"
                    if context_error
                    else "refreshed_with_warnings"
                    if context_warnings
                    else "refreshed"
                ),
                "context_error": context_error,
                "context_warnings": context_warnings,
            },
        )
    except SyncJobCancelled:
        heartbeat_stop.set()
        mark_cancelled()
    except Exception as exc:
        heartbeat_stop.set()
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="SYNC_JOB_FAILED", job_id=job_id, phase="sync_job")
        logger.error("sync job failed: %s", error_context, exc_info=True)
        stats["failed"] += 1
        store.update(
            job_id,
            status="failed",
            error=message,
            progress={
                "phase": "failed",
                "status_code": "FAILED",
                "task_id": job_id,
                "job_id": job_id,
                "operation": "sync_alphas",
                "status_message": message,
                "message": message,
                "percent": 100,
                "percent_complete": 100,
                "error_context": error_context,
                **stats,
                **_timing_payload(started_at, done=int(stats.get("scanned", 0) or 0)),
            },
        )

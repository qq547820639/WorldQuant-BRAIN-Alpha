"""Cloud sync job service orchestration entry point."""

from __future__ import annotations

import logging
from typing import Any

from brain_alpha_ops.brain_api.user_alpha_sync import list_user_alphas_for_sync
from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive

from .._helpers import (
    _final_sync_status_message,
    _sync_range_label,
    _timing_payload,
)
from .._types import (
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
from ._state import SyncJobContext

logger = logging.getLogger("brain_alpha_ops.web_cloud.sync_job._service")


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
    ctx = SyncJobContext(
        job_id,
        payload,
        store=store,
        safe_error_message=safe_error_message,
        error_payload=error_payload,
    )
    ctx.start_heartbeat()
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
                "status_message": "准备仅刷新官方上下文。" if ctx.context_only else f"准备{_sync_range_label(ctx.sync_range)}云端同步。",
                "message": "准备仅刷新官方上下文。" if ctx.context_only else f"准备{_sync_range_label(ctx.sync_range)}云端同步。",
                **ctx.stats,
                **_timing_payload(ctx.started_at),
            },
        )
        ctx.ensure_not_cancelled()
        run_config = run_config_from_payload(payload)
        api = api_from_run_config(run_config)
        api.authenticate()
        ctx.ensure_not_cancelled()
        if not ctx.context_only:
            repo = repository_factory(run_config.ops.storage_dir)
            rows = list_user_alphas_for_sync(api, ctx.sync_range, progress_callback=ctx.on_page)
            ctx.ensure_not_cancelled()
            merge_stats = repo.merge_cloud_alphas(rows, sync_range=ctx.sync_range)
            ctx.stats.update({
                "scanned": len(rows),
                "total": len(rows),
                "added": merge_stats["added"],
                "updated": merge_stats["updated"],
                "skipped": merge_stats["skipped"],
                "failed": merge_stats["failed"],
            })
            ctx.saved = list(rows)
            merge_message = (
                f"云端记录合并完成：新增 {ctx.stats['added']:,} 条，更新 {ctx.stats['updated']:,} 条，"
                f"跳过 {ctx.stats['skipped']:,} 条。"
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
                    **ctx.stats,
                    **_timing_payload(ctx.started_at),
                },
            )
            ctx.ensure_not_cancelled()

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
                **ctx.stats,
                **_timing_payload(ctx.started_at),
            },
        )
        try:
            ctx.fields = api.list_fields(
                "all",
                run_config.ops.settings.region,
                progress_callback=ctx.on_fields_progress,
            )
            ctx.ensure_not_cancelled()
            ctx.datasets = list_official_datasets_or_derive(
                api,
                ctx.fields,
                region=run_config.ops.settings.region,
                datasets_from_fields=datasets_from_fields,
                fallback_warning=ctx.on_dataset_fallback,
            )
            ctx.stats["datasets_count"] = len(ctx.datasets)
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
                    "fields_count": len(ctx.fields),
                    **ctx.stats,
                    **_timing_payload(ctx.started_at),
                },
            )

            ctx.operators = api.list_operators(
                "all",
                progress_callback=ctx.on_operators_progress,
            )
            ctx.ensure_not_cancelled()
            persist_official_context(ctx.fields, ctx.operators, ctx.datasets)
        except SyncJobCancelled:
            raise
        except Exception as exc:
            ctx.context_error = safe_error_message(exc)
            ctx.stats["failed"] += 1
            ctx.fields = list(default_fields)
            ctx.operators = list(default_operators)
            ctx.datasets = []
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "sync_alphas",
                    "phase": "context",
                    "status_code": "CONTEXT_FAILED",
                    "status_message": f"官方上下文刷新失败，已改用本地兜底上下文：{ctx.context_error}",
                    "message": f"官方上下文刷新失败，已改用本地兜底上下文：{ctx.context_error}",
                    "context_error": ctx.context_error,
                    "current": 3,
                    "total_steps": 3,
                    **ctx.stats,
                    **_timing_payload(ctx.started_at, done=ctx.stats["scanned"]),
                },
            )
        ctx.ensure_not_cancelled()
        filter_window_count = int(ctx.stats.get("api_reported_total") or ctx.stats.get("filter_window_count") or 0)
        result = {
            "ok": True,
            **ctx.stats,
            "api_reported_total": filter_window_count,
            "filter_window_count": filter_window_count,
            "count": len(ctx.saved),
            "total": len(ctx.saved),
            "alphas": ctx.saved,
            "fields_count": len(ctx.fields),
            "operators_count": len(ctx.operators),
            "datasets_count": len(ctx.datasets),
            "context_status": (
                "failed"
                if ctx.context_error
                else "refreshed_with_warnings"
                if ctx.context_warnings
                else "refreshed"
            ),
            "context_error": ctx.context_error,
            "context_warnings": ctx.context_warnings,
            **_timing_payload(ctx.started_at, done=ctx.stats["scanned"]),
        }
        final_status = "completed_with_warnings" if ctx.context_error or ctx.context_warnings else "completed"
        completion_message = _final_sync_status_message(
            ctx.stats,
            context_error=ctx.context_error,
            context_warnings=ctx.context_warnings,
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
                "status_code": "COMPLETED_WITH_WARNINGS" if ctx.context_error else "COMPLETED",
                "percent": 100,
                "percent_complete": 100,
                "status_message": completion_message,
                "message": completion_message,
                **ctx.stats,
                **_timing_payload(ctx.started_at, done=ctx.stats["scanned"]),
                "fields_count": len(ctx.fields),
                "operators_count": len(ctx.operators),
                "datasets_count": len(ctx.datasets),
                "context_status": (
                    "failed"
                    if ctx.context_error
                    else "refreshed_with_warnings"
                    if ctx.context_warnings
                    else "refreshed"
                ),
                "context_error": ctx.context_error,
                "context_warnings": ctx.context_warnings,
            },
        )
    except SyncJobCancelled:
        ctx.stop_heartbeat()
        ctx.mark_cancelled()
    except Exception as exc:
        ctx.stop_heartbeat()
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="SYNC_JOB_FAILED", job_id=job_id, phase="sync_job")
        logger.error("sync job failed: %s", error_context, exc_info=True)
        ctx.stats["failed"] += 1
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
                **ctx.stats,
                **_timing_payload(ctx.started_at, done=int(ctx.stats.get("scanned", 0) or 0)),
            },
        )

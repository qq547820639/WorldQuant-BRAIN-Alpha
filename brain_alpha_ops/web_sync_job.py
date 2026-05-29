"""Cloud sync background job service for the local web console."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive
from brain_alpha_ops.research.repository import ResearchRepository


logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...

    def is_cancelled(self, job_id: str) -> bool:
        ...


class SyncJobCancelled(RuntimeError):
    """Raised internally when a user asks to stop a cloud sync job."""


RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ApiFromRunConfig = Callable[[RunConfig], Any]
RepositoryFactory = Callable[[str], ResearchRepository]
DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
PersistOfficialContext = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]
SafeErrorMessage = Callable[[Exception], str]
ErrorPayload = Callable[..., dict[str, Any]]


def _timing_payload(started_at: float, *, done: int = 0, total: int = 0, now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    start = float(started_at or current)
    elapsed = max(0.0, current - start)
    payload: dict[str, Any] = {
        "started_at_ms": int(start * 1000),
        "updated_at_ms": int(current * 1000),
        "elapsed_seconds": round(elapsed, 1),
    }
    done = max(0, int(done or 0))
    total = max(0, int(total or 0))
    if done > 0 and total > done and elapsed > 0:
        rate = done / elapsed
        eta_seconds = max(1, int(round((total - done) / rate))) if rate > 0 else 0
        payload.update({
            "rate_per_second": round(rate, 3),
            "eta_seconds": eta_seconds,
            "eta_deadline_at_ms": int((current + eta_seconds) * 1000),
        })
    elif total and done >= total:
        payload.update({
            "rate_per_second": round(done / elapsed, 3) if elapsed > 0 else 0,
            "eta_seconds": 0,
        })
    return payload


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
    sync_range = str(payload.get("syncRange", "3d"))
    started_at = time.time()
    stats: dict[str, Any] = {"range": sync_range, "scanned": 0, "total": 0, "added": 0, "updated": 0, "skipped": 0, "failed": 0}
    context_error = ""

    def ensure_not_cancelled() -> None:
        checker = getattr(store, "is_cancelled", None)
        if callable(checker) and checker(job_id):
            raise SyncJobCancelled("云端同步已停止。")

    def mark_cancelled() -> None:
        store.update(
            job_id,
            status="stopped",
            result={
                "ok": False,
                "status": "stopped",
                "range": sync_range,
                **stats,
                **_timing_payload(started_at, done=int(stats.get("scanned", 0) or 0), total=int(stats.get("total", 0) or 0)),
                "message": "云端同步已停止。",
            },
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "sync_alphas",
                "phase": "stopped",
                "status_code": "STOPPED",
                "status_message": "云端同步已停止，可调整范围后重试。",
                "message": "云端同步已停止，可调整范围后重试。",
                "percent": 100,
                "percent_complete": 100,
                **stats,
                **_timing_payload(started_at, done=int(stats.get("scanned", 0) or 0), total=int(stats.get("total", 0) or 0)),
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
                "status_message": f"Preparing cloud sync for {sync_range}.",
                "message": f"Preparing cloud sync for {sync_range}.",
                **stats,
                **_timing_payload(started_at),
            },
        )
        ensure_not_cancelled()
        run_config = run_config_from_payload(payload)
        api = api_from_run_config(run_config)
        api.authenticate()
        ensure_not_cancelled()
        repo = repository_factory(run_config.ops.storage_dir)

        def on_page(progress: dict[str, Any]) -> None:
            ensure_not_cancelled()
            stats["scanned"] = int(progress.get("scanned", stats["scanned"]) or 0)
            stats["total"] = int(progress.get("total", stats["total"]) or 0)
            stats["page_size"] = int(progress.get("page_size", stats.get("page_size", 0)) or 0)
            stats["offset"] = int(progress.get("offset", stats.get("offset", 0)) or 0)
            store.update(
                job_id,
                status="running",
                progress={
                    "task_id": job_id,
                    "job_id": job_id,
                    "operation": "sync_alphas",
                    "phase": "scan",
                    "status_code": "SCAN",
                    "status_message": f"Scanning cloud alphas: {stats['scanned']} / {stats['total'] or 'unknown'}",
                    "message": f"Scanning cloud alphas: {stats['scanned']} / {stats['total'] or 'unknown'}",
                    **stats,
                    **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
                },
            )
            ensure_not_cancelled()

        rows = api.list_user_alphas(sync_range, progress_callback=on_page)
        ensure_not_cancelled()
        if not stats["total"]:
            stats["total"] = len(rows)
        merge_stats = repo.merge_cloud_alphas(rows, sync_range=sync_range)
        stats.update({
            "scanned": len(rows),
            "added": merge_stats["added"],
            "updated": merge_stats["updated"],
            "skipped": merge_stats["skipped"],
            "failed": merge_stats["failed"],
        })
        saved = list(rows)
        store.update(
            job_id,
            status="running",
            progress={
                "task_id": job_id,
                "job_id": job_id,
                "operation": "sync_alphas",
                "phase": "merge",
                "status_code": "MERGE",
                "status_message": f"Merged cloud records: added {stats['added']}, updated {stats['updated']}, skipped {stats['skipped']}.",
                "message": f"Merged cloud records: added {stats['added']}, updated {stats['updated']}, skipped {stats['skipped']}.",
                **stats,
                **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
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
                "status_message": "Updating official fields cache.",
                "message": "Updating official fields cache.",
                "current": 1,
                "total_steps": 3,
                **stats,
                **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
            },
        )
        try:
            def on_fields_progress(progress: dict[str, Any]) -> None:
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
                        "status_message": f"Updating official fields cache: {progress.get('scanned', 0)} / {progress.get('total') or 'unknown'}",
                        "message": f"Updating official fields cache: {progress.get('scanned', 0)} / {progress.get('total') or 'unknown'}",
                        "current": 1,
                        "total_steps": 3,
                        "fields_count": int(progress.get("scanned", 0) or 0),
                        "fields_total": int(progress.get("total", 0) or 0),
                        **stats,
                        **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
                    },
                )
                ensure_not_cancelled()

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
                    "status_message": "Updating official operators cache.",
                    "message": "Updating official operators cache.",
                    "current": 2,
                    "total_steps": 3,
                    "fields_count": len(fields),
                    **stats,
                    **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
                },
            )

            def on_operators_progress(progress: dict[str, Any]) -> None:
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
                        "status_message": f"Updating official operators cache: {progress.get('scanned', 0)} / {progress.get('total') or 'unknown'}",
                        "message": f"Updating official operators cache: {progress.get('scanned', 0)} / {progress.get('total') or 'unknown'}",
                        "current": 2,
                        "total_steps": 3,
                        "fields_count": len(fields),
                        "operators_count": int(progress.get("scanned", 0) or 0),
                        "operators_total": int(progress.get("total", 0) or 0),
                        **stats,
                        **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
                    },
                )
                ensure_not_cancelled()

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
                    "status_message": f"Official context refresh failed; using fallback context: {context_error}",
                    "message": f"Official context refresh failed; using fallback context: {context_error}",
                    "context_error": context_error,
                    "current": 3,
                    "total_steps": 3,
                    **stats,
                    **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
                },
            )
        ensure_not_cancelled()
        result = {
            "ok": True,
            **stats,
            "count": len(saved),
            "total": stats["total"] or len(saved),
            "alphas": saved,
            "fields_count": len(fields),
            "operators_count": len(operators),
            "datasets_count": len(datasets),
            "context_status": "failed" if context_error else "refreshed",
            "context_error": context_error,
            **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
        }
        final_status = "completed_with_warnings" if context_error else "completed"
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
                "status_message": (
                    f"Cloud sync completed with context warning: {context_error}"
                    if context_error else
                    f"Cloud sync completed: scanned {stats['scanned']}, added {stats['added']}, "
                    f"updated {stats.get('updated', 0)}, skipped {stats['skipped']}, failed {stats['failed']}."
                ),
                "message": (
                    f"Cloud sync completed with context warning: {context_error}"
                    if context_error else
                    f"Cloud sync completed: scanned {stats['scanned']}, added {stats['added']}, "
                    f"updated {stats.get('updated', 0)}, skipped {stats['skipped']}, failed {stats['failed']}."
                ),
                **stats,
                **_timing_payload(started_at, done=stats["scanned"], total=stats["total"]),
                "fields_count": len(fields),
                "operators_count": len(operators),
                "datasets_count": len(datasets),
                "context_status": "failed" if context_error else "refreshed",
                "context_error": context_error,
            },
        )
    except SyncJobCancelled:
        mark_cancelled()
    except Exception as exc:
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
                **_timing_payload(started_at, done=int(stats.get("scanned", 0) or 0), total=int(stats.get("total", 0) or 0)),
            },
        )

"""Cloud sync background job service for the local web console."""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from brain_alpha_ops.config import RunConfig
from brain_alpha_ops.research.repository import ResearchRepository


logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


RunConfigFromPayload = Callable[[dict[str, Any]], RunConfig]
ApiFromRunConfig = Callable[[RunConfig], Any]
RepositoryFactory = Callable[[str], ResearchRepository]
DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
PersistOfficialContext = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]
SafeErrorMessage = Callable[[Exception], str]
ErrorPayload = Callable[..., dict[str, Any]]


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
    stats = {"range": sync_range, "scanned": 0, "total": 0, "added": 0, "updated": 0, "skipped": 0, "failed": 0}
    try:
        store.update(
            job_id,
            status="running",
            progress={"phase": "auth", "status_code": "AUTH", "message": f"Preparing cloud sync for {sync_range}.", **stats},
        )
        run_config = run_config_from_payload(payload)
        api = api_from_run_config(run_config)
        api.authenticate()
        repo = repository_factory(run_config.ops.storage_dir)

        def on_page(progress: dict[str, Any]) -> None:
            stats["scanned"] = int(progress.get("scanned", stats["scanned"]) or 0)
            stats["total"] = int(progress.get("total", stats["total"]) or 0)
            stats["page_size"] = int(progress.get("page_size", stats.get("page_size", 0)) or 0)
            stats["offset"] = int(progress.get("offset", stats.get("offset", 0)) or 0)
            store.update(
                job_id,
                status="running",
                progress={
                    "phase": "scan",
                    "status_code": "SCAN",
                    "message": f"Scanning cloud alphas: {stats['scanned']} / {stats['total'] or 'unknown'}",
                    **stats,
                },
            )

        rows = api.list_user_alphas(sync_range, progress_callback=on_page)
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
                "phase": "merge",
                "status_code": "MERGE",
                "message": f"Merged cloud records: added {stats['added']}, updated {stats['updated']}, skipped {stats['skipped']}.",
                **stats,
            },
        )

        store.update(
            job_id,
            status="running",
            progress={
                "phase": "context",
                "status_code": "CONTEXT_FIELDS",
                "message": "Updating official fields cache.",
                "current": 1,
                "total_steps": 3,
                **stats,
            },
        )
        try:
            fields = api.list_fields(
                "all",
                run_config.ops.settings.region,
                progress_callback=lambda progress: store.update(
                    job_id,
                    status="running",
                    progress={
                        "phase": "context",
                        "status_code": "CONTEXT_FIELDS",
                        "message": f"Updating official fields cache: {progress.get('scanned', 0)} / {progress.get('total') or 'unknown'}",
                        "current": 1,
                        "total_steps": 3,
                        "fields_count": int(progress.get("scanned", 0) or 0),
                        "fields_total": int(progress.get("total", 0) or 0),
                        **stats,
                    },
                ),
            )
            datasets = datasets_from_fields(fields)
            stats["datasets_count"] = len(datasets)
            store.update(
                job_id,
                status="running",
                progress={
                    "phase": "context",
                    "status_code": "CONTEXT_OPERATORS",
                    "message": "Updating official operators cache.",
                    "current": 2,
                    "total_steps": 3,
                    "fields_count": len(fields),
                    **stats,
                },
            )
            operators = api.list_operators(
                "all",
                progress_callback=lambda progress: store.update(
                    job_id,
                    status="running",
                    progress={
                        "phase": "context",
                        "status_code": "CONTEXT_OPERATORS",
                        "message": f"Updating official operators cache: {progress.get('scanned', 0)} / {progress.get('total') or 'unknown'}",
                        "current": 2,
                        "total_steps": 3,
                        "fields_count": len(fields),
                        "operators_count": int(progress.get("scanned", 0) or 0),
                        "operators_total": int(progress.get("total", 0) or 0),
                        **stats,
                    },
                ),
            )
            persist_official_context(fields, operators, datasets)
        except Exception:
            stats["failed"] += 1
            fields = list(default_fields)
            operators = list(default_operators)
            datasets = []
        result = {
            "ok": True,
            **stats,
            "count": len(saved),
            "total": stats["total"] or len(saved),
            "alphas": saved,
            "fields_count": len(fields),
            "operators_count": len(operators),
            "datasets_count": len(datasets),
        }
        store.update(
            job_id,
            status="completed",
            result=result,
            progress={
                "phase": "completed",
                "status_code": "COMPLETED",
                "message": (
                    f"Cloud sync completed: scanned {stats['scanned']}, added {stats['added']}, "
                    f"updated {stats.get('updated', 0)}, skipped {stats['skipped']}, failed {stats['failed']}."
                ),
                **stats,
                "fields_count": len(fields),
                "operators_count": len(operators),
                "datasets_count": len(datasets),
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="SYNC_JOB_FAILED", job_id=job_id, phase="sync_job")
        logger.error("sync job failed: %s", error_context, exc_info=True)
        stats["failed"] += 1
        store.update(
            job_id,
            status="failed",
            error=message,
            progress={"phase": "failed", "status_code": "FAILED", "message": message, "error_context": error_context, **stats},
        )

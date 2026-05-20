"""Cloud/context refresh service used by web candidate checks."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from brain_alpha_ops.research.repository import ResearchRepository


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


OfficialContextCounts = Callable[[], dict[str, Any]]
DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
PersistOfficialContext = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]
SafeErrorMessage = Callable[[Exception], str]


def refresh_cloud_context_for_check_service(
    api: Any,
    repo: ResearchRepository,
    sync_range: str,
    job_id: str,
    total: int,
    mode: str,
    region: str = "",
    *,
    refresh_remote: bool = False,
    store: JobStoreLike,
    official_context_file_counts: OfficialContextCounts,
    datasets_from_fields: DatasetsFromFields,
    persist_official_context: PersistOfficialContext,
    safe_error_message: SafeErrorMessage,
) -> tuple[list[dict[str, Any]], str]:
    context_errors: list[str] = []

    if not refresh_remote:
        rows = repo.latest_cloud_alphas()
        counts = official_context_file_counts()
        store.update(
            job_id,
            status="running",
            progress={
                "phase": "cloud_sync",
                "status_code": "CHECK_LOCAL_CACHE",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "cloud_scanned": len(rows),
                "cloud_total": len(rows),
                **counts,
                "message": f"Using local cloud cache for checks: {len(rows)} rows.",
                "items": [],
            },
        )
        if not rows:
            return [], "local cloud cache empty; run manual sync first"
        return rows, ""

    try:
        rows = api.list_user_alphas(
            sync_range,
            progress_callback=lambda progress: store.update(
                job_id,
                status="running",
                progress={
                    "phase": "cloud_sync",
                    "status_code": "CHECK_CLOUD_SYNC",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "checked": 0,
                    "submittable": 0,
                    "blocked": 0,
                    "failed": 0,
                    "cloud_scanned": int(progress.get("scanned", 0) or 0),
                    "cloud_total": int(progress.get("total", 0) or 0),
                    "message": f"Refreshing cloud alphas: scanned {progress.get('scanned', 0)} / {progress.get('total') or 'unknown'}.",
                    "items": [],
                },
            ),
        )
    except Exception as exc:
        return [], safe_error_message(exc)

    fields: list[dict[str, Any]] = []
    operators: list[dict[str, Any]] = []
    fields_count = 0
    operators_count = 0
    try:
        fields = api.list_fields("all", region)
        fields_count = len(fields)
        store.update(
            job_id,
            status="running",
            progress={
                "phase": "cloud_sync",
                "status_code": "CHECK_CONTEXT_FIELDS",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "message": f"Updated official fields cache: {fields_count} rows.",
                "items": [],
            },
        )
    except Exception as exc:
        context_errors.append(f"fields refresh failed: {safe_error_message(exc)}")

    try:
        operators = api.list_operators("all")
        operators_count = len(operators)
        store.update(
            job_id,
            status="running",
            progress={
                "phase": "cloud_sync",
                "status_code": "CHECK_CONTEXT_OPERATORS",
                "mode": mode,
                "range": sync_range,
                "total": total,
                "checked": 0,
                "submittable": 0,
                "blocked": 0,
                "failed": 0,
                "message": f"Updated official operators cache: {operators_count} rows.",
                "items": [],
            },
        )
    except Exception as exc:
        context_errors.append(f"operators refresh failed: {safe_error_message(exc)}")

    try:
        datasets = datasets_from_fields(fields) if fields_count > 0 else []
        persist_official_context(
            fields if fields_count > 0 else [],
            operators if operators_count > 0 else [],
            datasets,
        )
    except Exception as exc:
        context_errors.append(f"persist context failed: {safe_error_message(exc)}")

    repo.merge_cloud_alphas(rows, sync_range=sync_range)
    error_msg = "; ".join(context_errors)[:500] if context_errors else ""
    return rows, error_msg

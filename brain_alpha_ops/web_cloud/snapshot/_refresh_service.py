"""Cloud/context refresh service used by web candidate checks."""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from brain_alpha_ops.brain_api.user_alpha_sync import list_user_alphas_for_sync
from brain_alpha_ops.official_context_datasets import list_official_datasets_or_derive
from brain_alpha_ops.research.repository import ResearchRepository

logger = logging.getLogger(__name__)


class JobStoreLike(Protocol):
    def update(self, job_id: str, **kwargs: Any) -> None:
        ...


OfficialContextCounts = Callable[[], dict[str, Any]]
DatasetsFromFields = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
PersistOfficialContext = Callable[[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None]
SafeErrorMessage = Callable[[Exception], str]


def _cloud_refresh_progress_message(progress: dict[str, Any]) -> str:
    scanned = int(progress.get("scanned", 0) or 0)
    reference = int(
        progress.get("api_reported_total")
        or progress.get("filter_window_count")
        or 0
    )
    page = int(progress.get("pages_fetched") or progress.get("page_number") or 0)
    reference_text = (
        f"接口分页参考数 {reference} 条，不是云端 Alpha 总量"
        if reference > 0
        else "接口分页参考数仍在确认"
    )
    page_text = f"；当前第 {page} 页" if page else ""
    return f"云端 Alpha 分页拉取中：已拉取 {scanned} 条；{reference_text}{page_text}。"


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
    context_warnings: list[str] = []

    def on_dataset_fallback(message: str, exc: Exception) -> None:
        context_warnings.append(f"datasets refresh fallback: {message}: {safe_error_message(exc)}")

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
                "cloud_saved_count": len(rows),
                **counts,
                "message": f"Using local cloud cache for checks: {len(rows)} rows.",
                "items": [],
            },
        )
        if not rows:
            return [], "local cloud cache empty; run manual sync first"
        return rows, ""

    try:
        rows = list_user_alphas_for_sync(
            api,
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
                    "cloud_api_reported_total": int(progress.get("api_reported_total", 0) or 0),
                    "cloud_filter_window_count": int(
                        progress.get("filter_window_count")
                        or progress.get("api_reported_total")
                        or 0
                    ),
                    "cloud_page_size": int(progress.get("page_size", 0) or 0),
                    "cloud_page_limit": int(progress.get("page_limit", 0) or 0),
                    "cloud_pages_fetched": int(progress.get("pages_fetched") or progress.get("page_number") or 0),
                    "cloud_expected_pages": int(progress.get("expected_pages", 0) or 0),
                    "cloud_next_offset": int(progress.get("next_offset", 0) or 0),
                    "message": _cloud_refresh_progress_message(progress),
                    "items": [],
                },
            ),
        )
    except Exception as exc:
        message = safe_error_message(exc)
        logger.warning(
            "cloud alpha refresh failed for check job_id=%s range=%s: %s",
            job_id,
            sync_range,
            message,
            exc_info=True,
        )
        return [], message

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
        message = safe_error_message(exc)
        logger.warning(
            "official fields refresh failed for check job_id=%s range=%s: %s",
            job_id,
            sync_range,
            message,
            exc_info=True,
        )
        context_errors.append(f"fields refresh failed: {message}")

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
        message = safe_error_message(exc)
        logger.warning(
            "official operators refresh failed for check job_id=%s range=%s: %s",
            job_id,
            sync_range,
            message,
            exc_info=True,
        )
        context_errors.append(f"operators refresh failed: {message}")

    try:
        datasets = (
            list_official_datasets_or_derive(
                api,
                fields,
                region=region,
                datasets_from_fields=datasets_from_fields,
                fallback_warning=on_dataset_fallback,
            )
            if fields_count > 0
            else []
        )
        persist_official_context(
            fields if fields_count > 0 else [],
            operators if operators_count > 0 else [],
            datasets,
        )
        if context_warnings:
            store.update(
                job_id,
                status="running",
                progress={
                    "phase": "cloud_sync",
                    "status_code": "CHECK_CONTEXT_WARNING",
                    "mode": mode,
                    "range": sync_range,
                    "total": total,
                    "checked": 0,
                    "submittable": 0,
                    "blocked": 0,
                    "failed": 0,
                    "context_warnings": context_warnings,
                    "message": "; ".join(context_warnings),
                    "items": [],
                },
            )
    except Exception as exc:
        message = safe_error_message(exc)
        logger.warning(
            "persist official context failed for check job_id=%s range=%s: %s",
            job_id,
            sync_range,
            message,
            exc_info=True,
        )
        context_errors.append(f"persist context failed: {message}")

    repo.merge_cloud_alphas(rows, sync_range=sync_range)
    store.update(
        job_id,
        status="running",
        progress={
            "phase": "cloud_sync",
            "status_code": "CHECK_CONTEXT_WARNING" if context_warnings else "CHECK_CLOUD_SYNC_SAVED",
            "mode": mode,
            "range": sync_range,
            "total": total,
            "checked": 0,
            "submittable": 0,
            "blocked": 0,
            "failed": 0,
            "cloud_saved_count": len(rows),
            "context_warnings": context_warnings,
            "message": (
                f"{'; '.join(context_warnings)}；本地已保存 {len(rows)} 条云端 Alpha，继续执行提交前复核。"
                if context_warnings
                else f"本地已保存 {len(rows)} 条云端 Alpha，继续执行提交前复核。"
            ),
            "items": [],
        },
    )
    error_msg = "; ".join(context_errors)[:500] if context_errors else ""
    return rows, error_msg

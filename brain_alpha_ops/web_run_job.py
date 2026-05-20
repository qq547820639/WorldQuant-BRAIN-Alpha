"""Background production job runner for the local web console."""

from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.observability import error_payload


RunConfigFromPayload = Callable[[dict[str, Any]], Any]
RunPipeline = Callable[..., Any]
ComputeRunStats = Callable[[dict[str, Any], Any], dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]


def run_job_service(
    job_id: str,
    payload: dict[str, Any],
    *,
    job_store: Any,
    run_config_from_payload: RunConfigFromPayload,
    run_pipeline_from_config: RunPipeline,
    compute_run_stats: ComputeRunStats,
    safe_error_message: SafeErrorMessage,
    log: logging.Logger,
) -> None:
    try:
        job_store.update(
            job_id,
            status="running",
            progress={"phase": "startup", "current": 0, "total": 1, "percent": 0, "message": "后台任务启动。", "alpha_id": ""},
        )
        run_config = run_config_from_payload(payload)
        result = run_pipeline_from_config(
            run_config,
            progress_callback=lambda progress: job_store.update(job_id, progress=progress),
            stop_callback=lambda: job_store.is_cancelled(job_id),
        )
        final_status = "stopped" if job_store.is_cancelled(job_id) else "completed"
        result_data = result.to_dict()
        last_progress = (job_store.get(job_id) or {}).get("progress", {})
        last_data = dict(last_progress.get("data") or {})
        last_data.update(result_data.get("summary") or {})
        last_data["candidates"] = result_data.get("candidates") or []
        last_data["backtests"] = (result_data.get("summary") or {}).get("backtest_slots") or last_data.get("backtests", [])
        last_data["stats"] = compute_run_stats(last_data, run_config)
        job_store.update(
            job_id,
            status=final_status,
            result=result_data,
            progress={
                "phase": final_status,
                "current": 0 if final_status == "stopped" else 1,
                "total": 1,
                "percent": 0 if final_status == "stopped" else 100,
                "message": "任务已停止。" if final_status == "stopped" else "任务完成。",
                "alpha_id": "",
                "continuous": run_config.ops.budget.run_forever,
                "data": last_data,
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="RUN_JOB_FAILED", job_id=job_id, phase="run_job")
        log.error("production job failed: %s", error_context, exc_info=True)
        job_store.update(
            job_id,
            status="failed",
            error=message,
            progress={
                "phase": "failed",
                "current": 1,
                "total": 1,
                "percent": 100,
                "message": message,
                "alpha_id": "",
                "error_context": error_context,
            },
        )

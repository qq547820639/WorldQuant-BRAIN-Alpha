"""Background production job runner for the local web console.

Supports two modes:
  run_job_service()       — raw AlphaResearchPipeline (backward-compat)
  run_guided_job_service() — GuidedPipeline with checkpoint/resume/history
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from brain_alpha_ops.observability import error_payload


RunConfigFromPayload = Callable[[dict[str, Any]], Any]
RunPipeline = Callable[..., Any]
ComputeRunStats = Callable[[dict[str, Any], Any], dict[str, Any]]
SafeErrorMessage = Callable[[Exception], str]


def run_guided_job_service(
    job_id: str,
    payload: dict[str, Any],
    *,
    job_store: Any,
    run_config_from_payload: RunConfigFromPayload,
    compute_run_stats: ComputeRunStats,
    safe_error_message: SafeErrorMessage,
    log: logging.Logger,
) -> None:
    """Run a production job using GuidedPipeline with checkpoint/resume support.

    The 'guided' mode in the web payload toggles this path; otherwise
    run_job_service() is used for backward compatibility.
    """
    try:
        from brain_alpha_ops.ux.guided_pipeline import GuidedPipeline

        job_store.update(
            job_id,
            status="running",
            progress={"phase": "startup", "current": 0, "total": 1, "percent": 0, "message": "引导式生产任务启动...", "alpha_id": ""},
        )
        run_config = run_config_from_payload(payload)
        guided = GuidedPipeline(
            run_config,
            stop_callback=lambda: job_store.is_cancelled(job_id),
        )

        phase_names = list(getattr(guided, "phases", {}) or {}) or ["guided"]

        def _progress_cb(phase: str, status: str = "", data: dict[str, Any] | None = None) -> None:
            progress_data = data if isinstance(data, dict) else {}
            try:
                current = phase_names.index(phase) + 1
            except ValueError:
                current = min(len(phase_names), 1)
            total = max(1, len(phase_names))
            explicit_percent = progress_data.get("percent")
            try:
                percent = float(explicit_percent)
            except (TypeError, ValueError):
                base = (current - 1) / total * 100.0
                percent = current / total * 100.0 if status == "completed" else max(5.0, base)
            percent = max(0.0, min(100.0, percent))
            message = (
                progress_data.get("message")
                or progress_data.get("summary")
                or progress_data.get("error")
                or status
                or phase
            )
            job_store.update(job_id, progress={
                "phase": phase,
                "status": status,
                "current": current,
                "total": total,
                "percent": round(percent, 1),
                "message": str(message),
                "alpha_id": str(progress_data.get("alpha_id") or ""),
                "data": progress_data,
            })

        guided.on_progress(_progress_cb)

        if payload.get("resume"):
            result = guided.resume()
        else:
            result = guided.run()

        final_status = "stopped" if job_store.is_cancelled(job_id) else "completed"
        raw_result_data = result.to_dict() if hasattr(result, "to_dict") else result
        result_data: dict[str, Any] = raw_result_data if isinstance(raw_result_data, dict) else {}
        raw_summary = result_data.get("summary")
        summary: dict[str, Any] = raw_summary if isinstance(raw_summary, dict) else {}
        candidates = summary.get("candidates") or result_data.get("candidates", [])

        job_store.update(
            job_id,
            status=final_status,
            result=result_data,
            progress={
                "phase": final_status,
                "current": 1,
                "total": 1,
                "percent": 100,
                "message": "引导式任务完成。" if final_status == "completed" else "任务已停止。",
                "alpha_id": "",
                "data": {
                    "candidates": candidates,
                    "stats": compute_run_stats({"candidates": candidates}, run_config),
                    "checkpoint_available": True,
                },
            },
        )
    except Exception as exc:
        message = safe_error_message(exc)
        error_context = error_payload(exc, error_code="GUIDED_JOB_FAILED", job_id=job_id, phase="guided_run")
        log.error("guided production job failed: %s", error_context, exc_info=True)
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
